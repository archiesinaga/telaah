"""Formatting and limits for the Gradio demo (`app.py`): no model calls here, so it is unit-tested."""
import re
import time

from telaah import tools
from telaah.answer import BANK_NAMES, CITE_RE, REFUSAL, entity_label

MIN_GAP_S = 15  # per visitor: seconds between questions
SESSION_MAX = 30  # per visitor: questions per session
PAGE_SHOW = 6000  # chars of a source page shown next to the answer

ROUTE_LABEL = {
    "facts": "tabel fakta (satu angka, dibaca langsung dari tabel laporan)",
    "rag": "RAG (cari halaman, lalu model menjawab dari halaman itu)",
    "agent": "agen (rencana → langkah → verifikasi → hitung)",
    "regulation": "regulasi + angka bank",
    "restatement": "angka dua laporan (penyajian kembali)",
    "refuse": "ditolak: bank di luar dokumen yang tersedia",
    "twoyear": "dua tahun dari satu laporan",
}
PART_LABEL = {"faq": "FAQ", "ringkasan": "ringkasan", "penjelasan": "penjelasan"}


def doc_label(doc_id: str) -> str:
    """'bri_2025' -> 'BRI LT 2025', 'ojk_pojk_22_2023__faq' -> 'POJK Nomor 22 Tahun 2023 (FAQ)'."""
    base, _, part = doc_id.partition("__")
    bank, _, year = base.partition("_")
    if bank in BANK_NAMES and year.isdigit():
        return f"{BANK_NAMES[bank]} LT {year}"
    name = entity_label([base])
    if name == base:  # e.g. ojk_pedoman_ai_perbankan_2025
        name = " ".join(w.upper() if w in ("ojk", "bi", "ai") else w.capitalize() for w in base.split("_"))
    return f"{name} ({PART_LABEL.get(part, part)})" if part else name


def cite_label(doc_id: str, page: int) -> str:
    return f"{doc_label(doc_id)}, hlm. {page}"


def is_refusal(r: dict) -> bool:
    return bool(r.get("refused")) or r.get("answer", "").strip().startswith(REFUSAL)


def display_answer(r: dict) -> str:
    """Answer markdown: readable citations, and a plain-language refusal instead of the raw marker."""
    from telaah.agent import split_cites

    text = CITE_RE.sub(lambda m: f"**[{cite_label(m.group(1).strip(), int(m.group(2)))}]**",
                       split_cites(r.get("answer", "")).strip())
    if is_refusal(r):
        why = text.replace(REFUSAL, "", 1).lstrip(" .:-\n")
        return "### Tidak ditemukan dalam dokumen\n*Not found in the documents.*" + (f"\n\n{why}" if why else "")
    return text


def trust_line(r: dict) -> str:
    """Are the answer's figures on the pages it cites? Same check as the agent's verifier (no LLM call)."""
    from telaah.agent import check_text, split_cites

    if is_refusal(r):
        return ""
    text = split_cites(r.get("answer", ""))
    if not CITE_RE.search(text):
        return "⚠ Jawaban tanpa sitasi halaman: periksa sendiri. *No page citation.*"
    # the agent's own verifier already allows its calculator results (a difference is on no page)
    bad = r["unsupported"] if r.get("route") == "agent" and r.get("verified") is not None else check_text(text)
    if not bad:
        calc = " Hasil hitungan dari kalkulator. *Computed figures come from the calculator.*" if (
            r.get("route") == "agent" and ((r.get("calc_result") or {}).get("expression") or "kalkulator" in r.get("context", ""))) else ""
        return "✓ Angka dalam jawaban ada di halaman yang dikutip. *Every figure is on a cited page.*" + calc
    missing = sorted({n for b in bad for n in b["missing"]})
    return ("⚠ Sebagian angka tidak ditemukan di halaman yang dikutip"
            + (f" ({', '.join(missing)})" if missing else "") + ". *Some figures are not on the cited pages.*")


def source_choices(r: dict) -> list[tuple[str, str]]:
    """(label, 'doc|page') for the cited pages; for a refusal or an uncited answer, the top retrieved pages."""
    from telaah.agent import split_cites

    pages = [] if is_refusal(r) else [(d.strip(), int(p)) for d, p in CITE_RE.findall(split_cites(r.get("answer", "")))]
    if not pages:
        pages = [tuple(p) for p in r.get("retrieved", [])[:5]]
    return [(cite_label(d, p), f"{d}|{p}") for d, p in dict.fromkeys(pages)]


YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def bold_figures(page_text: str, answer: str) -> str:
    """Bold the numbers on a page that the answer states (years and bare small integers are left alone)."""
    from telaah.agent import _claim

    wanted = {v for tok in tools.NUM_RE.findall(_claim(answer, set())) for v in tools.number_variants(tok)}
    if not wanted:
        return page_text

    def mark(m):
        tok = m.group(0)
        return f"**{tok}**" if not YEAR_RE.fullmatch(tok) and tools.number_variants(tok) & wanted else tok

    return tools.NUM_RE.sub(mark, page_text)


def page_view(value: str | None, answer: str) -> str:
    if not value:
        return ""
    doc, _, page = value.rpartition("|")
    try:
        text = tools.read_page_text(doc, int(page))
    except (KeyError, ValueError):
        return f"Halaman {value} tidak tersedia."
    more = "\n\n*… halaman dipotong / page truncated*" if len(text) > PAGE_SHOW else ""
    return f"#### {cite_label(doc, int(page))}\n\n{bold_figures(text[:PAGE_SHOW], answer)}{more}"


def how_md(r: dict, seconds: float, chart_note: bool = False) -> str:
    """The 'how it answered' panel: route, steps of the agent, calculator, second look, searched pages."""
    lines = [f"**Jalur / route:** {ROUTE_LABEL.get(r.get('route', ''), r.get('route', '-'))}  ",
             f"**Waktu / time:** {seconds:.1f} detik"]
    if chart_note:
        lines.append("\n*Membaca grafik (model visi) tidak tersedia di demo ini; jawaban hanya dari teks halaman. "
                     "Chart reading is off in this demo: answered from page text only.*")
    if r.get("look", 1) > 1:
        lo = (r["look"] - 1) * 5 + 1
        lines.append(f"\nDijawab pada pencarian lanjutan (halaman peringkat {lo}–{lo + 4}), lolos cek angka & sumber.")
    steps = r.get("steps") or []
    if steps:
        lines += ["\n| # | Langkah / step | Status | Jawaban langkah |", "|---|---|---|---|"]
        for i, st in enumerate(steps, 1):
            ans = re.sub(r"\s+", " ", CITE_RE.sub(lambda m: f"[{cite_label(m.group(1).strip(), int(m.group(2)))}]",
                                                   st.get("answer", "")))[:160].replace("|", "/")
            lines.append(f"| {i} | {st.get('q', '').replace('|', '/')} | {st.get('status', '')} | {ans} |")
    calc = r.get("calc_result") or {}
    if calc.get("expression"):
        from telaah.agent import fmt_id

        lines.append(f"\n**Kalkulator:** `{calc['expression']}` = {fmt_id(calc['value'])} {calc.get('unit', '')}")
    retrieved = list(dict.fromkeys(tuple(p) for p in r.get("retrieved", [])))[:5]
    if retrieved and not steps:
        lines.append("\n**Halaman teratas yang ditemukan / top pages:** " + "; ".join(cite_label(d, p) for d, p in retrieved))
    return "\n".join(lines)


def check_limit(times: list[float], now: float | None = None) -> str | None:
    """Message when this visitor must wait, else None. `times` are the visitor's earlier question times."""
    now = time.time() if now is None else now
    if len(times) >= SESSION_MAX:
        return f"Batas {SESSION_MAX} pertanyaan per sesi tercapai; muat ulang halaman nanti. *Session limit reached.*"
    if times and now - times[-1] < MIN_GAP_S:
        return f"Tunggu {MIN_GAP_S - (now - times[-1]):.0f} detik sebelum bertanya lagi. *Please wait a moment.*"
    return None


def corpus_md(doc_ids: list[str]) -> str:
    banks = sorted({d for d in doc_ids if d.split("_")[0] in BANK_NAMES})
    regs = sorted({d.split("__")[0] for d in doc_ids if d.split("_")[0] not in BANK_NAMES})
    return (f"**Laporan tahunan bank ({len(banks)}):** " + ", ".join(doc_label(d) for d in banks)
            + f"\n\n**Regulasi OJK/BI ({len(regs)}):** " + ", ".join(doc_label(d) for d in regs))
