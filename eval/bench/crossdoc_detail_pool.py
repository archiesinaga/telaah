"""Page pairs for the dev-only cross_doc DETAIL diagnostic set (BENCHMARK.md Status 2026-11-28).

Two banks, same report year, same term (sample_pages.pairs), from pages that no benchmark split has used:
everything in sample_pages.v3_excluded() plus every page (and its +-1 neighbours) of pages6.jsonl and the gold pages
of test v3 (test3.jsonl, user_test3.jsonl, user_test.jsonl). Split files are read for page numbers only; nothing but
counts is printed. Only dev-hash pages are sampled, so unused test-hash pages stay free for a later held-out set and
the pairs pass userq.check_test_page for split 'dev' unchanged. Most pairs use a term the facts table does not answer.

    .venv/Scripts/python eval/bench/crossdoc_detail_pool.py            # -> eval/bench/crossdoc_detail_pairs.jsonl
"""
import json
import random
import re
import sys
from collections import Counter

import sample_pages
from common import BANK, HERE, SEED, docs, page_split, pages, read_jsonl

OUT = HERE / "crossdoc_detail_pairs.jsonl"
N_NOT_FACTS, N_FACTS = 68, 12  # ~85% on a term the facts table does not cover


def in_facts(label: str) -> bool:
    from telaah.facts import Q_INDICATORS
    return any(re.search(pat, label.lower()) for pat in Q_INDICATORS.values())


def excluded() -> set:
    near = set(sample_pages.v3_excluded())
    extra = {tuple(dp) for r in read_jsonl(HERE / "pages6.jsonl") for dp in r["pages"]}
    for f in ("test3.jsonl", "user_test3.jsonl", "user_test.jsonl", "user_dev.jsonl"):
        for r in read_jsonl(HERE / f):
            extra |= {tuple(p) for p in r.get("gold_pages", [])}
    near |= {(d, p + o) for d, p in extra for o in (-1, 0, 1)}
    print(f"excluded with neighbours (v3 rule + pages6 + test v3 gold): {len(near)}")
    return near


def main() -> None:
    rng = random.Random(SEED + 99)
    used = excluded()
    test_hash = {(d, p) for d in docs() for p in pages(d) if page_split(d, p) == "test"}
    used |= test_hash  # dev-hash pages only
    all_terms = list(sample_pages.TERMS)
    rows = []
    for terms, n in (([t for t in all_terms if not in_facts(t)], N_NOT_FACTS), ([t for t in all_terms if in_facts(t)], N_FACTS)):
        sample_pages.TERMS = terms
        for r in sample_pages.pairs(n, used, rng, any_split="dev"):
            r["in_facts_table"] = in_facts(r["term"])
            rows.append(r)
    sample_pages.TERMS = all_terms
    print("pairs sampled:", len(rows), "| on a facts-table term:", sum(r["in_facts_table"] for r in rows))
    print("report years:", dict(Counter(r["pages"][0][0].split("_")[1] for r in rows)))
    print("banks:", dict(Counter(BANK[d.split("_")[0]] for r in rows for d, _ in r["pages"])))
    if "--dry-run" in sys.argv:
        print("dry run: nothing written")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(json.dumps({"id": f"x{i:04d}", **r}, ensure_ascii=False) + "\n")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
