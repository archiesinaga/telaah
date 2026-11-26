"""Shared helpers for the benchmark tools (see eval/BENCHMARK.md)."""
import hashlib
import json
import re
from collections import defaultdict
from functools import cache
from pathlib import Path

HERE = Path(__file__).parent
EVAL = HERE.parent
ROOT = EVAL.parent
PROCESSED = ROOT / "data" / "processed"
SEED = 20261021
TEST_SHARE = 0.25
REPORT_RE = re.compile(r"^(bri|bca|bni|btn|mandiri)_(2024|2025)$")
SKIP_DOCS = {"bca_2024"}  # only 12 pages parsed: the system cannot answer from it
BANK = {"bri": "BRI", "mandiri": "Bank Mandiri", "bni": "BNI", "btn": "BTN", "bca": "BCA"}

TYPES = ["text_fact", "table_lookup", "chart", "calculation", "cross_doc", "regulation", "unanswerable"]
# (total, dev incl. seed, test) per type, from BENCHMARK.md
QUOTA = {"text_fact": (120, 90, 30), "table_lookup": (120, 90, 30), "chart": (90, 67, 23),
         "calculation": (90, 68, 22), "cross_doc": (78, 68, 10), "regulation": (60, 45, 15),
         "unanswerable": (30, 22, 8)}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


@cache
def pages(doc: str) -> dict[int, str]:
    """Parsed text of each page (1-based), chunks joined."""
    out: dict[int, str] = defaultdict(str)
    for r in read_jsonl(PROCESSED / f"{doc}.jsonl"):
        out[int(r["page"])] += r["text"] + "\n"
    return dict(out)


def docs() -> list[str]:
    return sorted(p.stem for p in PROCESSED.glob("*.jsonl"))


def is_report(doc: str) -> bool:
    return bool(REPORT_RE.match(doc)) and doc not in SKIP_DOCS


def is_regulation(doc: str) -> bool:
    return doc.startswith(("ojk_", "bi_"))


@cache
def tuned_pages() -> frozenset[tuple[str, int]]:
    """Gold pages of the seed questions, agent tasks and held-out sets: never test pages."""
    seen = set()
    for name in ["seed_questions.jsonl", "agent_tasks.jsonl", "heldout_tasks.jsonl", "heldout2_tasks.jsonl"]:
        for row in read_jsonl(EVAL / name):
            seen |= {(d, int(p)) for d, p in row.get("gold_pages", [])}
            seen |= {(f["doc"], int(f["page"])) for f in row.get("gold_facts", []) if "doc" in f}
    return frozenset(seen)


def page_split(doc: str, page: int) -> str:
    """Fixed per page: a hash share goes to test, pages the system was tuned on never do."""
    h = hashlib.sha256(f"{SEED}:{doc}:{page}".encode()).digest()
    test = int.from_bytes(h[:8], "big") / 2**64 < TEST_SHARE and (doc, page) not in tuned_pages()
    return "test" if test else "dev"


def split_of(*doc_pages: tuple[str, int]) -> str:
    """Split of a question: its pages' split, or 'mixed' (not used) when they disagree."""
    splits = {page_split(d, p) for d, p in doc_pages}
    return splits.pop() if len(splits) == 1 else "mixed"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


ARCHIVE_V1 = HERE / "archive_test_v1"


def referenced_pages(obj, out: set) -> set:
    """Every (doc, page) anywhere in a JSON value: [doc, page] pairs and {"doc", "page"} dicts. Never printed."""
    known = set(docs())
    if isinstance(obj, dict):
        if isinstance(obj.get("doc"), str) and str(obj.get("page", "")).isdigit():
            out.add((obj["doc"], int(obj["page"])))
        for v in obj.values():
            referenced_pages(v, out)
    elif isinstance(obj, list):
        if len(obj) == 2 and isinstance(obj[0], str) and obj[0] in known and str(obj[1]).isdigit():
            out.add((obj[0], int(obj[1])))
        else:
            for v in obj:
                referenced_pages(v, out)
    return out


def test_v1_pages() -> set:
    """Pages a Claude session may have seen through test v1 (questions, golds, extra gold pages)."""
    seen: set = set()
    for path in sorted(ARCHIVE_V1.glob("*.jsonl")):
        for row in read_jsonl(path):
            referenced_pages(row, seen)
    return seen
