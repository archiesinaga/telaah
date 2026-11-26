"""Import hand-written cross_doc questions from a CSV into user_{split}.jsonl, with the form's checks.

    .venv/Scripts/python eval/bench/import_cross_doc.py eval/bench/cross_doc_test_import.csv --dry-run
    .venv/Scripts/python eval/bench/import_cross_doc.py eval/bench/cross_doc_test_import.csv

Columns (header row required): question, page_a, page_b, bank_a, bank_b, indicator, value_a, value_b, unit
(page = doc:page, e.g. bri_2025:145; values exactly as printed; unit one of %, triliun Rupiah, miliar Rupiah,
juta Rupiah). Valid rows are appended; refused rows are listed by row number with the reason. Prints counts and
reasons only, never a question (BENCHMARK.md rule 2), so the file can stay unread by Claude sessions.
"""
import argparse
import csv
from pathlib import Path

from common import HERE, append_jsonl, norm, read_jsonl
from userq import cross_doc_row

COLUMNS = ["question", "page_a", "page_b", "bank_a", "bank_b", "indicator", "value_a", "value_b", "unit"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file")
    ap.add_argument("--split", default="test", choices=["test", "dev"])
    ap.add_argument("--dry-run", action="store_true", help="check only, write nothing")
    ap.add_argument("--out", help="output jsonl (default eval/bench/user_{split}.jsonl)")
    a = ap.parse_args()
    out = Path(a.out) if a.out else HERE / f"user_{a.split}.jsonl"
    with open(a.csv_file, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        rdr = csv.DictReader(f, delimiter=delim)
        rdr.fieldnames = [(h or "").strip().lower() for h in (rdr.fieldnames or [])]
        missing = [c for c in COLUMNS if c not in rdr.fieldnames]
        if missing:
            raise SystemExit(f"missing columns: {missing} (found {rdr.fieldnames})")
        rows = list(rdr)
    existing = read_jsonl(out) if out.exists() else []
    seen = {norm(r["question"]) for r in existing}
    n = len(existing)
    ok, bad = 0, []
    for i, r in enumerate(rows, 2):  # row 1 is the header
        try:
            q = (r["question"] or "").strip()
            if norm(q) in seen:
                raise ValueError("duplicate question")
            row = cross_doc_row(a.split, n + 1, q, r["page_a"] or "", r["page_b"] or "", r["bank_a"] or "",
                                r["bank_b"] or "", r["indicator"] or "", r["value_a"] or "", r["value_b"] or "",
                                (r["unit"] or "").strip())
        except ValueError as e:
            bad.append((i, str(e)))
            continue
        seen.add(norm(q))
        n += 1
        ok += 1
        if not a.dry_run:
            append_jsonl(out, row)
    tail = " (dry run, nothing written)" if a.dry_run else f", written to {out.name}"
    print(f"{a.csv_file}: {len(rows)} rows, valid {ok}, refused {len(bad)}{tail}")
    for i, why in bad:
        print(f"  row {i}: {why}")
    if not a.dry_run:
        total = sum(r.get("type") == "cross_doc" for r in read_jsonl(out))
        print(f"cross_doc rows now in {out.name}: {total}")


if __name__ == "__main__":
    main()
