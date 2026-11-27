"""Growth/difference of one item over two years: when the agent's two one-year steps look wrong, re-read ONE page
for both years at once.

Dev diagnosis 11-27 (calculation run 071530): in 21 of 45 misses the gold page was retrieved but a figure was wrong.
The gold page is a table with both years side by side, yet each step reads one year on its own:
- both steps read the same column of that table -> the same figure twice -> "selisih 0" (bd0227, bd0254, bd0264);
- one step reads the table, the other takes the second year from another page (bd0246, bd0268, bd0279, bd0283);
- one step has no citation at all (bd0225).
Here the cited page(s) are re-read with one prompt asking for both years. A read is accepted only when both figures
are on the page, they differ, and one of them equals a step's figure (so a step answer that was right anchors the
read to the right row). The answer is then written by `stepcalc`. Anything else returns None and the agent goes on
as before."""
import json
import re

from openai import OpenAI

from telaah import stepcalc, tools
from telaah.answer import _chat
from telaah.metrics import _norm
from telaah.twoyear import DIFF_RE, GROWTH_RE

SYSTEM = """Kamu membaca SATU halaman laporan keuangan. Ambil nilai item yang ditanyakan pada dua periode: {old} dan {new}.
Halaman biasanya memuat tabel dengan kolom {new} dan {old} berdampingan: cari baris item itu, lalu ambil angka di kolom masing-masing tahun.
Pembacaan sebelumnya (salah satunya bisa keliru, misalnya kolom yang sama dibaca dua kali): {hint}. Cari baris yang memuat angka itu.
Salin angka PERSIS seperti tertulis (jangan dikonversi, jangan dihitung).
Keluarkan HANYA JSON: {{"{old}": "angka", "{new}": "angka"}}"""
MAX_PAGE_CHARS = 8000
NUM_RE = re.compile(r"\d[\d.,]*\d|\d")


def _value(tok: str) -> float | None:
    try:
        return float(_norm(tok))
    except ValueError:
        return None


def _parsed(steps: list[dict], years: list[str]) -> dict | None:
    """{year: (step, figure)} when each of the two steps asks for one of the two years and states one figure."""
    by_year = {}
    for s in steps:
        ys, fig = stepcalc.periods(s["q"]), stepcalc.figure(s.get("answer", ""))
        if len(ys) != 1 or ys[0] not in years or ys[0] in by_year or fig is None:
            return None
        by_year[ys[0]] = (s, fig)
    return by_year


def candidates(question: str, steps: list[dict]) -> list[tuple[str, int]] | None:
    """Pages to re-read (newer-year step's page first), or None when the steps look fine or the question is not a
    two-year growth/difference of one item."""
    years = stepcalc.periods(question)
    if bool(GROWTH_RE.search(question)) == bool(DIFF_RE.search(question)) or len(years) != 2 or len(steps) != 2:
        return None
    if not all(s.get("status") == "ok" for s in steps):
        return None
    by_year = _parsed(steps, years)
    if not by_year:
        return None
    (s_old, f_old), (s_new, f_new) = by_year[years[0]], by_year[years[1]]
    if f_old["pct"] or f_new["pct"]:
        return None  # percentages (ratios) are rarely one table row with two year columns; leave them alone
    pages = [tuple(s["citations"][0]) if s.get("citations") else None for s in (s_new, s_old)]
    cited = list(dict.fromkeys(p for p in pages if p))
    if not cited:
        return None
    if None in pages or len(cited) == 2:
        return cited  # one step without a citation, or the two years from two different pages
    same_figure = _value(_norm_tok(f_old)) == _value(_norm_tok(f_new))
    return cited if same_figure else None  # one page, same figure twice = one column read twice


def _norm_tok(fig: dict) -> str:
    m = NUM_RE.search(fig["text"])
    return m.group(0) if m else ""


def read(llm: OpenAI, question: str, page: tuple[str, int], years: list[str], hint: str) -> tuple[str, str, str] | None:
    """(old figure, new figure, page text) as written on the page, or None when the page does not give two
    different figures that both occur on it. `hint`: what the steps read ('2023 -> 2,416,792; 2024 -> ...')."""
    try:
        text = tools.read_page_text(*page)
    except KeyError:
        return None
    old, new = years
    raw = _chat(llm, SYSTEM.format(old=old, new=new, hint=hint),
                f"Halaman [{page[0]} p.{page[1]}]:\n{text[:MAX_PAGE_CHARS]}\n\nPertanyaan: {question}")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    toks = []
    for y in (old, new):
        hit = NUM_RE.search(str(data.get(y) or ""))
        if not hit:
            return None
        toks.append(hit.group(0))
    vals = [_value(t) for t in toks]
    if None in vals or vals[0] == vals[1]:
        return None
    if not tools.check_citation(page[0], page[1], " ".join(toks))["supported"]:
        return None  # a figure the page does not hold
    return toks[0], toks[1], text


def _suffix(fig: dict) -> str:
    unit = f" {stepcalc.WORD[fig['exp']]}" if fig["exp"] else ""
    return unit + (" Rupiah" if fig["cur"] else "")


def fix(llm: OpenAI, question: str, steps: list[dict]) -> list[dict] | None:
    """The two steps rewritten from one page that holds both years, or None (keep the steps as they are)."""
    pages = candidates(question, steps)
    if not pages:
        return None
    years = stepcalc.periods(question)
    by_year = _parsed(steps, years)
    if not by_year:
        return None
    step_values = {_value(_norm_tok(fig)): fig for _, fig in by_year.values()}
    hint = "; ".join(f"{y} -> {_norm_tok(by_year[y][1])}" for y in years)
    for page in pages:
        got = read(llm, question, page, years, hint)
        if not got:
            continue
        toks = dict(zip(years, got[:2]))
        anchor = next((step_values[_value(t)] for t in toks.values() if _value(t) in step_values), None)
        if anchor is None:
            continue  # neither figure matches a step: probably another row; do not trust it
        out = []
        for y in years:
            s, _ = by_year[y]
            shown = toks[y] if re.search(r"[.,]", toks[y]) else stepcalc.fmt(float(_norm(toks[y])))  # '2057330' -> '2.057.330'
            out.append({**s, "answer": f"Nilai pada tahun {y} adalah {shown}{_suffix(anchor)} [{page[0]} p.{page[1]}].",
                        "citations": [page], "context": (s.get("context") or "") + f"\n\n[{page[0]} p.{page[1]}]\n{got[2]}",
                        "pairread": True})
        return out
    return None


__all__ = ["candidates", "fix", "read"]
