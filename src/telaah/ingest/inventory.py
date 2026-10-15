"""Document inventory CSV: pages, chars/page (low = likely scanned), table pages."""
import csv
import json

from telaah.config import PROCESSED_DIR, ROOT

FIELDS = ["doc_id", "pages_with_text", "avg_chars_per_page", "pages_with_tables"]


def build_inventory() -> None:
    rows = []
    for f in sorted(PROCESSED_DIR.glob("*.jsonl")):
        chunks = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l]
        n = len(chunks)
        rows.append({
            "doc_id": f.stem,
            "pages_with_text": n,
            "avg_chars_per_page": sum(len(c["text"]) for c in chunks) // max(n, 1),
            "pages_with_tables": sum(1 for c in chunks if "| ---" in c["text"] or "|---" in c["text"]),
        })
    out = ROOT / "data" / "inventory.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} docs). Add source/year/language columns by hand.")
