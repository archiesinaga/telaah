"""Record TEST review decisions made by the reviewer subagent (BENCHMARK.md rules 1-2, test v2). Prints counts only.

    .venv/Scripts/python eval/bench/bulk_review_test.py decisions.json

decisions.json: {"accept": [cids], "reject": {cid: reason}, "edit": {cid: new question}}
Same output format as bulk_review.py / review_app.decide (reviewed_test.jsonl) with "reviewer": "claude-subagent".
Run it from the reviewer subagent only: the tuning session must not read the file it writes or the candidates.
Rejected reasons should come from review_app.REASONS; accepted drafts that are flagged must still have their
evidence on the page.
"""
import json
import sys
import time
from collections import Counter

from bulk_review import clean, loose_ok
from common import HERE, append_jsonl, read_jsonl
from gold import compute, fmt_id

REASONS = {"wrong or unsupported answer", "ambiguous / several answers", "not self-contained", "trivial",
           "chart not readable", "duplicate", "other"}


def main(path: str) -> None:
    dec = json.load(open(path, encoding="utf-8"))
    cands = {c["cid"]: c for c in read_jsonl(HERE / "candidates_test.jsonl")}
    out = HERE / "reviewed_test.jsonl"
    done = {r["cid"] for r in read_jsonl(out)}
    now = time.strftime("%Y-%m-%d %H:%M")
    acc, rej, skipped = Counter(), Counter(), 0
    for cid, reason in dec.get("reject", {}).items():
        if cid not in cands or cid in done:
            skipped += 1
            continue
        append_jsonl(out, {"cid": cid, "split": "test", "decision": "reject",
                           "reason": reason if reason in REASONS else "other",
                           "reviewer": "claude-subagent", "reviewed_at": now})
        rej[cands[cid]["type"]] += 1
    for cid in dec.get("accept", []):
        if cid not in cands or cid in done or cid in dec.get("reject", {}):
            skipped += 1
            continue
        c = cands[cid]
        if c["problems"] and not loose_ok(c):
            append_jsonl(out, {"cid": cid, "split": "test", "decision": "reject", "reason": "wrong or unsupported answer",
                               "reviewer": "claude-subagent", "reviewed_at": now})
            rej[c["type"]] += 1
            continue
        d = c["draft"]
        row = {"cid": cid, "split": "test", "decision": "accept", "reviewer": "claude-subagent", "reviewed_at": now,
               "type": c["type"], "question": clean(dec.get("edit", {}).get(cid, d["question"])),
               "gold_pages": c["pages"], "answerable": True}
        if c["type"] in ("calculation", "cross_doc"):
            x, gold = compute(d["figures"], d["op"])
            if c["type"] == "cross_doc":
                gold = fmt_id(round(abs(x), 2))
            row.update({"figures": d["figures"], "op": d["op"], "computed": gold, "numeric": True,
                        "gold_answer": gold if c["type"] == "calculation" else (
                            d["answer"].strip() if "selisih" in d["answer"] else f"{d['answer'].strip()} (selisih {gold})")})
        else:
            row.update({"gold_answer": d["answer"].strip(), "numeric": bool(d.get("numeric", True))})
        append_jsonl(out, row)
        acc[c["type"]] += 1
    print("accepted:", dict(acc), "rejected:", dict(rej), "skipped (unknown or already decided):", skipped)


if __name__ == "__main__":
    main(sys.argv[1])
