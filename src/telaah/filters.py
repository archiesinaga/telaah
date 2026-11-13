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
REG_PREFIX = {"pojk": "ojk_pojk", "padg": "bi_padg", "pbi": "bi_pbi", "seojk": "ojk_seojk",
              # spelled-out names (bd0346 "Peraturan Bank Indonesia Nomor 6", bd0370 "Surat Edaran Otoritas ...")
              "peraturan otoritas jasa keuangan": "ojk_pojk", "peraturan anggota dewan gubernur": "bi_padg",
              "peraturan bank indonesia": "bi_pbi", "surat edaran otoritas jasa keuangan": "ojk_seojk"}
# "PADG No. 27 Tahun 2025", "PADG Bank Indonesia No. 20", "Peraturan Anggota Dewan Gubernur (PADG) Nomor 26" also name
# one document: before these forms were read, 21 dev questions searched the whole corpus (8 with recall 0)
REG_RE = re.compile(
    r"\b(pojk|padg|pbi|seojk|peraturan\s+otoritas\s+jasa\s+keuangan|peraturan\s+anggota\s+dewan\s+gubernur"
    r"|peraturan\s+bank\s+indonesia|surat\s+edaran\s+otoritas\s+jasa\s+keuangan)"
    r"(?:\s*\([a-z]+\))?(?:\s+bank\s+indonesia)?\s*(?:(?:nomor|no\.?)\s*)?(\d+)(?:/[a-z]+\.\d+)?(?:/(\d{4}))?"
    r"(?:\s*tahun\s*(\d{4}))?",
    re.I,
)


def reg_kind(m: re.Match) -> str:
    return REG_PREFIX[" ".join(m.group(1).lower().split())]
YEAR_RE = re.compile(r"\b(20\d\d)\b")
# "menurut/gunakan Laporan Tahunan 2025" names the source report: it beats the other years in the question
# (a 2021-2025 trend question must read 2021-2024 from the 2025 report, whose prior-year columns are restated)
SOURCE_RE = re.compile(r"laporan tahunan\s*(20\d\d)")


@lru_cache
def doc_ids() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in PROCESSED_DIR.glob("*.jsonl")))


def named_prefixes(question: str) -> list[str]:
    """Doc-id prefixes of the banks and regulations a question names, whether or not they are in the corpus:
    'POJK Nomor 12 Tahun 2024' -> 'ojk_pojk_12_2024', 'BRI' -> 'bri_'."""
    out = []
    for m in REG_RE.finditer(question):
        num, year = m.group(2), m.group(3) or m.group(4)
        out.append(f"{reg_kind(m)}_{num}_" + (year or ""))
    q = question.lower()
    out += [bank + "_" for bank, pat in BANKS.items() if re.search(pat, q)]
    return out


def detect_groups(question: str) -> list[list[str]]:
    """One group of doc_ids per entity named in the question; [] means no filter."""
    q = question.lower()
    docs = doc_ids()
    groups: list[list[str]] = []

    for m in REG_RE.finditer(question):
        num = m.group(2)
        year = m.group(3) or m.group(4)
        pre = f"{reg_kind(m)}_{num}_" + (year or "")
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
