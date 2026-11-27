"""Viewer for the TEST reviewer subagent (BENCHMARK.md, test v2). Output is for the subagent only: never run it in the
tuning session.

    .venv/Scripts/python eval/bench/review_helper_test.py list TYPE            # pending cids of a type (flag marks)
    .venv/Scripts/python eval/bench/review_helper_test.py show CID OUT_DIR     # draft + parsed page text; saves page PNGs
    .venv/Scripts/python eval/bench/review_helper_test.py accepted TYPE        # accepted cids of a type not yet audited
    .venv/Scripts/python eval/bench/review_helper_test.py final CID OUT_DIR    # the ACCEPTED row (as it will be scored) + pages
"""
import os
import sys
from pathlib import Path

from common import HERE, ROOT, pages, read_jsonl

SPLIT = os.environ.get("BENCH_SPLIT", "test")  # "test3" = test v3 (BENCHMARK.md 2026-11-27)

sys.path.insert(0, str(ROOT / "src"))
from telaah.vision import render_page  # noqa: E402


def pending(typ: str) -> list[dict]:
    done = {r["cid"] for r in read_jsonl(HERE / f"reviewed_{SPLIT}.jsonl")}
    return [c for c in read_jsonl(HERE / f"candidates_{SPLIT}.jsonl") if c["type"] == typ and c["cid"] not in done]


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "list":
        rows = sorted(pending(sys.argv[2]), key=lambda c: (bool(c["problems"]), c["cid"]))
        print(len(rows), "pending;", " ".join(c["cid"] + ("*" if c["problems"] else "") for c in rows), "(* = auto-flagged)")
    elif cmd == "accepted":
        audited = {r["cid"] for r in read_jsonl(HERE / f"audit_{SPLIT}.jsonl") if r["verdict"] != "fix"}
        rows = [r["cid"] for r in read_jsonl(HERE / f"reviewed_{SPLIT}.jsonl")
                if r["decision"] == "accept" and r["type"] == sys.argv[2] and r["cid"] not in audited]
        print(len(rows), "accepted, not yet audited:", " ".join(sorted(rows)))
    elif cmd == "final":  # audit view: the accepted row only (no drafter evidence, no reviewer notes)
        cid, out = sys.argv[2], Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        rows = [r for r in read_jsonl(HERE / f"reviewed_{SPLIT}.jsonl") if r["cid"] == cid and r["decision"] == "accept"]
        rows += [r for r in read_jsonl(HERE / f"user_{SPLIT}.jsonl") if r["cid"] == cid]  # hand-written rows
        r = rows[0]
        print(f"CID {cid}  type {r['type']}  gold pages {r['gold_pages']}")
        print("QUESTION:", r["question"])
        print("GOLD ANSWER:", r["gold_answer"])
        if r.get("figures"):
            print("FIGURES:", r["figures"], "OP:", r.get("op"))
        for i, (doc, page) in enumerate(r["gold_pages"]):
            png = out / f"{cid}_{i}_{doc}_{page}.png"
            png.write_bytes(render_page(doc, page, dpi=170 if r["type"] in ("chart", "cross_doc") else 130))
            print(f"--- PAGE {doc}:{page}  image: {png}")
            print(pages(doc).get(page, "")[:6000])
    elif cmd == "show":
        cid, out = sys.argv[2], Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        c = next(c for c in read_jsonl(HERE / f"candidates_{SPLIT}.jsonl") if c["cid"] == cid)
        d = c["draft"]
        print(f"CID {cid}  type {c['type']}  pages {c['pages']}  problems {c['problems']}")
        for k in ("question", "answer", "evidence", "figures", "op", "numeric"):
            print(f"{k.upper()}: {d.get(k)}")
        for i, (doc, page) in enumerate(c["pages"]):
            png = out / f"{cid}_{i}_{doc}_{page}.png"
            png.write_bytes(render_page(doc, page, dpi=170 if c["type"] in ("chart", "cross_doc") else 130))
            print(f"--- PAGE {doc}:{page}  image: {png}")
            print(pages(doc).get(page, "")[:6000])


if __name__ == "__main__":
    main()
