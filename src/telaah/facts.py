"""Structured facts table: key bank indicators per (bank, year), parsed by code from the report tables.

Generic extractor (no per-page spec): every markdown table in a bank report whose header row has year columns
is read row by row; a row whose label matches an indicator alias becomes one fact per year column. The gold
facts in eval/agent_tasks.jsonl are only used to score this extractor (eval/check_facts.py), never to build it.

    .venv/Scripts/python -m telaah.facts        # (re)build data/facts.sqlite

Schema `facts`: bank, report_year, doc, page, indicator, label, year, value, raw, unit, inherited
  unit: "pct" ratio in percent, "jt" million Rp, "mi" billion Rp, "tn" trillion Rp, "" unknown
  inherited: 1 when the year header came from the previous page (table continued across pages)
"""
import json
import re
import sqlite3
from collections import Counter
from functools import lru_cache

from telaah.config import PROCESSED_DIR, ROOT

DB_PATH = ROOT / "data" / "facts.sqlite"
REPORT_RE = re.compile(r"^(bri|bca|bni|btn|mandiri)_(20\d\d)$")
FOOT = r"\s*[*¹²³\d]{0,2}\s*$"  # trailing footnote marks: "Total Kredit 1", "2024 *"

# indicator -> (kind, label regexes on the normalised first cell); checked in order, first match wins,
# so roa/roe ("ROE - Tier 1 Capital") come before tier1, tier1 before car, and npl_net before npl_gross
INDICATORS: dict[str, tuple[str, list[str]]] = {
    "roa": ("pct", [r"return on assets?\b", r"\broa\b", r"imbal hasil aset"]),
    "roe": ("pct", [r"return on equity", r"\broe\b", r"imbal hasil ekuitas"]),
    "cet1": ("pct", [r"common equity tier", r"\bcet\s*1\b"]),
    "tier1": ("pct", [r"tier\s*(1|i)\b", r"modal inti"]),
    "car": ("pct", [r"\bkpmm\b", r"kewajiban penyediaan modal minimum", r"capital adequacy", r"rasio kecukupan modal",
                    r"^car" + FOOT]),
    "npl_net": ("pct", [r"\bnpl\b.*\b(net|neto|nett)\b", r"\b(net|neto)\b.*\bnpl\b", r"kredit bermasalah.*\bneto\b"]),
    "npl_gross": ("pct", [r"\bnpl\b.*\b(gross|bruto)\b", r"\b(gross|bruto)\b.*\bnpl\b", r"kredit bermasalah.*\bbruto\b"]),
    "ldr": ("pct", [r"loan to deposit ratio", r"\bldr\b"]),
    "nim": ("pct", [r"net interest margin", r"\bnim\b", r"marjin bunga bersih"]),
    "bopo": ("pct", [r"\bbopo\b", r"beban operasional terhadap (pendapatan|penghasilan) operasional",
                     r"operating (cost|expenses?)\s*(/|to)\s*operating income"]),
    "casa": ("pct", [r"\bcasa\b"]),
    "total_aset": ("money", [r"^(total|jumlah) aset" + FOOT, r"^total assets" + FOOT]),
    "laba": ("money", [r"^laba (bersih|tahun berjalan)" + FOOT, r"^(net income|net profit)" + FOOT,
                       r"^(profit|income) for the year" + FOOT]),
    "ekuitas": ("money", [r"^(total|jumlah) ekuitas" + FOOT, r"^total equity" + FOOT]),
    # not here: DPK and total loans. Their rows are spread over segment, sub-total and cash-flow tables
    # (BRI "Total Dana Pihak Ketiga" p288 = 2,2 T), so a lookup would be wrong; those stay on RAG
}
STOCKS = {"total_aset", "ekuitas"}  # balances: a negative cell is a cash-flow change, not the balance
# a table under such a heading holds one segment or entity, not the bank's figure ("bank only" is not one of
# these: the regulatory ratios are reported bank only)
SEGMENT_RE = re.compile(r"segmen|segment|entitas anak|anak perusahaan|subsidiar", re.I)
# ratios built on an indicator ("LLR/NPL Bruto (Coverage Ratio)") are not the indicator
DERIVED_RE = re.compile(r"coverage|\bllr\b|cadangan|/\s*npl|terhadap npl|to npl", re.I)
YEAR_CELL = re.compile(r"^(?:fy\s*)?((?:19|20)\d\d)" + FOOT, re.I)
NUM_CELL = re.compile(r"^\(?-?\d[\d.,]*\)?\s*%?$")
UNIT_RE = re.compile(r"\b(?:dalam|in)\s+(jutaan|juta|miliar|milyar|triliun|millions?|billions?|trillions?)\b", re.I)
UNIT = {"jutaan": "jt", "juta": "jt", "million": "jt", "millions": "jt", "miliar": "mi", "milyar": "mi",
        "billion": "mi", "billions": "mi", "triliun": "tn", "trillion": "tn", "trillions": "tn"}


def norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("*", " ")).strip().lower()


def indicator_of(label: str) -> str | None:
    lab = norm_label(label)
    if DERIVED_RE.search(lab):
        return None
    for ind, (_, pats) in INDICATORS.items():
        if any(re.search(p, lab) for p in pats):
            return ind
    return None


def number_style(cells: list[str]) -> str:
    """'id' (1.234,5) or 'en' (1,234.5): a separator followed by 1-2 digits at the end is a decimal mark."""
    c = Counter()
    for s in cells:
        s = s.strip("()% ")
        if re.search(r"\d,\d{1,2}$", s):
            c["id"] += 1
        elif re.search(r"\d\.\d{1,2}$", s):
            c["en"] += 1
    return "en" if c["en"] > c["id"] else "id"


def parse_num(s: str, style: str) -> float | None:
    s = s.strip()
    if not NUM_CELL.match(s):
        return None
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()%- ")
    s = s.replace(",", "") if style == "en" else s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _header_years(cells: list[str]) -> dict[int, int]:
    """Column index -> year for a header row with at least two year cells (other columns, e.g. YoY, are skipped)."""
    cols = {i: int(m.group(1)) for i, c in enumerate(cells) if i > 0 and (m := YEAR_CELL.match(c))}
    return cols if len(cols) >= 2 and len(set(cols.values())) == len(cols) else {}


def _unit(kind: str, header_first: str, context: str, page_text: str, doc_unit: str) -> str:
    """Nearest statement first: header cell, text just above the table, the page, the report's usual unit."""
    if kind == "pct":
        return "pct"
    m = UNIT_RE.search(header_first) or UNIT_RE.search(context) or UNIT_RE.search(page_text)
    return UNIT[m.group(1).lower()] if m else doc_unit


def extract_doc(doc: str) -> list[dict]:
    m = REPORT_RE.match(doc)
    if not m:
        return []
    bank, report_year = m.group(1), int(m.group(2))
    pages = [json.loads(l) for l in open(PROCESSED_DIR / f"{doc}.jsonl", encoding="utf-8")]
    style = number_style([c for p in pages for l in p["text"].split("\n") if l.lstrip().startswith("|")
                          for c in _cells(l)[1:]])
    units = Counter(UNIT[m.group(1).lower()] for p in pages for m in UNIT_RE.finditer(p["text"]))
    doc_unit = units.most_common(1)[0][0] if units else ""
    out = []
    carry: tuple[dict[int, int], str, int] | None = None  # last header of the previous page: cols, first cell, width
    for p in pages:
        header, inherited, first_table = None, 0, True
        prev_table_line, context, segment = False, [], False
        for line in p["text"].split("\n"):
            if not line.lstrip().startswith("|"):
                if prev_table_line:
                    header, first_table, context = None, False, []
                prev_table_line = False
                if line.strip():
                    context = (context + [line.strip()])[-3:]  # heading and unit line just above the next table
                continue
            cells = _cells(line)
            new_table = not prev_table_line
            prev_table_line = True
            if new_table:
                segment = bool(SEGMENT_RE.search(" ".join(context)))
            if segment:
                continue
            if set("".join(cells)) <= set("-: "):
                continue
            cols = _header_years(cells)
            if cols:
                header, inherited = (cols, cells[0], len(cells)), 0
                continue
            if new_table and first_table and header is None and carry and carry[2] == len(cells):
                header, inherited = carry, 1
            if header is None:
                continue
            ind = indicator_of(cells[0])
            if not ind:
                continue
            kind = INDICATORS[ind][0]
            unit = _unit(kind, header[1], " ".join(context), p["text"], doc_unit)
            for i, y in header[0].items():
                if i < len(cells) and (v := parse_num(cells[i], style)) is not None:
                    if kind == "pct" and abs(v) > 1000:  # a nominal row with a ratio's name ("CASA" in Rp)
                        continue
                    if ind in STOCKS and v < 0:
                        continue
                    out.append({"bank": bank, "report_year": report_year, "doc": doc, "page": p["page"],
                                "indicator": ind, "label": cells[0], "year": y, "value": v, "raw": cells[i],
                                "unit": unit, "inherited": inherited})
        carry = header
    return out


