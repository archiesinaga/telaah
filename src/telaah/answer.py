import json
import os
import re
import time

from openai import OpenAI

from telaah.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MIN_INTERVAL,
    LLM_MODEL,
    MAX_ANSWER_TOKENS,
    TOP_K,
    VISION_PAGES,
)
from telaah.retrieve import entity_groups, retrieve, retrieve_entity

REFUSAL = "TIDAK DITEMUKAN"
SPLIT_SYSTEM = """Kamu memecah pertanyaan perbandingan menjadi pertanyaan sederhana, satu per entitas.
Keluarkan HANYA array JSON berisi tepat satu string per entitas, dalam urutan entitas yang diberikan.
Aturan untuk setiap pertanyaan:
- Tanyakan NILAI angkanya ("Berapa ..."), bukan ya/tidak, dan tanpa kata selisih/bandingkan/mana yang lebih.
- Pakai istilah indikator persis seperti pertanyaan asli (misalnya konsolidasian, bank only, gross) dan periodenya.
- Jangan sebut satuan (juta/miliar/triliun): laporan bisa memakai satuan lain.
- Pertahankan keterangan sumber angka seperti "menurut laporan tahunan 2024" atau "setelah disajikan kembali".
- Untuk angka milik bank, sebut nama bank dan tahunnya. Bila bank yang sama muncul dua kali (laporan tahun
  berbeda), sebut tahun laporannya. Untuk angka eksternal yang hanya dikutip dalam laporan (misalnya data
  industri, BI-Rate), tanyakan angka itu saja tanpa menyebut bank atau laporan sumbernya.
- Untuk peraturan, tanyakan angka atau ketentuan yang diatur, sebut nama peraturannya.
Contoh 1: "Apakah LDR BNI 2024 memenuhi batas yang diatur POJK Nomor 5 Tahun 2020?"
Entitas: 1. BNI (laporan tahunan 2024)  2. POJK Nomor 5 Tahun 2020
Keluaran: ["Berapa LDR BNI tahun 2024?", "Berapa batas LDR yang diatur POJK Nomor 5 Tahun 2020?"]
Contoh 2: "Berapa selisih ROA BCA 2024 dan rata-rata ROA industri perbankan 2024 yang dikutip laporan BNI 2024?"
Entitas: 1. BCA (laporan tahunan 2024)  2. BNI (laporan tahunan 2024)
Keluaran: ["Berapa ROA BCA tahun 2024?", "Berapa rata-rata ROA industri perbankan tahun 2024?"]"""
BANK_NAMES = {"bri": "BRI", "mandiri": "Bank Mandiri", "bni": "BNI", "bca": "BCA", "btn": "BTN"}
# headline statement items in annual reports are consolidated; the word matches the summary-table header
# ('LAPORAN POSISI KEUANGAN KONSOLIDASIAN'): 'total aset BRI' ranks the summary page 22nd, with it 5th
STATEMENT_ITEM_RE = re.compile(r"aset|laba|ekuitas|kredit|dpk|dana pihak ketiga", re.I)
CITE_RE = re.compile(r"\[([^\[\]]+?)\s+p\.(\d+)\]")

SYSTEM = f"""Kamu adalah asisten riset dokumen keuangan Indonesia.
Jawab HANYA berdasarkan konteks. Setiap klaim wajib diberi sitasi format [doc_id p.N]
sesuai label konteks, contoh: "Laba bersih Rp1.000 juta [bri_2025 p.28]". Gunakan label persis
seperti di konteks, dan taruh sitasi di akhir kalimat yang memuat klaim. Jika konteks tidak memuat jawaban, jawab persis: {REFUSAL}.
Jawab dalam bahasa pertanyaan."""


def parse_citations(text: str) -> list[tuple[str, int]]:
    return [(d.strip(), int(p)) for d, p in CITE_RE.findall(text)]


YEAR_CELL_RE = re.compile(r"(19|20)[0-9]{2}( ?[*]+)?")


