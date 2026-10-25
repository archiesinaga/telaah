import re
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation


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


_UNIT = re.compile(r"\s*(ribu|juta|miliar|milyar|triliun|thousand|million|billion|trillion)\b", re.I)
_EXP = {"ribu": 3, "thousand": 3, "juta": 6, "million": 6, "miliar": 9, "milyar": 9, "billion": 9,
        "triliun": 12, "trillion": 12}


def _tokens(s: str) -> list[tuple[str, int | None]]:
    """(normalized number, power of ten of the unit word right after it, or None) for each number in s."""
    out = []
    for m in _TOKEN.finditer(s):
        u = _UNIT.match(s, m.end())
        out.append((_norm(m.group()), _EXP[u.group(1).lower()] if u else None))
    return out


def _converted(gold: str, gold_exp: int, pred: list[tuple[str, int | None]]) -> bool:
    """A pred number written in ANOTHER unit word equals gold once converted and rounded or truncated to gold's
    last printed digit: 'Rp328.309.681 juta' vs 'Rp328,30 triliun', 'Rp154.987.000 juta' vs 'Rp155 triliun'.
    Same-unit and unitless numbers never reach this (they must match exactly)."""
    try:
        g = Decimal(gold)
    except InvalidOperation:
        return False
    if not g.is_finite():
        return False
    step = Decimal(1).scaleb(min(0, int(g.as_tuple().exponent)))
    for p, exp in pred:
        if exp is None or exp == gold_exp:
            continue
        try:
            v = Decimal(p).scaleb(exp - gold_exp)
        except InvalidOperation:
            continue
        if g in (v.quantize(step, ROUND_HALF_UP), v.quantize(step, ROUND_DOWN)):
            return True
    return False


def numeric_match(pred: str, gold: str) -> bool:
    g = _tokens(gold)
    p = _tokens(pred)
    plain = {n for n, _ in p}
    return bool(g) and all(n in plain or (exp is not None and _converted(n, exp, p)) for n, exp in g)


def refusal_correct(refused: bool, answerable: bool) -> float:
    return float(refused != answerable)
