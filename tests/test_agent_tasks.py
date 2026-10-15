import json
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))

import run_agent_tasks as rat  # noqa: E402

TASKS = [json.loads(l) for l in (EVAL / "agent_tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def test_canon_handles_indonesian_and_english_formats():
    assert rat.canon("1.249.044") == 1249044
    assert rat.canon("0,96") == 0.96
    assert rat.canon("0.96") == 0.96
    assert rat.canon("2.135.371,5") == 2135371.5
    assert rat.canon("-1,85") == -1.85


def test_gold_answers_score_full_marks():
    for t in TASKS:
        refused = not t["answerable"]
        s = rat.score(t, {"answer": t["gold_answer"], "refused": refused})
        assert s["success"] == 1.0, (t["id"], s)


def test_failure_types():
    t = next(t for t in TASKS if t["category"] == "ranking")
    assert rat.score(t, {"answer": "TIDAK DITEMUKAN", "refused": True})["failure"] == "refused"
    assert rat.score(t, {"answer": "nilainya 99,99", "refused": False})["failure"] == "no_gold_number"
    half = f"{t['gold_numbers'][0]}"
    assert rat.score(t, {"answer": half, "refused": False})["failure"] == "partial_numbers"
    u = next(t for t in TASKS if not t["answerable"])
    assert rat.score(u, {"answer": "Rp1.000", "refused": False})["failure"] == "answered_unanswerable"


def test_task_file_is_well_formed():
    assert len(TASKS) == 60 and len({t["id"] for t in TASKS}) == 60
    for t in TASKS:
        assert t["answerable"] == bool(t["gold_numbers"]) == bool(t["gold_pages"])
