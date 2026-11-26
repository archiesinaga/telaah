"""Pack the prebuilt data the demo needs into one zip (for a GitHub Release) and write the files that describe it.

    .venv/Scripts/python scripts/make_data_bundle.py [--version v1]

Writes (nothing is uploaded):
  dist/telaah-data-<version>.zip   data/processed/*.jsonl, data/qdrant/ (without .lock), data/facts.sqlite, DATA_NOTICE.md
  scripts/data_manifest.json       version, asset name, url, size, sha256 (read by scripts/fetch_data.py to verify the download)
  DATA_NOTICE.md                   source of every document in the bundle (from corpus/manifest.csv)

Not packed: data/raw (the PDFs), data/colpali, bm25.pkl (rebuilt from the text on first use; no pickle is downloaded),
transcripts and traces. The demo does not need them.
"""
import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "archiesinaga/telaah"

NOTICE_HEAD = """# Data notice

`telaah-data-<version>.zip` (GitHub Release `data-<version>`) holds the text extracted from the public documents below,
the vector index built from it, and the facts table. It exists so the demo can run without downloading and parsing about
1 GB of PDFs. The source PDFs are not redistributed.

- The annual reports and regulations belong to their publishers (the banks, OJK and Bank Indonesia). The extracted text
  is provided for research and evaluation of this project only. Indonesian laws and regulations are not subject to
  copyright (UU 28/2014 art. 42), the annual reports are.
- If you are a rights holder and want a document removed, open an issue in this repository and it will be removed from
  the bundle and from the Release.
- The original files can be fetched again from the URLs below with `python corpus/download_corpus.py`.

| doc_id | issuer | title | year | source |
| --- | --- | --- | --- | --- |
"""


def notice(docs: list[str], version: str) -> str:
    rows = {r["doc_id"]: r for r in csv.DictReader(open(ROOT / "corpus" / "manifest.csv", encoding="utf-8"))}
    out = [NOTICE_HEAD.replace("<version>", version)]
    for d in docs:
        base = rows.get(d) or rows.get(d.split("__")[0]) or {}
        title = (base.get("title") or d).replace("|", "/")
        out.append(f"| {d} | {base.get('issuer', '')} | {title} | {base.get('year', '')} | {base.get('url', '')} |\n")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    a = ap.parse_args()
    asset = f"telaah-data-{a.version}.zip"
    docs = sorted(p.stem for p in (ROOT / "data" / "processed").glob("*.jsonl"))
    text = notice(docs, a.version)
    (ROOT / "DATA_NOTICE.md").write_text(text, encoding="utf-8")

    files = [p for p in sorted((ROOT / "data" / "processed").glob("*.jsonl"))]
    files += [p for p in sorted((ROOT / "data" / "qdrant").rglob("*")) if p.is_file() and p.name != ".lock"]
    files += [ROOT / "data" / "facts.sqlite"]
    out = ROOT / "dist" / asset
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
        z.writestr("DATA_NOTICE.md", text)
    h = hashlib.sha256()
    with open(out, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    manifest = {"version": a.version, "tag": f"data-{a.version}", "asset": asset,
                "url": f"https://github.com/{REPO}/releases/download/data-{a.version}/{asset}",
                "size": out.stat().st_size, "sha256": h.hexdigest(), "documents": len(docs)}
    (ROOT / "scripts" / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files, {len(docs)} documents -> {out} ({manifest['size'] / 1e6:.0f} MB)")
    print("sha256", manifest["sha256"])


if __name__ == "__main__":
    main()
