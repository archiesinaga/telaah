"""Run seed questions; log per-metric scores to eval/runs/<timestamp>.json."""
import json
import time
from pathlib import Path

from telaah import config
from telaah.answer import ask
from telaah.judge import judge_correctness, judge_faithfulness
from telaah.metrics import citation_accuracy, numeric_match, recall_at_k, refusal_correct

HERE = Path(__file__).parent
KEYS = ["recall@5", "citation_acc", "refusal_acc", "correct_numeric", "correct_judge", "faithful", "latency_s"]


def run(path: Path = HERE / "seed_questions.jsonl", agent: bool = False, types: list[str] | None = None,
        router: bool = False, ids: list[str] | None = None) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if types:
        rows = [q for q in rows if q["type"] in types]
    if ids:
        rows = [q for q in rows if q["id"] in ids]
    agent = agent or router
    if router:
        from telaah.router import run_routed as answer_fn
    elif agent:
        from telaah.agent import run_agent as answer_fn
    else:
        answer_fn = ask
    results = []
    for n, q in enumerate(rows, 1):
        print(f"[{n}/{len(rows)}] {q['id']} {q['type']}", flush=True)
        gold = [tuple(g) for g in q["gold_pages"]]
        t0 = time.time()
        out = answer_fn(q["question"])
        correct = None
        if q["answerable"] and q.get("numeric"):
            correct = float(numeric_match(out["answer"], q["gold_answer"]))
        judged = q["answerable"] and not out["refused"]
        correct_judge = (
            judge_correctness(q["question"], q["gold_answer"], out["answer"]) if judged else None
        )
        faithful = judge_faithfulness(out["answer"], out["context"]) if judged else None
        results.append({
            "id": q["id"],
            "type": q["type"],
            "latency_s": round(time.time() - t0, 2),
            "recall@5": recall_at_k(out["retrieved"], gold),
            "citation_acc": citation_accuracy(out["citations"], gold),
            "refusal_acc": refusal_correct(out["refused"], q["answerable"]),
            "correct_numeric": correct,
            "correct_judge": correct_judge,
            "faithful": faithful,
            "answer": out["answer"],
            **({"verified": out["verified"], "steps": len(out["steps"])} if agent else {}),
            **({"route": out["route"]} if router else {}),
        })
        r = results[-1]
        print(f"    {r['latency_s']}s recall={r['recall@5']} refused={out['refused']}", flush=True)

    def mean(k: str):
        v = [r[k] for r in results if r[k] is not None]
        return round(sum(v) / len(v), 3) if v else None

    summary = {k: mean(k) for k in KEYS}
    log = {
        "config": {"agent": agent, "router": router, "llm": config.LLM_MODEL, "embed": config.EMBED_MODEL, "k": config.TOP_K},
        "summary": summary,
        "results": results,
    }
    out_dir = HERE / "runs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return log


if __name__ == "__main__":
    run()
