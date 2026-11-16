"""Run seed questions; log per-metric scores to eval/runs/<timestamp>.json."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from telaah import config
from telaah.answer import ask
from telaah.judge import judge_correctness, judge_faithfulness
from telaah.metrics import citation_accuracy, numeric_match, recall_at_k_groups, refusal_correct

HERE = Path(__file__).parent
KEYS = ["recall@5", "citation_acc", "refusal_acc", "correct_numeric", "correct_judge", "faithful", "latency_s"]


def run(path: Path = HERE / "seed_questions.jsonl", agent: bool = False, types: list[str] | None = None,
        router: bool = False, ids: list[str] | None = None, resume: str | None = None, judge_on_fail: bool = False,
        workers: int = 1, no_rag: bool = False) -> dict:
    """Each finished question is appended to a `.partial.jsonl` file, so a crash (memory, API quota) loses
    one question: rerun with `--resume <that file>` and only the missing ones are run.
    `judge_on_fail`: skip the LLM judges (correct_judge, faithful -> None) when the cheap checks already pass
    (numeric match, gold page retrieved and cited); non-numeric questions are always judged.
    `workers` > 1 runs that many questions at once (API-bound, so threads help); latency_s is then wall time
    under contention, not comparable with a workers=1 run."""
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if types:
        rows = [q for q in rows if q["type"] in types]
    if ids:
        rows = [q for q in rows if q["id"] in ids]
    agent = (agent or router) and not no_rag
    router = router and not no_rag
    if no_rag:  # closed-book baseline: no retrieval, so recall and faithfulness are not scored
        from telaah.answer import ask_no_rag as answer_fn
    elif router:
        from telaah.router import run_routed as answer_fn
    elif agent:
        from telaah.agent import run_agent as answer_fn
    else:
        answer_fn = ask
    out_dir = HERE / "runs"
    out_dir.mkdir(exist_ok=True)
    prefix = "" if path.name == "seed_questions.jsonl" else f"bench-{path.stem}-"
    if no_rag:
        prefix += "norag-"  # bench-test-*: never read per question
    partial = Path(resume) if resume else out_dir / f"{prefix}{time.strftime('%Y%m%d-%H%M%S')}.partial.jsonl"
    results = [json.loads(l) for l in partial.read_text(encoding="utf-8").splitlines() if l.strip()] if resume else []
    extra_path = path.with_name(f"extra_gold_{path.stem}.json")  # duplicated-fact pages, see bench/extra_gold.py
    extra_gold = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {}
    finished = {r["id"] for r in results}
    print(f"{len(finished)} questions already done, {len(rows) - len(finished)} to run; progress file {partial}", flush=True)
    lock = threading.Lock()

    def one(n: int, q: dict) -> None:
        with lock:
            print(f"[{n}/{len(rows)}] {q['id']} {q['type']}", flush=True)
        gold = [tuple(g) for g in q["gold_pages"] + extra_gold.get(q["id"], [])]
        t0 = time.time()
        out = answer_fn(q["question"])
        correct = None
        if q["answerable"] and q.get("numeric"):
            correct = float(numeric_match(out["answer"], q["gold_answer"]))
        groups = out.get("retrieved_groups") or [out["retrieved"]]
        recall = None if no_rag else recall_at_k_groups(groups, gold)
        cite = citation_accuracy(out["citations"], gold)
        passed = correct == 1.0 and recall == 1 and cite == 1
        judged = q["answerable"] and not out["refused"] and not (judge_on_fail and passed)
        correct_judge = (
            judge_correctness(q["question"], q["gold_answer"], out["answer"]) if judged else None
        )
        faithful = judge_faithfulness(out["answer"], out["context"]) if judged and not no_rag else None
        r = {
            "id": q["id"],
            "type": q["type"],
            "latency_s": round(time.time() - t0, 2),
            "recall@5": recall,
            "citation_acc": cite,
            "refusal_acc": refusal_correct(out["refused"], q["answerable"]),
            "correct_numeric": correct,
            "correct_judge": correct_judge,
            "faithful": faithful,
            "answer": out["answer"],
            "retrieved_top": [[list(p) for p in g[:5]] for g in groups],  # lets a later run be re-scored offline
            **({"verified": out["verified"], "steps": len(out["steps"])} if agent else {}),
            **({"route": out["route"]} if router else {}),
        }
        with lock:
            results.append(r)
            with partial.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"    {q['id']} {r['latency_s']}s recall={r['recall@5']} refused={out['refused']}", flush=True)

    todo = [(n, q) for n, q in enumerate(rows, 1) if q["id"] not in finished]
    if workers > 1:
        from telaah.index import client, embedder

        client(), embedder()  # lru_cache is not atomic: warm once so threads don't each open the local Qdrant store
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for fut in [pool.submit(one, n, q) for n, q in todo]:
                fut.result()  # re-raise a worker's error; finished questions are already in the partial file
    else:
        for n, q in todo:
            one(n, q)

    order = {q["id"]: i for i, q in enumerate(rows)}
    results.sort(key=lambda r: order.get(r["id"], len(order)))  # threads finish out of order

    def mean(k: str):
        v = [r[k] for r in results if r[k] is not None]
        return round(sum(v) / len(v), 3) if v else None

    summary = {k: mean(k) for k in KEYS}
    by_type = {}
    for t in sorted({r["type"] for r in results}):
        of_type = [r for r in results if r["type"] == t]
        by_type[t] = {"n": len(of_type)}
        for k in KEYS:
            v = [r[k] for r in of_type if r[k] is not None]
            by_type[t][k] = round(sum(v) / len(v), 3) if v else None
    log = {
        "config": {"agent": agent, "router": router, "no_rag": no_rag, "llm": config.LLM_MODEL, "embed": config.EMBED_MODEL, "k": config.TOP_K,
                   "questions": path.name},
        "summary": summary,
        "by_type": by_type,
        "results": results,
    }
    partial.with_name(partial.name.replace(".partial.jsonl", ".json")).write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return log


if __name__ == "__main__":
    run()
