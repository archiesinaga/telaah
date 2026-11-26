"""Re-score correct_numeric of a finished eval run with the current telaah.metrics.numeric_match (offline, no LLM).

    python eval/rescore_numeric.py eval/runs/<run>.json eval/bench/<questions>.jsonl [--write]

Prints only the summary and per-type scores before/after and the number of changed questions, never per-question
rows, so it is safe on a blind test run. --write keeps the original as <run>.before_numeric_fix.json and updates
the run in place. Only correct_numeric changes: judge/faithful were decided with the old score under
--judge-on-fail, so those stay as they were."""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from telaah.metrics import numeric_match  # noqa: E402

KEYS = ["recall@5", "citation_acc", "refusal_acc", "correct_numeric", "correct_judge", "faithful", "latency_s"]


def aggregate(results: list[dict]) -> tuple[dict, dict]:
    def mean(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return round(sum(v) / len(v), 3) if v else None

    summary = {k: mean(results, k) for k in KEYS}
    by_type = {}
    for t in sorted({r["type"] for r in results}):
        rows = [r for r in results if r["type"] == t]
        by_type[t] = {"n": len(rows), **{k: mean(rows, k) for k in KEYS}}
    return summary, by_type


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("questions", type=Path)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    log = json.loads(a.run.read_text(encoding="utf-8"))
    gold = {}
    for line in a.questions.read_text(encoding="utf-8").splitlines():
        if line.strip():
            q = json.loads(line)
            gold[q["id"]] = q
    missing = [r["id"] for r in log["results"] if r["id"] not in gold]
    if missing:
        sys.exit(f"{len(missing)} run ids are not in {a.questions.name}: wrong question file")

    before_sum, before_type = aggregate(log["results"])
    changed = 0
    for r in log["results"]:
        if r["correct_numeric"] is None:
            continue
        new = float(numeric_match(r["answer"], gold[r["id"]]["gold_answer"]))
        changed += new != r["correct_numeric"]
        r["correct_numeric"] = new
    after_sum, after_type = aggregate(log["results"])

    print(f"{a.run.name}: {changed} questions changed correct_numeric")
    print(f"overall numeric {before_sum['correct_numeric']} -> {after_sum['correct_numeric']}")
    for t in after_type:
        print(f"  {t:13s} n={after_type[t]['n']:3d}  numeric {before_type[t]['correct_numeric']} -> {after_type[t]['correct_numeric']}")

    if a.write:
        backup = a.run.with_name(a.run.stem + ".before_numeric_fix.json")
        if not backup.exists():
            shutil.copyfile(a.run, backup)
        log["summary"], log["by_type"] = after_sum, after_type
        log.setdefault("rescored", []).append("correct_numeric: trailing decimal zeros ignored (metrics._value)")
        a.run.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written; original kept as {backup.name}")


if __name__ == "__main__":
    main()
