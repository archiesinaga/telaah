"""Assemble eval/bench/dev.jsonl and test.jsonl from the seed questions and the reviewed drafts.

Quotas per type and split come from common.QUOTA; when more questions were accepted than a quota needs, a fixed
hash order picks them (seed questions are always kept). Prints counts and sha256 only.

    .venv/Scripts/python eval/bench/build.py
"""
import hashlib
from collections import Counter

from common import EVAL, HERE, QUOTA, TYPES, norm, read_jsonl

KEYS = ["id", "type", "question", "gold_answer", "gold_pages", "answerable", "numeric", "split", "source"]


def rank(cid: str) -> str:
    return hashlib.sha256(cid.encode()).hexdigest()


def collect(split: str) -> list[dict]:
    rows = []
    if split == "dev":
        rows += [{**q, "split": "dev", "source": "seed"} for q in read_jsonl(EVAL / "seed_questions.jsonl")]
    acc = [r for r in read_jsonl(HERE / f"reviewed_{split}.jsonl") if r["decision"] == "accept"]
    rows += [{**r, "source": "draft+review"} for r in acc]
    rows += [{"source": "user", **r} for r in read_jsonl(HERE / f"user_{split}.jsonl")]
    return rows


def build(split: str) -> tuple[list[dict], Counter, Counter]:
    col = 1 if split == "dev" else 2
    rows, have = collect(split), Counter()
    out = []
    for t in TYPES:
        of_type = [r for r in rows if r["type"] == t]
        seed = [r for r in of_type if r["source"] == "seed"]
        rest = sorted((r for r in of_type if r["source"] != "seed"), key=lambda r: rank(r["cid"]))
        have[t] = len(of_type)
        out += seed + rest[: max(0, QUOTA[t][col] - len(seed))]
    prefix = "bd" if split == "dev" else "bt"
    n = 0
    for r in out:
        if r["source"] != "seed":
            n += 1
            r["id"] = f"{prefix}{n:04d}"
        if "figures" in r:
            r.setdefault("extra", {}).update({"figures": r["figures"], "op": r["op"]})
    final = [{k: r[k] for k in KEYS} | ({"extra": r["extra"]} if "extra" in r else {}) for r in out]
    dup = Counter(norm(r["question"]) for r in final)
    if any(v > 1 for v in dup.values()):
        print(f"  {split}: {sum(v > 1 for v in dup.values())} duplicated questions")
    return final, Counter(r["type"] for r in final), have


def main() -> None:
    import json
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
