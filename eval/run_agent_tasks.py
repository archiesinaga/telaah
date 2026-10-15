"""Score the 60 multi-step tasks in eval/agent_tasks.jsonl with RAG, the agent, or the router.

    .venv/Scripts/python eval/run_agent_tasks.py --mode router --ids t001 t013 t033     # quick subset
    .venv/Scripts/python eval/run_agent_tasks.py --mode agent                           # all 60
    .venv/Scripts/python eval/run_agent_tasks.py --compare eval/runs/tasks-rag-*.json eval/runs/tasks-agent-*.json

A task is a success when every number in `gold_numbers` appears in the answer (a refusal for unanswerable
tasks). No LLM judge: the gold numbers are computed from the pages, so string matching is exact.
"""
import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
NUM_RE = re.compile(r"-?\d[\d.,]*")


def canon(tok: str) -> float | None:
    """Indonesian or English number text -> float. '1.249.044' -> 1249044, '0,96' -> 0.96, '0.96' -> 0.96."""
    t = tok.strip(".,")
    neg = t.startswith("-")
    t = t.lstrip("-")
    if not t:
        return None
    if "." in t and "," in t:  # the last separator is the decimal one
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "." in t:
        t = t.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+", t) else t
    elif "," in t:
        t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def numbers_in(text: str) -> list[float]:
    return [v for v in (canon(m) for m in NUM_RE.findall(text)) if v is not None]


def found(gold: str, pred_nums: list[float]) -> bool:
    g = canon(gold)
    if g is None:
        return False
    return any(abs(p - g) < 1e-9 * max(1, abs(g)) or abs(abs(p) - abs(g)) < 1e-9 * max(1, abs(g)) for p in pred_nums)


def score(task: dict, out: dict) -> dict:
    answer, refused = out["answer"], out["refused"]
    if not task["answerable"]:
        ok = refused
        return {"success": float(ok), "partial": float(ok), "missing": [], "failure": None if ok else "answered_unanswerable"}
    nums = numbers_in(answer)
    missing = [g for g in task["gold_numbers"] if not found(g, nums)]
    got = 1 - len(missing) / len(task["gold_numbers"])
    if not missing:
        failure = None
    elif refused:
        failure = "refused"
    elif got == 0:
        failure = "no_gold_number"
    else:
        failure = "partial_numbers"
    return {"success": float(not missing), "partial": round(got, 3), "missing": missing, "failure": failure}


def pages_hit(task: dict, out: dict) -> float | None:
    gold = [tuple(p) for p in task["gold_pages"]]
    if not gold:
        return None
    seen = set(map(tuple, out.get("retrieved", [])))
    return round(sum(g in seen for g in gold) / len(gold), 3)


def run(mode: str, ids: list[str] | None, cats: list[str] | None) -> Path:
    from telaah.agent import run_agent
    from telaah.answer import ask
    from telaah.router import run_routed

    fn = {"rag": ask, "agent": run_agent, "router": run_routed}[mode]
    rows = [json.loads(l) for l in (HERE / "agent_tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    if cats:
        rows = [r for r in rows if r["category"] in cats]
    results = []
    for n, t in enumerate(rows, 1):
        print(f"[{n}/{len(rows)}] {t['id']} {t['category']}", flush=True)
        t0 = time.time()
        out = fn(t["question"])
        sec = round(time.time() - t0, 1)
        s = score(t, out)
        r = {"id": t["id"], "category": t["category"], "seconds": sec, "steps": len(out.get("steps") or []) or 1,
             "min_steps": t["min_steps"], "route": out.get("route", mode), "verified": out.get("verified"),
             "pages_hit": pages_hit(t, out), "answer": out["answer"], **s}
        results.append(r)
        print(f"    {sec}s success={s['success']} partial={s['partial']} failure={s['failure']}", flush=True)
    from telaah import config

    log = {"config": {"mode": mode, "llm": config.LLM_MODEL, "base_url": config.LLM_BASE_URL},
           "summary": summarize(results), "results": results}
    out_dir = HERE / "runs"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"tasks-{mode}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log["summary"]["overall"], indent=2))
    print("saved", path)
    return path


def mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def summarize(results: list[dict]) -> dict:
    def block(rs):
        fails = defaultdict(int)
        for r in rs:
            if r["failure"]:
                fails[r["failure"]] += 1
        return {"n": len(rs), "success": mean([r["success"] for r in rs]), "partial": mean([r["partial"] for r in rs]),
                "pages_hit": mean([r["pages_hit"] for r in rs]), "steps": mean([r["steps"] for r in rs]),
                "seconds": mean([r["seconds"] for r in rs]), "failures": dict(fails)}

    by = defaultdict(list)
    for r in results:
        by[r["category"]].append(r)
    return {"overall": block(results), "by_category": {c: block(rs) for c, rs in by.items()}}


def compare(paths: list[str]) -> None:
    logs = [(Path(p).stem, json.loads(Path(p).read_text(encoding="utf-8"))) for p in paths]
    cats = sorted({c for _, l in logs for c in l["summary"]["by_category"]})
    print("| run | n | success | partial | pages_hit | steps | s/task |  " + " | ".join(cats) + " |")
    print("|" + "---|" * (7 + len(cats) + 0) + "---|")
    for name, l in logs:
        o = l["summary"]["overall"]
        per = " | ".join(str(l["summary"]["by_category"].get(c, {}).get("success")) for c in cats)
        print(f"| {name} | {o['n']} | {o['success']} | {o['partial']} | {o['pages_hit']} | {o['steps']} | {o['seconds']} | {per} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rag", "agent", "router"], default="router")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--cats", nargs="*")
    ap.add_argument("--compare", nargs="*", help="run JSONs to compare (no model calls)")
    a = ap.parse_args()
    if a.compare:
        compare(a.compare)
    else:
        sys.path.insert(0, str(HERE.parent / "src"))
        run(a.mode, a.ids, a.cats)
