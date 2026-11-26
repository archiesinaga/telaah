"""Viewer for the TEST reviewer subagent (BENCHMARK.md, test v2). Output is for the subagent only: never run it in the
tuning session.

    .venv/Scripts/python eval/bench/review_helper_test.py list TYPE            # pending cids of a type (flag marks)
    .venv/Scripts/python eval/bench/review_helper_test.py show CID OUT_DIR     # draft + parsed page text; saves page PNGs
"""
import sys
from pathlib import Path

from common import HERE, ROOT, pages, read_jsonl

sys.path.insert(0, str(ROOT / "src"))
from telaah.vision import render_page  # noqa: E402


def pending(typ: str) -> list[dict]:
    done = {r["cid"] for r in read_jsonl(HERE / "reviewed_test.jsonl")}
    return [c for c in read_jsonl(HERE / "candidates_test.jsonl") if c["type"] == typ and c["cid"] not in done]


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "list":
        rows = sorted(pending(sys.argv[2]), key=lambda c: (bool(c["problems"]), c["cid"]))
        print(len(rows), "pending;", " ".join(c["cid"] + ("*" if c["problems"] else "") for c in rows), "(* = auto-flagged)")
    elif cmd == "show":
        cid, out = sys.argv[2], Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        c = next(c for c in read_jsonl(HERE / "candidates_test.jsonl") if c["cid"] == cid)
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
