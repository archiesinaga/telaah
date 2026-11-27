"""Growth or difference of one item between two years, from the agent's two verified step answers, computed in Python.

The calculator prompt asks the 7B to write the expression itself, unit conversion included, and it mixes units
(dev bd0248: "Rp108,61 triliun" and "Rp105.146.044 juta" became `105146044 - 10861000000`; bd0246: "40,669,669
Rupiah" and "40,480,205 juta Rupiah" became `40480205000 - 40669669`). Here each step's figure and its unit word are
read by code, brought to one unit, and the answer sentence is written in Python. Any failed check returns None and
the calculator prompt answers as before."""
import re

from telaah.answer import CITE_RE
from telaah.metrics import _norm
from telaah.twoyear import DIFF_RE, GROWTH_RE, compute, fmt

REPORT_YEAR_RE = re.compile(r"laporan tahunan\s*(?:\w+\s+){0,6}?20\d\d", re.I)  # names the source report, not a period
YEAR_RE = re.compile(r"\b20\d\d\b")
# one figure: optional Rp/USD, the number, then an optional unit word or percent sign
FIG_RE = re.compile(
    r"(?P<cur>Rp\.?\s?|USD\s?)?(?P<num>-?\d[\d.,]*\d|-?\d)(?P<pct>\s?%|\s?persen)?"
    r"(?:\s*(?P<unit>ribu|juta|miliar|milyar|triliun)\b)?", re.I)
EXP = {"ribu": 3, "juta": 6, "miliar": 9, "milyar": 9, "triliun": 12}
WORD = {3: "ribu", 6: "juta", 9: "miliar", 12: "triliun"}
# one item rarely moves more than 10x in a year (largest dev calculation gold: +267,77%, a 3.7x ratio); a bigger
# gap between the two step figures means a dropped unit word ("6,14 juta" vs "7.045.749") or a wrong row
MAX_RATIO = 10
DATE_RE = re.compile(r"\b\d{1,2}\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\b", re.I)


def periods(text: str) -> list[str]:
    """Distinct years in a question or step, ignoring the year of a named source report."""
    return sorted(set(YEAR_RE.findall(REPORT_YEAR_RE.sub(" ", text))))


def figure(answer: str) -> dict | None:
    """The one figure a step answer states: 'X pada tahun 2024 adalah 585.615 juta Rupiah [bri_2024 p.1184].' ->
    {'value': 585615.0, 'exp': 6, 'pct': False, 'cur': True, 'text': '585.615 juta Rupiah'}. Read after the last
    'adalah' (the sentence repeats the question before it); None when there is no figure or more than one."""
    text = CITE_RE.sub(" ", answer)
    if "adalah" in text.lower():
        text = text[text.lower().rfind("adalah") + len("adalah"):]
    text = DATE_RE.sub(" ", text)
    found = []
    for m in FIG_RE.finditer(text):
        num = m.group("num")
        if YEAR_RE.fullmatch(num) and not (m.group("cur") or m.group("unit") or m.group("pct")):
            continue  # a year, not a figure
        try:
            value = float(_norm(num))
        except ValueError:
            return None
        found.append({"value": value, "exp": EXP[m.group("unit").lower()] if m.group("unit") else None,
                      "pct": bool(m.group("pct")), "cur": bool(m.group("cur")) or "rupiah" in text[m.end():m.end() + 12].lower(),
                      "text": m.group(0).strip()})
    return found[0] if len(found) == 1 else None


def answer(question: str, steps: list[dict]) -> list[str] | None:
    """Answer lines (same use as `facts.pair_comparison`) or None -> the calculator prompt."""
    grow, diff = bool(GROWTH_RE.search(question)), bool(DIFF_RE.search(question))
    years = periods(question)
    if grow == diff or len(years) != 2 or len(steps) != 2 or not all(s.get("status") == "ok" for s in steps):
        return None
    by_year = {}
    for s in steps:
        ys, fig = periods(s["q"]), figure(s.get("answer", ""))
        if len(ys) != 1 or ys[0] not in years or ys[0] in by_year or fig is None:
            return None
        by_year[ys[0]] = (s, fig)
    (s_old, old), (s_new, new) = by_year[years[0]], by_year[years[1]]
    if old["pct"] != new["pct"]:
        return None
    if old["pct"] and diff:
        return None  # a gap between two percentages is in points; leave it to the calculator prompt
    exps = {f["exp"] for f in (old, new)} - {None}
    if len(exps) == 2:  # different unit words: bring both to the smaller unit
        base = min(exps)
        v_old, v_new = (f["value"] * 10 ** (f["exp"] - base) for f in (old, new))
    else:  # same unit word, or one figure without a unit word (the 7B drops it): read both in the same unit
        base = exps.pop() if exps else None
        v_old, v_new = old["value"], new["value"]
    if v_old == v_new:
        return None  # two years with the same figure is almost always one column read twice (dev bd0254)
    if not old["pct"] and v_old and v_new and max(abs(v_old), abs(v_new)) / min(abs(v_old), abs(v_new)) > MAX_RATIO:
        return None  # units guessed wrong or the wrong row read (dev bd0224, bd0225, bd0233); calculator prompt instead
    result = compute("growth_pct" if grow else "difference", v_old, v_new)
    if result is None:
        return None
    cites = []
    for s in (s_old, s_new):
        for c in s.get("citations") or []:
            if tuple(c) not in cites:
                cites.append(tuple(c))
    cite = " ".join(f"[{d} p.{p}]" for d, p in cites)
    vals = f"nilai {years[0]}: {old['text']}; nilai {years[1]}: {new['text']}"
    if grow:
        return [f"Pertumbuhan antara {years[0]} dan {years[1]} adalah {result} ({vals}) {cite}".rstrip() + "."]
    unit = ""
    if base is not None:
        unit = " " + WORD[base] + (" Rupiah" if old["cur"] or new["cur"] else "")
    elif old["cur"] or new["cur"]:
        unit = " Rupiah"
    way = "naik" if v_new > v_old else "turun"
    return [f"Selisih antara {years[0]} dan {years[1]} adalah {result}{unit} ({way}; {vals}) {cite}".rstrip() + "."]


__all__ = ["answer", "figure", "periods", "fmt"]
