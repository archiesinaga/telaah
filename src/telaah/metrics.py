import re


def recall_at_k(retrieved: list[tuple[str, int]], gold: list[tuple[str, int]], k: int = 5) -> float:
    return float(any(g in retrieved[:k] for g in gold)) if gold else 1.0


def citation_accuracy(cited: list[tuple[str, int]], gold: list[tuple[str, int]]) -> float:
    if not gold:
        return 1.0 if not cited else 0.0
    return float(bool(cited) and all(c in gold for c in cited))


def _nums(s: str) -> list[str]:
    # Indonesian format uses "." for thousands and "," for decimals.
    if re.search(r"\d\.\d{3}", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return re.findall(r"-?\d+(?:\.\d+)?", s)


def numeric_match(pred: str, gold: str) -> bool:
    g = _nums(gold)
    return bool(g) and all(x in _nums(pred) for x in g)


def refusal_correct(refused: bool, answerable: bool) -> float:
    return float(refused != answerable)
