"""Turn eval run JSONs into markdown tables (overall + per question type).

Usage: python eval/summarize.py eval/runs/A.json [eval/runs/B.json ...]
With several runs, prints one overall table (one row per run) and a per-type table for each.
"""
import collections
import json
import sys
from pathlib import Path

KEYS = ["recall@5", "citation_acc", "refusal_acc", "correct_numeric", "correct_judge", "faithful", "latency_s"]


def _mean(values: list) -> str:
    v = [x for x in values if x is not None]
    return f"{sum(v) / len(v):.2f}" if v else "-"


def overall_table(runs: list[tuple[str, dict]]) -> str:
    head = "| run | " + " | ".join(KEYS) + " |\n|---|" + "---|" * len(KEYS)
    rows = [f"| {name} | " + " | ".join(_mean([d['summary'][k]]) for k in KEYS) + " |" for name, d in runs]
    return "\n".join([head, *rows])


def per_type_table(d: dict) -> str:
    groups = collections.defaultdict(list)
    for r in d["results"]:
        groups[r["type"]].append(r)
    head = "| type | n | " + " | ".join(KEYS) + " |\n|---|---|" + "---|" * len(KEYS)
    rows = [
        f"| {t} | {len(rs)} | " + " | ".join(_mean([r[k] for r in rs]) for k in KEYS) + " |"
        for t, rs in sorted(groups.items())
    ]
    return "\n".join([head, *rows])


def main(paths: list[str]) -> None:
    runs = [(Path(p).stem, json.loads(Path(p).read_text(encoding="utf-8"))) for p in paths]
    print(overall_table(runs))
    for name, d in runs:
        print(f"\n{name} ({d['config']['llm']})\n")
        print(per_type_table(d))


if __name__ == "__main__":
    main(sys.argv[1:])
