import re


def recall_at_k(retrieved: list[tuple[str, int]], gold: list[tuple[str, int]], k: int = 5) -> float:
    return float(any(g in retrieved[:k] for g in gold)) if gold else 1.0


def citation_accuracy(cited: list[tuple[str, int]], gold: list[tuple[str, int]]) -> float:
    if not gold:
        return 1.0 if not cited else 0.0
    return float(bool(cited) and all(c in gold for c in cited))


_TOKEN = re.compile(r"-?\d[\d.,]*\d|-?\d")


def _norm(tok: str) -> str:
    """One number token, Indonesian or English: '1.234,56' -> '1234.56', '2,416,792' -> '2416792', '14,76' -> '14.76',
    '1.227' -> '1227' (a group of exactly three digits after a separator is thousands)."""
    if "." in tok and "," in tok:
        dec = "," if tok.rfind(",") > tok.rfind(".") else "."
        thou = "." if dec == "," else ","
        return tok.replace(thou, "").replace(dec, ".")
    sep = "." if "." in tok else "," if "," in tok else None
    if sep is None:
        return tok
    if re.fullmatch(rf"-?\d{{1,3}}(?:\{sep}\d{{3}})+", tok):
        return tok.replace(sep, "")
    return tok.replace(sep, ".") if tok.count(sep) == 1 else tok.replace(sep, "")


def _nums(s: str) -> list[str]:
    return [_norm(t) for t in _TOKEN.findall(s)]


def numeric_match(pred: str, gold: str) -> bool:
    g = _nums(gold)
    return bool(g) and all(x in _nums(pred) for x in g)


def refusal_correct(refused: bool, answerable: bool) -> float:
    return float(refused != answerable)
