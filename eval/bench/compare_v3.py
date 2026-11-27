"""Test v3 A/B (BENCHMARK.md Status 2026-11-27): frozen code (test-v2-freeze) vs HEAD on the same test3 questions.

    .venv/Scripts/python eval/bench/compare_v3.py eval/runs/<frozen run>.json eval/runs/<HEAD run>.json

Primary (fixed before the runs): correct_numeric on calculation and on cross_doc, McNemar exact test (two-sided) on the
discordant pairs. Secondary: overall and per type means of numeric, recall@5, citation, refusal; cross_doc split by
`extra.in_facts_table`. Prints counts and means only, never ids, questions or answers (rule 2), so it is safe on a
blind split. Both runs must be scored by the same scorer (rescore the frozen run with eval/rescore_numeric.py first).
"""
import json
import sys
from math import comb

from common import HERE, V3, read_jsonl

METRICS = ["correct_numeric", "recall@5", "citation_acc", "refusal_acc"]
PRIMARY = ["calculation", "cross_doc"]


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p: binomial(b + c, 0.5) tail, doubled, capped at 1."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def mean(rows: list[dict], key: str) -> str:
    v = [r[key] for r in rows if r.get(key) is not None]
    return f"{sum(v) / len(v):.3f}" if v else "  -  "


def main(frozen_path: str, head_path: str) -> None:
    qs = {q["id"]: q for q in read_jsonl(HERE / f"{V3}.jsonl")}
    runs = [{r["id"]: r for r in json.load(open(p, encoding="utf-8"))["results"]} for p in (frozen_path, head_path)]
    ids = sorted(set(qs) & set(runs[0]) & set(runs[1]))
    missing = [len(set(qs) - set(r)) for r in runs]
    print(f"test3 questions {len(qs)}, in both runs {len(ids)}, missing in frozen/HEAD {missing[0]}/{missing[1]}")
    groups = {"ALL": ids}
    for t in sorted({qs[i]["type"] for i in ids}):
        groups[t] = [i for i in ids if qs[i]["type"] == t]
    xd = groups.get("cross_doc", [])
    groups["cross_doc | facts-table indicator"] = [i for i in xd if qs[i].get("extra", {}).get("in_facts_table")]
    groups["cross_doc | other indicator"] = [i for i in xd if not qs[i].get("extra", {}).get("in_facts_table")]
    print(f"\n{'group':36s} {'n':>4s}  " + "  ".join(f"{m[:9]:>9s} fz/HEAD" for m in METRICS))
    for g, gi in groups.items():
        cells = [f"{mean([runs[0][i] for i in gi], m)}/{mean([runs[1][i] for i in gi], m)}" for m in METRICS]
        print(f"{g:36s} {len(gi):4d}  " + "  ".join(f"{c:>17s}" for c in cells))
    print("\nnumeric flips, frozen -> HEAD (b = right->wrong, c = wrong->right), McNemar exact two-sided:")
    for g in PRIMARY + ["ALL", "cross_doc | facts-table indicator", "cross_doc | other indicator"]:
        gi = groups.get(g, [])
        pairs = [(runs[0][i]["correct_numeric"], runs[1][i]["correct_numeric"]) for i in gi
                 if runs[0][i].get("correct_numeric") is not None and runs[1][i].get("correct_numeric") is not None]
        b = sum(1 for f, h in pairs if f == 1 and h == 0)
        c = sum(1 for f, h in pairs if f == 0 and h == 1)
        tag = "PRIMARY" if g in PRIMARY else "secondary"
        print(f"  [{tag}] {g:34s} n {len(pairs):3d}  b {b:3d}  c {c:3d}  p {mcnemar_exact(b, c):.4f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
