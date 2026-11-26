"""Download the prebuilt demo data (extracted text, vector index, facts table) and unpack it into ./data.

    python scripts/fetch_data.py            # download, verify the sha256 pinned in scripts/data_manifest.json, unpack
    python scripts/fetch_data.py --force    # replace an existing data/ folder content
    python scripts/fetch_data.py --zip PATH # use an already downloaded zip (still verified)

Standard library only. The download is checked against the sha256 stored in this repository, so a tampered or partial
file is refused. The first run of the app also downloads the embedding model (BAAI/bge-m3, about 2 GB) from Hugging Face.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "data_manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, size: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "telaah-fetch-data"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            print(f"\r  {done / 1e6:6.0f} / {size / 1e6:.0f} MB", end="", flush=True)
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--zip", help="use this local zip instead of downloading")
    a = ap.parse_args()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (ROOT / "data" / "processed").is_dir() and any((ROOT / "data" / "processed").iterdir()) and not a.force:
        print("data/processed already exists: nothing to do (use --force to replace it).")
        return 0
    zpath = Path(a.zip) if a.zip else ROOT / "dist" / m["asset"]
    if not a.zip:
        print(f"downloading {m['asset']} ({m['size'] / 1e6:.0f} MB) from the GitHub Release {m['tag']} ...")
        try:
            download(m["url"], zpath, m["size"])
        except Exception as e:  # noqa: BLE001
            print(f"download failed: {e}\nTry again, or download {m['url']} in a browser and run with --zip <file>.")
            return 1
    got = sha256(zpath)
    if got != m["sha256"]:
        print(f"sha256 mismatch for {zpath.name}:\n  expected {m['sha256']}\n  got      {got}\nRefusing to unpack.")
        return 1
    root = ROOT.resolve()
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():  # refuse paths that would leave the project folder
            if not (root / name).resolve().is_relative_to(root):
                print(f"unsafe path in zip: {name}")
                return 1
        z.extractall(root)
    print(f"unpacked {m['documents']} documents into {ROOT / 'data'} (checksum ok). Next: python app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
