"""Record the audit verdicts of the auditor subagents (test v2). Prints counts only.

    .venv/Scripts/python eval/bench/audit_record_test.py verdicts.json

verdicts.json: {cid: {"verdict": "correct" | "wrong" | "fix", "note": "short reason", "question": "<corrected question>"}}.
"fix" keeps the row but replaces its question text (e.g. adds the missing unit/scale); the gold answer is never changed.
"correct" only for cids in audit_sample_test.json; "wrong" and "fix" for any accepted test row (reviewer-accepted
or hand-written). Rows are appended to audit_test.jsonl with "auditor": "claude-subagent" (a model check, not a human one).
"""
import json
import os
import sys
import time

from audit import audit_file, sample_file
from common import HERE, read_jsonl

SPLIT = os.environ.get("BENCH_SPLIT", "test")  # "test3" = test v3 (BENCHMARK.md 2026-11-27)


def main(path: str) -> None:
    verdicts = json.load(open(path, encoding="utf-8"))
    sample = set(json.loads(sample_file(SPLIT).read_text(encoding="utf-8")))
    accepted = {r["cid"] for r in read_jsonl(HERE / f"reviewed_{SPLIT}.jsonl") if r["decision"] == "accept"}
    accepted |= {r["cid"] for r in read_jsonl(HERE / f"user_{SPLIT}.jsonl")}
    done = {(r["cid"], r["verdict"] == "fix") for r in read_jsonl(audit_file(SPLIT))}
    n = {"correct": 0, "wrong": 0, "fix": 0}
    skipped = 0
    with open(audit_file(SPLIT), "a", encoding="utf-8") as f:
        for cid, v in verdicts.items():
            kind = v.get("verdict")
            ok = ((kind == "correct" and cid in sample) or (kind == "wrong" and cid in accepted)
                  or (kind == "fix" and cid in accepted and v.get("question", "").strip()))
            if not ok or (cid, kind == "fix") in done:
                skipped += 1
                continue
            row = {"cid": cid, "split": SPLIT, "verdict": kind, "note": v.get("note", "")[:300],
                   "auditor": "claude-subagent", "audited_at": time.strftime("%Y-%m-%d %H:%M")}
            if kind == "fix":
                row["question"] = v["question"].strip()
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n[kind] += 1
    print(f"recorded: {n}, skipped {skipped}")


if __name__ == "__main__":
    main(sys.argv[1])
