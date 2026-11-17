import json
import re
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path


def load_extra_gold(path: Path, questions: list[dict]) -> dict[str, list[tuple[str, int]]]:
    """Extra gold pages (eval/bench/extra_gold.py): {id: {"q": question text, "pages": [[doc, page], ...]}}.
    The text is stored because a rebuilt question file renumbers ids, and id-only keys then silently put pages on
    neighbour questions (found 2026-11-17: 307 shifted dev ids). Raises if any entry's text does not match the
    question with that id; `questions` must be the whole file, not a --types/--ids subset."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    text = {q["id"]: q["question"] for q in questions}
    bad = [i for i, e in raw.items() if not isinstance(e, dict) or text.get(i) != e.get("q")]
    if bad:
        raise ValueError(f"{path.name}: {len(bad)} entries do not match their question id (e.g. {bad[:5]}); "
                         f"re-key them with: python eval/bench/extra_gold.py --remap")
    return {i: [(d, int(p)) for d, p in e["pages"]] for i, e in raw.items()}


def remap_extra_gold(raw: dict, questions: list[dict]) -> tuple[dict, list[str]]:
    """Re-key extra gold entries by their stored question text. Returns (new file content, dropped old ids):
    entries whose question is no longer in the file are dropped."""
    by_text = {q["question"]: q["id"] for q in questions}
    out, dropped = {}, []
    for i, e in raw.items():
        new_id = by_text.get(e.get("q")) if isinstance(e, dict) else None
        if new_id is None:
            dropped.append(i)
        else:
            out[new_id] = e
    return dict(sorted(out.items())), dropped


def recall_at_k(retrieved: list[tuple[str, int]], gold: list[tuple[str, int]], k: int = 5) -> float:
    return float(any(g in retrieved[:k] for g in gold)) if gold else 1.0


def recall_at_k_groups(groups: list[list[tuple[str, int]]], gold: list[tuple[str, int]], k: int = 5) -> float:
    """Recall when the answer read several retrievals (agent steps, entities): each one's own top k counts.
    Scoring the first k of all of them combined only ever looked at step 1."""
    return max((recall_at_k(g, gold, k) for g in groups), default=recall_at_k([], gold, k))


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