def build(path=DB_PATH) -> int:
    rows = [r for d in sorted(PROCESSED_DIR.glob("*.jsonl")) for r in extract_doc(d.stem)]
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE facts (bank TEXT, report_year INT, doc TEXT, page INT, indicator TEXT, label TEXT,
                   year INT, value REAL, raw TEXT, unit TEXT, inherited INT)""")
    con.executemany("INSERT INTO facts VALUES (:bank,:report_year,:doc,:page,:indicator,:label,:year,:value,:raw,"
                    ":unit,:inherited)", rows)
    con.execute("CREATE INDEX ix ON facts (bank, indicator, year)")
    con.commit()
    con.close()
    lookup_rows.cache_clear()
    return len(rows)


@lru_cache
def lookup_rows(bank: str, indicator: str, year: int) -> tuple[dict, ...]:
    if not DB_PATH.exists():
        return ()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM facts WHERE bank=? AND indicator=? AND year=?", (bank, indicator, year)).fetchall()
    con.close()
    return tuple(dict(r) for r in rows)


def lookup(bank: str, indicator: str, year: int, report_year: int | None = None) -> dict | None:
    """Best fact for (bank, indicator, year), or None.

    Report: the named one, else the latest report holding the year (prior-year columns are restated).
    Within a report: the value printed on the most pages wins (headline figures repeat across the highlights,
    MD&A and financial statements; segment or bank-only rows do not), ties go to the earliest page.
    `alternatives` lists the other values seen, so a caller can tell a clear hit from a contested one."""
    rows = [r for r in lookup_rows(bank, indicator, year) if not r["inherited"]] or list(lookup_rows(bank, indicator, year))
    if not rows:
        return None
    ry = report_year if report_year in {r["report_year"] for r in rows} else max(r["report_year"] for r in rows)
    rows = [r for r in rows if r["report_year"] == ry]
    pages = Counter()
    for r in {(r["value"], r["page"]): r for r in rows}.values():
        pages[r["value"]] += 1
    best = max(pages, key=lambda v: (pages[v], -min(r["page"] for r in rows if r["value"] == v)))
    hit = min((r for r in rows if r["value"] == best), key=lambda r: r["page"])
    return {**hit, "support": pages[best], "alternatives": sorted(v for v in pages if v != best)}


# question wording -> indicator (the label regexes above are anchored on table cells, not on questions)
Q_INDICATORS: dict[str, str] = {
    "npl_net": r"\bnpl\b[^.?]*\b(net|neto|nett)\b|kredit bermasalah[^.?]*\bneto\b",
    "npl_gross": r"\bnpl\b|non performing loan|kredit bermasalah",
    "cet1": r"common equity tier|\bcet\s*1\b",
    "tier1": r"tier\s*1|modal inti",
    "car": r"\bcar\b|\bkpmm\b|kecukupan modal|kewajiban penyediaan modal",
    "ldr": r"\bldr\b|loan to deposit",
    "nim": r"\bnim\b|net interest margin|marjin bunga bersih",
    "bopo": r"\bbopo\b|beban operasional terhadap",
    "casa": r"\bcasa\b",
    "roa": r"\broa\b|return on asset|imbal hasil aset",
    "roe": r"\broe\b|return on equity|imbal hasil ekuitas",
    "total_aset": r"\b(total|jumlah) aset\b|\baset total\b",
    "laba": r"\blaba (bersih|tahun berjalan)\b|\bnet (income|profit)\b",
    "ekuitas": r"\b(total|jumlah) ekuitas\b",
}
# more specific indicators that also match a broader pattern ("NPL net" also matches npl_gross, "CAR Tier 1" car)
Q_SHADOWS = {"npl_net": "npl_gross", "cet1": "tier1", "tier1": "car"}
# wordings the table cannot answer: chart readings, quarters, the parent-attributable share of profit
Q_SKIP = re.compile(r"grafik|kuartal|triwulan|semester|atribusi|diatribusikan|segmen|anak perusahaan", re.I)
UNIT_TXT = {"jt": "juta Rupiah", "mi": "miliar Rupiah", "tn": "triliun Rupiah"}
BANK_NAME = {"bri": "BRI", "mandiri": "Bank Mandiri", "btn": "BTN", "bca": "BCA", "bni": "BNI"}


def parse_step(q: str) -> tuple[str, str, int, int | None] | None:
    """(bank, indicator, year, report_year) when a one-figure question names exactly one of each; else None."""
    from telaah.filters import BANKS, SOURCE_RE

    if Q_SKIP.search(q):
        return None
    ql = q.lower()
    banks = [b for b, pat in BANKS.items() if re.search(pat, ql)]
    inds = {i for i, pat in Q_INDICATORS.items() if re.search(pat, ql)}
    inds -= {Q_SHADOWS[i] for i in inds if i in Q_SHADOWS}
    src = SOURCE_RE.search(ql)
    report_year = int(src.group(1)) if src else None
    years = set(map(int, re.findall(r"\b(20\d\d)\b", SOURCE_RE.sub(" ", ql))))
    if not years and report_year:
        years = {report_year}
    if len(banks) != 1 or len(inds) != 1 or len(years) != 1:
        return None
    return banks[0], inds.pop(), years.pop(), report_year


def shown(hit: dict) -> str:
    """The value in Indonesian notation (BNI prints 1,362,055 and 2.1)."""
    raw = hit["raw"].strip()
    if re.search(r"\d\.\d{1,2}%?$", raw) or re.search(r"\d,\d{3}", raw):
        raw = raw.replace(",", "_").replace(".", ",").replace("_", ".")
    if hit["unit"] == "pct":
        return raw.rstrip("%").strip() + "%"
    return f"Rp{raw} {UNIT_TXT.get(hit['unit'], '')}".strip()


def answer_step(q: str) -> dict | None:
    """One plan step answered from the table, in the shape of `answer.ask` (cited sentence + the cited page as
    context, so the agent's citation check reads the same page); None -> the caller uses RAG."""
    parsed = parse_step(q)
    if not parsed:
        return None
    bank, ind, year, report_year = parsed
    hit = lookup(bank, ind, year, report_year)
    if not hit:
        return None
    from telaah.tools import read_page_text

    sentence = f"{hit['label']} {BANK_NAME[bank]} tahun {year}: {shown(hit)} [{hit['doc']} p.{hit['page']}]."
    return {"answer": sentence, "citations": [(hit["doc"], hit["page"])], "retrieved": [(hit["doc"], hit["page"])],
            "context": f"[{hit['doc']} p.{hit['page']}]\n{read_page_text(hit['doc'], hit['page'])}", "refused": False,
            "fact": {k: hit[k] for k in ("doc", "page", "label", "year", "value", "raw", "unit", "support")}}


if __name__ == "__main__":
    print(build(), "facts ->", DB_PATH)
