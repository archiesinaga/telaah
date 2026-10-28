"""Sample the pages Gemini drafts SFT examples from -> sft/pages.jsonl (see sft/DESIGN.md, step 1).

Never a benchmark page: test-split pages (by the page hash, so the test files are never opened), tuned pages
(seed, agent tasks, held-out sets), dev gold and extra gold pages, and every page drafted for the benchmark.
Deterministic; rerunning rewrites the same file.

    .venv/Scripts/python sft/page_pool.py
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "eval" / "bench"))
from common import HERE as BENCH, SEED, page_split, read_jsonl, tuned_pages  # noqa: E402
from sample_pages import kind_pools, round_robin  # noqa: E402

OUT = HERE / "pages.jsonl"
# ~800 pages x 3 drafts ~ 2,400 candidates -> ~2,200 examples after filtering (DESIGN.md)
# calculation pools (tables with 2+ years) are drafted as reading questions: the look-alike-year case
COUNT = {"text_fact": 160, "table_lookup": 200, "calculation": 200, "chart": 140, "regulation": 100}


def excluded() -> tuple[set, Counter]:
    why: Counter = Counter()
    out: set = set()

    def add(dps, reason: str) -> None:
        for d, p in dps:
            dp = (d, int(p))
            if dp not in out:
                why[reason] += 1
                out.add(dp)

    add(tuned_pages(), "tuned (seed, agent, held-out)")
    add((dp for q in read_jsonl(BENCH / "dev.jsonl") for dp in q["gold_pages"]), "dev gold")
    extra = json.loads((BENCH / "extra_gold_dev.json").read_text(encoding="utf-8"))
    add((dp for v in extra.values() for dp in v), "extra gold")
    for name in ("pages.jsonl", "pages2.jsonl"):
        add((dp for r in read_jsonl(BENCH / name) for dp in r["pages"]), "benchmark drafted")
    return out, why


def main() -> None:
    rng = random.Random(SEED + 100)
    skip, why = excluded()
    pools = kind_pools()
    used: set = set()
    rows, sizes = [], {}
    for kind, pool in pools.items():
        if kind not in COUNT:
            continue
        test = sum(page_split(d, p) == "test" for d, p in pool)
        ok = [dp for dp in pool if dp not in skip and page_split(*dp) == "dev"]
        sizes[kind] = (len(pool), test, len(pool) - test - len(ok), len(ok))
        rows += [{"kind": kind, "pages": [list(dp)]} for dp in round_robin(ok, COUNT[kind], used, rng)]
    with open(OUT, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(json.dumps({"id": f"s{i:04d}", **r}, ensure_ascii=False) + "\n")
    print("excluded pages by reason:", dict(why))
    print("pool per kind (all, test split, benchmark-excluded, eligible):")
    for k, v in sizes.items():
        print(f"  {k:13s} {v[0]:6d} {v[1]:6d} {v[2]:6d} {v[3]:6d}")
    print("sampled:", dict(Counter(r["kind"] for r in rows)), "total", len(rows))
    print("docs:", dict(sorted(Counter(r["pages"][0][0] for r in rows).items())))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