def year_rows(text: str) -> str:
    """Rewrite markdown tables whose header is a row of years so every value carries its year:
    '| RIM | 78,35% | ... | 84,52% |' -> 'RIM: 2021=78,35%; ...; 2025=84,52%'. The 7B misread wide
    five-year tables (wrong row or column) when the header was far above the row."""
    out, years = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            years = None
            out.append(line)
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue  # separator row
        head = cells[1:]
        if len(head) >= 2 and all(YEAR_CELL_RE.fullmatch(c) for c in head if c) and sum(1 for c in head if c) >= 2:
            years = head
            out.append(f"{cells[0]} (kolom: {', '.join(c for c in head if c)})")
            continue
        if years and len(cells) == len(years) + 1:
            label, vals = cells[0], cells[1:]
            pairs = [f"{y}={v}" for y, v in zip(years, vals) if v and v != label]
            out.append(f"{label}: {'; '.join(pairs)}" if pairs else label)
            continue
        out.append(line)
    return "\n".join(out)


# year_rows made eval worse (table numeric 0.87 -> 0.67: the 7B refused or misread rewritten rows), so it is opt-in
YEAR_ROWS = os.getenv("YEAR_ROWS", "0") == "1"


def compact(text: str) -> str:
    """Drop markdown table padding so the 3000-char cap keeps real content."""
    text = re.sub(r" {2,}", " ", year_rows(text) if YEAR_ROWS else text)
    return re.sub(r"-{3,}", "---", text)


VISION_HINT = (
    "Catatan: bagian [Transkripsi gambar halaman oleh model visi] berisi angka yang tercetak pada grafik di "
    "halaman itu. Angka tersebut adalah bukti yang sah; cocokkan label dan periodenya dengan pertanyaan.\n\n"
)
VISION_TEXT_CAP = 800  # page text kept next to a full image transcription (keeps the prompt in 8192 tokens)
TRANSCRIPT_CAP = 1500  # index-time chart transcription kept per page


PAGE_CAP = 3000  # chars per page
CONTEXT_CHARS = 16000  # page-text budget (~6k tokens) so the prompt fits the 8192-token window


