"""SFT step 6 prep: split sft/sft.jsonl 90/10 by source page for the Kaggle upload.

All examples drafted from the same page go to the same side (no page in both train and val).
The split is a hash of "doc_id|page", so it is stable across rebuilds.

Run:  python sft/split_sft.py          -> sft/kaggle_upload/train.jsonl, val.jsonl
"""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "sft.jsonl"
OUT = HERE / "kaggle_upload"
VAL_PCT = 10


def side(page):
    key = f"{page[0]}|{page[1]}".encode("utf-8")
    return "val" if int(hashlib.sha1(key).hexdigest(), 16) % 100 < VAL_PCT else "train"


def main():
    rows = [json.loads(line) for line in SRC.open(encoding="utf-8") if line.strip()]
    split = {"train": [], "val": []}
    for r in rows:
        split[side(r["page"])].append(r)

    OUT.mkdir(exist_ok=True)
    for name, items in split.items():
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    pages = {n: {tuple(r["page"]) for r in items} for n, items in split.items()}
    assert not pages["train"] & pages["val"], "a page is on both sides"
    print(f"total {len(rows)}: train {len(split['train'])}, val {len(split['val'])}")
    print(f"pages: train {len(pages['train'])}, val {len(pages['val'])}, overlap 0")
    for field in ("kind", "mix"):
        for n, items in split.items():
            c = collections.Counter(r[field] for r in items)
            print(f"{field:4} {n:5} " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))


if __name__ == "__main__":
    main()
