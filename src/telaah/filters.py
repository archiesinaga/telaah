"""Rule-based detection of which documents a question is about."""
import re
from functools import lru_cache

from telaah.config import PROCESSED_DIR

BANKS = {
    "bri": r"\bbri\b|bank rakyat indonesia",
    "mandiri": r"mandiri",
    "bni": r"\bbni\b|negara indonesia",
    "bca": r"\bbca\b|central asia",
    "btn": r"\bbtn\b|tabungan negara",
}
REG_PREFIX = {"pojk": "ojk_pojk", "padg": "bi_padg", "pbi": "bi_pbi", "seojk": "ojk_seojk"}
REG_RE = re.compile(
    r"\b(pojk|padg|pbi|seojk)\s*(?:nomor\s*)?(\d+)(?:/[a-z]+\.\d+)?(?:/(\d{4}))?(?:\s*tahun\s*(\d{4}))?",
    re.I,
)
YEAR_RE = re.compile(r"\b(20\d\d)\b")
# "menurut/gunakan Laporan Tahunan 2025" names the source report: it beats the other years in the question
# (a 2021-2025 trend question must read 2021-2024 from the 2025 report, whose prior-year columns are restated)
SOURCE_RE = re.compile(r"laporan tahunan\s*(20\d\d)")


@lru_cache
def doc_ids() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in PROCESSED_DIR.glob("*.jsonl")))


def detect_groups(question: str) -> list[list[str]]:
    """One group of doc_ids per entity named in the question; [] means no filter."""
    q = question.lower()
    docs = doc_ids()
    groups: list[list[str]] = []

    for m in REG_RE.finditer(question):
        kind, num = m.group(1).lower(), m.group(2)
        year = m.group(3) or m.group(4)
        pre = f"{REG_PREFIX[kind]}_{num}_" + (year or "")
        ids = [d for d in docs if d.startswith(pre)]
        if ids and ids not in groups:
            groups.append(ids)

    years = set(YEAR_RE.findall(q))
    source = set(SOURCE_RE.findall(q))
    for bank, pat in BANKS.items():
        if re.search(pat, q):
            ids = [d for d in docs if d.startswith(bank + "_")]
            # a year written right after the bank name ("BTN 2025") wins over other years in the question
            named = set(re.findall(r"(?:" + pat + r")\s*(20[0-9][0-9])", q))
            by_year = [d for d in ids if d.rsplit("_", 1)[-1] in (source or named or years)]
            groups.append(by_year or ids)
    return groups
