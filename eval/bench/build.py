"""Assemble eval/bench/dev.jsonl and test.jsonl (or, with --split test3, only test3.jsonl = test v3) from the seed
questions and the reviewed drafts.

Quotas per type and split come from common.QUOTA; when more questions were accepted than a quota needs, a fixed
hash order picks them (seed questions are always kept). Prints counts and sha256 only.

    .venv/Scripts/python eval/bench/build.py
    .venv/Scripts/python eval/bench/build.py --split test3   # test v3 only; dev.jsonl and test.jsonl untouched
"""
import hashlib
from collections import Counter

from common import EVAL, HERE, QUOTA, QUOTA_V3, TYPES, V3, norm, read_jsonl

KEYS = ["id", "type", "question", "gold_answer", "gold_pages", "answerable", "numeric", "split", "source"]


def rank(cid: str) -> str:
    return hashlib.sha256(cid.encode()).hexdigest()


def collect(split: str) -> list[dict]:
    rows = []
    if split == "dev":
        rows += [{**q, "split": "dev", "source": "seed"} for q in read_jsonl(EVAL / "seed_questions.jsonl")]
    audit_rows = read_jsonl(HERE / f"audit_{split}.jsonl")  # audit.py
    wrong = {r["cid"] for r in audit_rows if r["verdict"] == "wrong"}
    fixed = {r["cid"]: r["question"] for r in audit_rows if r["verdict"] == "fix"}  # latest wins
    acc = [r for r in read_jsonl(HERE / f"reviewed_{split}.jsonl") if r["decision"] == "accept" and r["cid"] not in wrong]
    rows += [{**r, "source": "draft+review", **({"question": fixed[r["cid"]]} if r["cid"] in fixed else {})} for r in acc]
    rows += [{"source": "user", **r, **({"question": fixed[r["cid"]]} if r["cid"] in fixed else {})}
             for r in read_jsonl(HERE / f"user_{split}.jsonl") if r["cid"] not in wrong]
    return rows


def quota(split: str, t: str) -> int:
    return QUOTA_V3[t] if split == V3 else QUOTA[t][1 if split == "dev" else 2]


def build(split: str) -> tuple[list[dict], Counter, Counter]:
    rows, have = collect(split), Counter()
    out = []
    for t in TYPES:
        of_type = [r for r in rows if r["type"] == t]
        seed = [r for r in of_type if r["source"] == "seed"]
        rest = sorted((r for r in of_type if r["source"] != "seed"), key=lambda r: rank(r["cid"]))
        have[t] = len(of_type)
        out += seed + rest[: max(0, quota(split, t) - len(seed))]
    prefix = {"dev": "bd", V3: "b3t"}.get(split, "bt")
    in_facts = {r["id"]: r["in_facts_table"] for r in read_jsonl(HERE / "pages6.jsonl") if "in_facts_table" in r}
    n = 0
    for r in out:
        if r["source"] != "seed":
            n += 1
            r["id"] = f"{prefix}{n:04d}"
        if "figures" in r:
            r.setdefault("extra", {}).update({"figures": r["figures"], "op": r["op"]})
        if split == V3 and (page_id := str(r.get("cid", "")).rsplit("-", 1)[0]) in in_facts:
            r.setdefault("extra", {})["in_facts_table"] = in_facts[page_id]  # cross_doc reported per group
    final = [{k: r[k] for k in KEYS} | ({"extra": r["extra"]} if "extra" in r else {}) for r in out]
    dup = Counter(norm(r["question"]) for r in final)
    if any(v > 1 for v in dup.values()):
        print(f"  {split}: {sum(v > 1 for v in dup.values())} duplicated questions")
    return final, Counter(r["type"] for r in final), have


def main_v3() -> None:
    import json
    final, used, have = build(V3)
    earlier = {tuple(p) for f in ("dev.jsonl", "test.jsonl") for r in read_jsonl(HERE / f) for p in r["gold_pages"]}
    leak = sum(any(tuple(p) in earlier for p in r["gold_pages"]) for r in final)
    if leak:
        print(f"  {V3}: {leak} questions share a gold page with dev or test v2")
    path = HERE / f"{V3}.jsonl"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{V3}: {len(final)}/{sum(QUOTA_V3.values())}  " + "  ".join(f"{t} {used[t]}/{QUOTA_V3[t]} (have {have[t]})" for t in TYPES))
    print(f"  sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")


def main() -> None:
    import json
    import sys
    if "--split" in sys.argv and sys.argv[sys.argv.index("--split") + 1] == V3:
        return main_v3()
    test_pages = set()
    for split in ("test", "dev"):
        final, used, have = build(split)
        if split == "test":
            test_pages = {tuple(p) for r in final for p in r["gold_pages"]}
        else:
            leak = sum(any(tuple(p) in test_pages for p in r["gold_pages"]) for r in final)
            if leak:
                print(f"  dev: {leak} questions share a gold page with test")
        path = HERE / f"{split}.jsonl"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for r in final:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        col = 1 if split == "dev" else 2
        print(f"{split}: {len(final)}/{sum(q[col] for q in QUOTA.values())}  "
              + "  ".join(f"{t} {used[t]}/{QUOTA[t][col]} (have {have[t]})" for t in TYPES))
        print(f"  sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")


if __name__ == "__main__":
    main()