QUESTION_STOP = {
    "berapa", "pada", "tahun", "akhir", "laporan", "tahunan", "menurut", "gunakan", "data", "dari", "masing",
    "dalam", "rupiah", "persen", "desimal", "yang", "dan", "atau", "untuk", "dengan", "apakah", "bank", "nilai",
    "angka", "per", "juta", "miliar", "triliun", "konsolidasian", "sebutkan", "hitung", "antara", "sampai",
}
YEAR_HEAD_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def excerpt(text: str, question: str, cap: int) -> str:
    """First `cap` chars of a page, unless the table row the question is about lies beyond them: then keep the
    page head, the nearest year-header row and a window around that row (wide summary tables put 'Total Aset'
    or the capital ratio past char 3000). Unchanged whenever the best-matching row is already inside the cap."""
    if len(text) <= cap or not question:
        return text[:cap]
    kws = {w for w in re.findall(r"[a-z]{3,}", question.lower()) if w not in QUESTION_STOP}
    if not kws:
        return text[:cap]
    lines, offs, pos = text.split("\n"), [], 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1
    scores = [len({k for k in kws if k in ln.lower()}) for ln in lines]
    best = max(range(len(lines)), key=lambda i: (scores[i], -i))
    if scores[best] < 2 or offs[best] + len(lines[best]) + 80 <= cap:  # nothing better beyond the cap
        return text[:cap]
    head_n = min(600, cap // 4)
    header = next((lines[j] for j in range(best - 1, -1, -1) if len(YEAR_HEAD_RE.findall(lines[j])) >= 3), "")
    budget = cap - head_n - len(header) - 10
    start = max(head_n, offs[best] - budget // 3)
    return text[:head_n] + "\n...\n" + (header + "\n" if header else "") + text[start:start + budget]


def build_context(chunks: list[dict], question: str = "") -> str:
    plain = max(1, sum(1 for c in chunks if not c.get("vision")))
    cap = min(PAGE_CAP, CONTEXT_CHARS // plain)  # many pages (multi-entity questions) share the budget
    parts = []
    for c in chunks:
        if c.get("vision"):
            body = "[Transkripsi gambar halaman oleh model visi]\n" + c["vision"].strip()
            body += "\n\n[Teks halaman]\n" + compact(c["text"])[:VISION_TEXT_CAP]
        elif c.get("transcript"):  # chart values transcribed at index time (telaah.transcripts)
            body = "[Transkripsi grafik halaman oleh model visi]\n" + c["transcript"].strip()[:TRANSCRIPT_CAP]
            body += "\n\n[Teks halaman]\n" + excerpt(compact(c["text"]), question, max(VISION_TEXT_CAP, cap - TRANSCRIPT_CAP))
        else:
            body = excerpt(compact(c["text"]), question, cap)
        parts.append(f"[{c['doc_id']} p.{c['page']}]\n{body}")
    return "\n\n".join(parts)


def add_page_images(question: str, chunks: list[dict]) -> tuple[list[dict], list[tuple[str, int]]]:
    """Chart questions: transcribe the top retrieved pages, rendered from the source PDF; the
    transcription goes FIRST in that page's context (see build_context). Any report with a PDF qualifies,
    not only the few in the ColPali index (gating on that index refused 20 of 28 dev chart questions)."""
    from telaah import vision

    if not (vision.enabled() and vision.wants_image(question)):
        return chunks, []
    out, done = [], []
    for c in chunks:
        if len(done) < VISION_PAGES and vision.has_pdf(c["doc_id"]):
            try:
                reading = vision.read_page(question, c["doc_id"], c["page"])
            except Exception as e:  # noqa: BLE001 - fall back to the text-only context
                print(f"[telaah] vision step skipped: {e}")
                reading = ""
            if reading and not reading.upper().startswith(vision.IRRELEVANT):
                c = {**c, "vision": reading}
                done.append((c["doc_id"], c["page"]))
        out.append(c)
    return out, done


_last_call = 0.0


def throttle() -> None:
    """Keep LLM calls at least LLM_MIN_INTERVAL seconds apart (free API tiers cap requests per minute)."""
    global _last_call
    if LLM_MIN_INTERVAL > 0:
        wait = _last_call + LLM_MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _chat(llm: OpenAI, system: str, user: str) -> str:
    throttle()
    resp = llm.chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        max_tokens=MAX_ANSWER_TOKENS,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content or ""


def entity_label(doc_ids: list[str]) -> str:
    """Readable name for the split prompt: 'bri_2025' -> 'BRI (laporan tahunan 2025)',
    'bi_padg_23_2025' -> 'PADG Nomor 23 Tahun 2025'. Doc ids in sub-questions hurt retrieval."""
    names = []
    for d in doc_ids:
        parts = d.split("__")[0].split("_")  # '__faq', '__ringkasan' ... are parts of the same regulation
        if len(parts) == 2 and parts[0] in BANK_NAMES:
            names.append(f"{BANK_NAMES[parts[0]]} (laporan tahunan {parts[1]})")
        elif len(parts) == 4 and parts[0] in ("bi", "ojk"):
            names.append(f"{parts[1].upper()} Nomor {parts[2]} Tahun {parts[3]}")
        else:
            names.append(d)
    return " / ".join(dict.fromkeys(names))


def _consolidated(sub: str, group: list[str]) -> str:
    """Annual-report statement items without 'bank only' -> ask for the consolidated figure."""
    low = sub.lower()
    is_report = all(d.split("_")[0] in BANK_NAMES for d in group)
    if is_report and STATEMENT_ITEM_RE.search(sub) and "bank only" not in low and "konsolidasi" not in low:
        return sub.rstrip(" ?") + " (konsolidasian)?"
    return sub


def refine_step(step: str, question: str) -> str:
    """Planner step for a single-document question: add what the planner dropped, so it retrieves like a seed
    question - 'konsolidasian' for statement items (ranks the summary table first) and the named source
    report ('menurut Laporan Tahunan 2025'), which pins the restated prior-year columns."""
    from telaah.filters import SOURCE_RE, detect_groups

    groups = detect_groups(step)
    if groups:
        step = _consolidated(step, groups[0])
    src = SOURCE_RE.findall(question.lower())
    if src and not SOURCE_RE.search(step.lower()):
        step = step.rstrip(" ?") + f" (menurut Laporan Tahunan {src[0]})?"
    return step


def split_question(llm: OpenAI, question: str, groups: list[list[str]]) -> list[str]:
    """One simple question per entity (LLM); falls back to the original question per entity."""
    ents = "\n".join(f"{i + 1}. {entity_label(g)}" for i, g in enumerate(groups))
    raw = _chat(llm, SPLIT_SYSTEM, f"Pertanyaan: {question}\n\nEntitas (urutan):\n{ents}")
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        subs = json.loads(m.group(0)) if m else []
    except ValueError:
        subs = []
    subs = subs[: len(groups)]  # the model sometimes appends the comparison itself as an extra item
    if len(subs) == len(groups) and all(isinstance(s, str) and s.strip() for s in subs):
        return [_consolidated(s, g) for s, g in zip(subs, groups)]
    return [question] * len(groups)


def answer_entity(llm: OpenAI, sub: str, group: list[str], n: int | None = None, later: list[str] | None = None):
    """One simple question answered from ONE entity's documents: (answer, chunks, vision pages, context).
    `later`: the same bank's newer reports, whose top pages follow the own ones (their comparison tables hold
    this year's figures as the prior-year column)."""
    got = retrieve_entity(sub, group, *([] if n is None else [n]))
    if later:
        seen = {(c["doc_id"], c["page"]) for c in got}
        got += [c for c in retrieve_entity(sub, later) if (c["doc_id"], c["page"]) not in seen]
    chunks, vp = add_page_images(sub, got)
    ctx = build_context(chunks, sub)
    got = _chat(llm, SYSTEM, f"{VISION_HINT if vp else ''}Konteks:\n{ctx}\n\nPertanyaan: {sub}")
    return got, chunks, vp, ctx


def ask_entities(question: str, groups: list[list[str]]) -> dict:
    """Cross-document question: split into one question per entity, answer each from that entity's
    own pages with the normal pipeline, then compose. Keeps the 7B from mixing figures of banks/documents."""
    llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
    subs = split_question(llm, question, groups)
    all_chunks, vision_pages, raw, parts, any_answer, per_entity = [], [], [], [], False, []
    for sub, g in zip(subs, groups):
        got, chunks, vp, ctx = answer_entity(llm, sub, g)
        all_chunks += chunks
        per_entity.append([(c["doc_id"], c["page"]) for c in chunks])
        vision_pages += vp
        raw.append(ctx)
        any_answer = any_answer or REFUSAL not in got
        parts.append(f"[Jawaban untuk: {sub}]\n{got.strip()}")
    if any_answer:
        text = _chat(
            llm,
            SYSTEM,
            "Konteks:\n" + "\n\n".join(parts) + f"\n\nPertanyaan: {question}\n"
            "Jawab dari jawaban-jawaban di atas; hitung selisih bila diminta dan pertahankan sitasi [doc_id p.N].",
        )
    else:
        text = REFUSAL
    if CITE_REPAIR and any_answer:  # the compose call may cite a neighbouring page of an entity's own page
        text = repair_cites(text, [(c["doc_id"], c["page"]) for c in all_chunks])
    return {
        "answer": text,
        "citations": parse_citations(text),
        "retrieved": [(c["doc_id"], c["page"]) for c in all_chunks],
        "retrieved_groups": per_entity,  # per entity, for recall@k
        "context": "\n\n".join(raw),
        "refused": REFUSAL in text,
        "vision": vision_pages,
        "sub_questions": subs,
        "sub_answers": parts,
    }

# Second look (opt-in): a refusal from the top k pages is asked again on ranks k+1..2k, then 2k+1..3k (text only,
# no vision). Dev experiment, 10-25 (27 wrongly refused, 22 unanswerable): 17 rescued, 1 unanswerable answered
# with a figure from another regulation. A later answer is kept only if `later_look_ok` accepts it.
SECOND_LOOK = os.getenv("TELAAH_SECOND_LOOK", "0") == "1"
# Opt-in: a cited page that lacks the answer's figures is replaced by the retrieved page that holds them (the agent
# already does this per step). Seen in the demo: RIM thresholds cited PADG p.4, the figures are on p.7.
CITE_REPAIR = os.getenv("TELAAH_CITE_REPAIR", "0") == "1"
LOOKS = 3


def later_look_ok(question: str, text: str, pages: list[tuple[str, int]]) -> tuple[str, bool]:
    """(repaired answer, accept?) for an answer from a later look: it must cite, every number must be on a
    cited page (after moving a citation to the look page holding it), and when the question names banks or
    regulations every cited document must be one of them (the leaked answer cited POJK 22/2023 for POJK 12/2024)."""
    from telaah.agent import check_text, repair_text
    from telaah.filters import named_prefixes

    text = repair_text(text, pages)
    cites = parse_citations(text)
    named = named_prefixes(question)
    on_topic = all(any(d.startswith(p) for p in named) for d, _ in cites) if named else True
    return text, bool(cites) and on_topic and not check_text(text)


def repair_cites(text: str, pages: list[tuple[str, int]]) -> str:
    from telaah.agent import repair_split, repair_text

    return repair_split(repair_text(text, pages), pages)


POOL_EXTRA = 5


def ask(question: str, k: int | None = None, pool_with: str | None = None) -> dict:
    """`pool_with`: a sibling question (the agent passes the original one) whose top POOL_EXTRA pages are added after
    this question's own top k, so every step of a two-period question sees the page that holds both columns."""
    groups = entity_groups(question)
    if groups:  # no second look here: each entity's own top k only
        return ask_entities(question, groups)
    n = TOP_K if k is None else k
    pool = retrieve(question, k=n * LOOKS if SECOND_LOOK else n)  # same top n for any k
    first = pool[:n]
    if pool_with and pool_with != question:
        seen = {(c["doc_id"], c["page"]) for c in first}
        first = first + [c for c in retrieve(pool_with, k=POOL_EXTRA) if (c["doc_id"], c["page"]) not in seen]
    chunks, vision_pages = add_page_images(question, first)
    llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
    hint = VISION_HINT if vision_pages else ""
    context = build_context(chunks, question)
    text = _chat(llm, SYSTEM, f"{hint}Konteks:\n{context}\n\nPertanyaan: {question}")
    retrieved, look = [(c["doc_id"], c["page"]) for c in chunks], 1
    if CITE_REPAIR and REFUSAL not in text:
        text = repair_cites(text, retrieved)
    for i in range(1, LOOKS if SECOND_LOOK else 1):
        part = pool[i * n:(i + 1) * n]
        if REFUSAL not in text or not part:
            break
        pages = [(c["doc_id"], c["page"]) for c in part]
        retrieved += pages
        ctx = build_context(part, question)
        got = _chat(llm, SYSTEM, f"Konteks:\n{ctx}\n\nPertanyaan: {question}")
        if REFUSAL in got:
            continue
        got, ok = later_look_ok(question, got, pages)
        if ok:
            text, context, look = got, ctx, i + 1
        break  # an answer that fails the check ends the search: keep the refusal
    return {
        "answer": text,
        "citations": parse_citations(text),
        "retrieved": retrieved,  # first n = first look, so recall@k is unchanged
        "context": context,
        "refused": REFUSAL in text,
        "vision": vision_pages,
        "look": look,
    }
