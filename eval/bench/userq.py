"""Entries the user writes (or imports) by hand: checked against the corpus, gold computed in Python.

Shared by review_app.py (the "Cross-doc (write your own)" tab) and import_cross_doc.py (CSV). Never prints questions.
"""
import re
from functools import cache

from common import V3, norm, page_split, pages, test_v1_pages
from gold import compute, fmt_id

UNITS = ["%", "triliun Rupiah", "miliar Rupiah", "juta Rupiah"]


def parse_pages(s: str) -> list[list]:
    out = []
    for part in re.split(r"[;,\n]", s):
        if part.strip():
            doc, page = part.strip().rsplit(":", 1)
            out.append([doc.strip(), int(page)])
    return out


def parse_id_number(s: str) -> float:
    """Indonesian number as printed: '1.234,56' -> 1234.56, '3,29' -> 3.29."""
    t = s.strip().replace("%", "").replace(" ", "")
    if not re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d+)?|-?\d+(,\d+)?", t):
        raise ValueError(f"cannot read the number '{s}' (use the printed form, e.g. 1.234,56 or 3,29)")
    return float(t.replace(".", "").replace(",", "."))


@cache
def _v3_excluded() -> frozenset:
    from sample_pages import v3_excluded
    return frozenset(v3_excluded())


def check_test_page(split: str, ref: str, printed: str) -> tuple[str, int]:
    """'doc:page' must exist, belong to `split`, not be a test-v1 page, and print the figure."""
    try:
        doc, page = parse_pages(ref)[0]
    except (ValueError, IndexError):
        raise ValueError(f"cannot read the page reference '{ref}' (use doc:page, e.g. bri_2025:145)") from None
    text = pages(doc).get(page)
    if text is None:
        raise ValueError(f"{doc}:{page} does not exist in the corpus")
    if split == V3:  # test v3: any hash share, but never a used page or its neighbour (BENCHMARK.md 2026-11-27)
        if (doc, page) in _v3_excluded():
            raise ValueError(f"{doc}:{page} was used before (or is next to a used page): pick another page")
    elif page_split(doc, page) != split:
        raise ValueError(f"{doc}:{page} is a {page_split(doc, page)} page, not {split}: pick another page")
    if split == "test" and (doc, page) in test_v1_pages():
        raise ValueError(f"{doc}:{page} was seen through the retired test v1: pick another page")
    if norm(printed) not in norm(text.replace("|", " ")):
        raise ValueError(f"'{printed}' is not printed on {doc}:{page} (check the number and the page)")
    return doc, page


def cross_doc_row(split, num, question, ref_a, ref_b, bank_a, bank_b, label, val_a, val_b, unit) -> dict:
    """One checked cross_doc row for user_{split}.jsonl; raises ValueError with the reason when it is not valid."""
    question, bank_a, bank_b, label = (x.strip() for x in (question, bank_a, bank_b, label))
    val_a, val_b = val_a.strip(), val_b.strip()
    if not question or not bank_a or not bank_b or not label:
        raise ValueError("Fill in the question, both bank names and the indicator label.")
    if unit not in UNITS:
        raise ValueError(f"unit must be one of {UNITS}")
    da, pa = check_test_page(split, ref_a, val_a)
    db, pb = check_test_page(split, ref_b, val_b)
    if da.split("_")[0] == db.split("_")[0]:
        raise ValueError("Use two different banks.")
    if da.split("_")[1] != db.split("_")[1]:
        raise ValueError("Use the same report year for both banks.")
    if "bca_2024" in (da, db):
        raise ValueError("bca_2024 is not usable (only 12 pages parsed).")
    va, vb = parse_id_number(val_a), parse_id_number(val_b)
    if va == vb:
        raise ValueError("The two values are equal: no higher bank, no difference.")
    figures = [{"bank": bank_a, "label": label, "value": val_a, "value_float": va, "unit": unit, "page": "A"},
               {"bank": bank_b, "label": label, "value": val_b, "value_float": vb, "unit": unit, "page": "B"}]
    _, gap = compute(figures, "difference")
    hi = bank_a if va > vb else bank_b
    show_v = (lambda v: fmt_id(v) + "%") if unit == "%" else (lambda v: f"{fmt_id(v)} {unit}")
    gap_unit = "poin persentase" if unit == "%" else unit
    answer = f"{hi} lebih tinggi: {label} {bank_a} {show_v(va)} vs {bank_b} {show_v(vb)} (selisih {gap} {gap_unit})."
    return {"cid": f"u-{split}-{num:03d}", "split": split, "type": "cross_doc", "question": question,
            "gold_answer": answer, "gold_pages": [[da, pa], [db, pb]], "answerable": True, "numeric": True,
            "figures": figures, "op": "difference", "computed": gap,
            **({"extra": {"in_facts_table": _in_facts(label)}} if split == V3 else {})}


def _in_facts(label: str) -> bool:
    """Is the indicator one the facts table answers (cross_doc reported per group, test v3)."""
    from telaah.facts import Q_INDICATORS
    return any(re.search(pat, label.lower()) for pat in Q_INDICATORS.values())
