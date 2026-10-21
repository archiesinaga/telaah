"""Record review decisions for a batch of dev candidates at once (used when Claude reviews, not the user).

    .venv/Scripts/python eval/bench/bulk_review.py decisions.json

decisions.json: {"accept": [cids], "reject": {cid: reason}, "edit": {cid: new question}}
Same output format as review_app.decide (reviewed_dev.jsonl), plus "reviewer": "claude". The test split is
refused: Claude never reads it (BENCHMARK.md rule 2). Page references ("halaman 773", "dokumen bri_2024") are
stripped from questions: a question must stand alone.
"""
import json
import re
import sys
import time

from common import HERE, append_jsonl, pages, read_jsonl
from gold import compute, fmt_id

REF = re.compile(r"\s*(?:,\s*)?(?:pada |di |dalam )?(?:halaman \d+|dokumen \w+_\d{4}|\(\w+_\d{4}\))", re.I)


def clean(q: str) -> str:
    return re.sub(r"\s+", " ", REF.sub("", q)).replace(" ,", ",").strip()


def loose_ok(c: dict) -> bool:
    """Evidence words all on the page (list markers and line breaks ignored)."""
    ev = c["draft"].get("evidence") or []
    ev = ev if isinstance(ev, list) else [ev]
    text = re.sub(r"[^a-z0-9]+", " ", " ".join(pages(d)[p] for d, p in c["pages"]).lower())
    return all(re.sub(r"[^a-z0-9]+", " ", e.lower()).strip()[:120] in text for e in ev)


def main(path: str) -> None:
    dec = json.load(open(path, encoding="utf-8"))
    cands = {c["cid"]: c for c in read_jsonl(HERE / "candidates_dev.jsonl")}
    done = {r["cid"] for r in read_jsonl(HERE / "reviewed_dev.jsonl")}
    out = HERE / "reviewed_dev.jsonl"
    n_acc = n_rej = 0
    now = time.strftime("%Y-%m-%d %H:%M")
    for cid, reason in dec.get("reject", {}).items():
        if cid in cands and cid not in done:
            append_jsonl(out, {"cid": cid, "split": "dev", "decision": "reject", "reason": reason,
                               "reviewer": "claude", "reviewed_at": now})
            n_rej += 1
    for cid in dec.get("accept", []):
        c = cands[cid]  # KeyError if the cid is a test candidate: refused on purpose
        if cid in done or cid in dec.get("reject", {}):
            continue
        if c["problems"] and not loose_ok(c):
            print(f"  {cid}: flagged and evidence not on the page, rejected")
            append_jsonl(out, {"cid": cid, "split": "dev", "decision": "reject", "reason": "evidence not on page",
                               "reviewer": "claude", "reviewed_at": now})
            n_rej += 1
            continue
        d = c["draft"]
        row = {"cid": cid, "split": "dev", "decision": "accept", "reviewer": "claude", "reviewed_at": now,
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
        n_acc += 1
    print(f"accepted {n_acc}, rejected {n_rej}")


if __name__ == "__main__":
    main(sys.argv[1])
