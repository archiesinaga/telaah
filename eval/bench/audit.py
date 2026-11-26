"""Human audit of model-reviewed drafts (test v2): a seeded random sample of the accepted rows, checked by the user.

    .venv/Scripts/python eval/bench/audit.py make test        # writes audit_sample_test.json (cids only), prints counts
    .venv/Scripts/python eval/bench/audit.py add-user test    # add every hand-written (user_test) cross_doc row to the sample
    .venv/Scripts/python eval/bench/audit.py stats test       # verdicts so far: counts and the error rate

The sample is ~25% of the rows accepted by the reviewer subagent per type (chart 50%, at least 4 per type), seeded so it
is reproducible. The user judges each row in the review app's "Audit sample" tab (Correct / Wrong); a Wrong row is
dropped by build.py. If the sample error rate is above 15%, review the rest by hand. Prints counts only.
"""
import json
import random
import sys
from collections import Counter

from common import HERE, SEED, read_jsonl

SHARE = {"chart": 0.5}
DEFAULT_SHARE = 0.25
MIN_PER_TYPE = 4


def sample_file(split): return HERE / f"audit_sample_{split}.json"
def audit_file(split): return HERE / f"audit_{split}.jsonl"


def accepted(split: str) -> list[dict]:
    return [r for r in read_jsonl(HERE / f"reviewed_{split}.jsonl")
            if r["decision"] == "accept" and r.get("reviewer", "").startswith("claude")]


def make(split: str) -> None:
    rows = accepted(split)
    rng = random.Random(SEED + 77)
    picked = []
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    for t in sorted(by_type):
        pool = sorted(by_type[t], key=lambda r: r["cid"])
        n = min(len(pool), max(MIN_PER_TYPE, round(len(pool) * SHARE.get(t, DEFAULT_SHARE))))
        picked += [r["cid"] for r in rng.sample(pool, n)]
    sample_file(split).write_text(json.dumps(sorted(picked)), encoding="utf-8")
    print(f"accepted by the reviewer: {Counter(r['type'] for r in rows)}")
    print(f"audit sample: {len(picked)} rows (cids only) -> {sample_file(split).name}")


def add_user(split: str) -> None:
    """Rows written through the cross-doc tab / importer are not in reviewed_{split}.jsonl: audit all of them too."""
    cids = {r["cid"] for r in read_jsonl(HERE / f"user_{split}.jsonl") if r["type"] == "cross_doc"}
    sample = set(json.loads(sample_file(split).read_text(encoding="utf-8"))) if sample_file(split).exists() else set()
    sample_file(split).write_text(json.dumps(sorted(sample | cids)), encoding="utf-8")
    print(f"hand-written cross_doc rows added to the audit sample: {len(cids - sample)} (sample now {len(sample | cids)})")


def stats(split: str) -> None:
    sample = json.loads(sample_file(split).read_text(encoding="utf-8")) if sample_file(split).exists() else []
    rows = read_jsonl(audit_file(split))
    fixes = sum(r["verdict"] == "fix" for r in rows)
    verdicts = {r["cid"]: r["verdict"] for r in rows if r["verdict"] != "fix" and r["cid"] in set(sample)}
    extra_wrong = len({r["cid"] for r in rows if r["verdict"] == "wrong" and r["cid"] not in set(sample)})
    if extra_wrong:
        print(f"rows outside the sample judged wrong by later checks: {extra_wrong} (not in the error rate)")
    wrong = sum(v == "wrong" for v in verdicts.values())
    if fixes:
        print(f"question fixes recorded (e.g. unit/scale added): {fixes}")
    print(f"sample {len(sample)}, audited {len(verdicts)}, correct {len(verdicts) - wrong}, wrong {wrong}"
          + (f", error rate {wrong / len(verdicts):.0%}" if verdicts else ""))
    if verdicts and wrong / len(verdicts) > 0.15:
        print("error rate above 15%: review the remaining accepted rows by hand")


if __name__ == "__main__":
    {"make": make, "add-user": add_user, "stats": stats}[sys.argv[1]](sys.argv[2])
