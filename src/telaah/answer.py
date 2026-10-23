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


def answer_entity(llm: OpenAI, sub: str, group: list[str], n: int | None = None):
    """One simple question answered from ONE entity's documents: (answer, chunks, vision pages, context)."""
    chunks, vp = add_page_images(sub, retrieve_entity(sub, group, *([] if n is None else [n])))
    ctx = build_context(chunks, sub)
    got = _chat(llm, SYSTEM, f"{VISION_HINT if vp else ''}Konteks:\n{ctx}\n\nPertanyaan: {sub}")
    return got, chunks, vp, ctx


def ask_entities(question: str, groups: list[list[str]]) -> dict:
    """Cross-document question: split into one question per entity, answer each from that entity's
    own pages with the normal pipeline, then compose. Keeps the 7B from mixing figures of banks/documents."""
    llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
    subs = split_question(llm, question, groups)
    all_chunks, vision_pages, raw, parts, any_answer = [], [], [], [], False
    for sub, g in zip(subs, groups):
        got, chunks, vp, ctx = answer_entity(llm, sub, g)
        all_chunks += chunks
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
    return {
        "answer": text,
        "citations": parse_citations(text),
        "retrieved": [(c["doc_id"], c["page"]) for c in all_chunks],
        "context": "\n\n".join(raw),
        "refused": REFUSAL in text,
        "vision": vision_pages,
        "sub_questions": subs,
        "sub_answers": parts,
    }

def ask(question: str, k: int | None = None) -> dict:
    groups = entity_groups(question)
    if groups:
        return ask_entities(question, groups)
    chunks, vision_pages = add_page_images(question, retrieve(question, **({} if k is None else {"k": k})))
    llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
    hint = VISION_HINT if vision_pages else ""
    throttle()
    resp = llm.chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        max_tokens=MAX_ANSWER_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": f"{hint}Konteks:\n{build_context(chunks, question)}\n\nPertanyaan: {question}",
            },
        ],
    )
    text = resp.choices[0].message.content or ""
    return {
        "answer": text,
        "citations": parse_citations(text),
        "retrieved": [(c["doc_id"], c["page"]) for c in chunks],
        "context": build_context(chunks, question),
        "refused": REFUSAL in text,
        "vision": vision_pages,
    }
