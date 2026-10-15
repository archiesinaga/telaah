"""Agent tools as plain functions; `mcp_server.py` exposes them over MCP."""
import ast
import json
import operator
import re
from functools import lru_cache

from telaah.config import PROCESSED_DIR

NUM_RE = re.compile(r"\d[\d.,]*\d|\d")
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
MAX_POW = 100


@lru_cache(maxsize=None)
def _pages(doc_id: str) -> dict[int, str]:
    path = PROCESSED_DIR / f"{doc_id}.jsonl"
    if not path.exists():
        raise KeyError(f"unknown doc_id: {doc_id}")
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["page"]: r["text"] for r in rows}


def list_documents() -> list[str]:
    return sorted(p.stem for p in PROCESSED_DIR.glob("*.jsonl"))


def search_documents(query: str, k: int = 5) -> list[dict]:
    """Top-k pages for a query: doc_id, page, and a text snippet."""
    from telaah.retrieve import retrieve

    return [
        {"doc_id": c["doc_id"], "page": c["page"], "snippet": " ".join(c["text"].split())[:300]}
        for c in retrieve(query, k=k)
    ]


def read_page_text(doc_id: str, page: int) -> str:
    """Full text of one page; raises KeyError for unknown doc/page (empty pages are not indexed)."""
    pages = _pages(doc_id)
    if page not in pages:
        raise KeyError(f"{doc_id} has no text for page {page}")
    return pages[page]


def read_page_image(question: str, doc_id: str, page: int) -> str:
    """Vision-model reading of a page image, conditioned on the question (cached on disk)."""
    from telaah import vision

    return vision.read_page(question, doc_id, page)


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(b) > MAX_POW:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](a, b)
    raise ValueError("only numbers and + - * / ** % // are allowed")


def calculate(expression: str) -> float:
    """Evaluate an arithmetic expression without exec/eval (AST whitelist). Use '.' as decimal point."""
    return _eval(ast.parse(expression.strip(), mode="eval"))


def number_variants(token: str) -> set[str]:
    """Plain-number readings of a token written with Indonesian (1.234,5) or English (1,234.5) separators."""
    out = set()
    for thousands, decimal in ((".", ","), (",", ".")):
        t = token.replace(thousands, "")
        if token.count(decimal) <= 1:
            t = t.replace(decimal, ".")
            out.add(t.rstrip("0").rstrip(".") if "." in t else t)
    return out


def numbers_in(text: str) -> set[str]:
    return {v for tok in NUM_RE.findall(text) for v in number_variants(tok)}


def check_citation(doc_id: str, page: int, claim: str) -> dict:
    """Does the cited page exist, and does every number in the claim occur on it?"""
    try:
        text = read_page_text(doc_id, page)
    except KeyError as e:
        return {"supported": False, "page_found": False, "missing_numbers": [], "reason": str(e)}
    page_nums = numbers_in(text)
    missing = [
        tok for tok in NUM_RE.findall(claim)
        if not (number_variants(tok) & page_nums)
    ]
    return {
        "supported": not missing,
        "page_found": True,
        "missing_numbers": missing,
        "reason": "all numbers found on page" if not missing else "numbers not on cited page",
    }
