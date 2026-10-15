"""Retrieval-only ablation (no LLM): recall@5 per question type for each pipeline variant."""
import collections
import json
import sys
from pathlib import Path

from telaah.metrics import numeric_match, recall_at_k
from telaah.retrieve import retrieve

HERE = Path(__file__).parent
VARIANTS = {
    "dense": dict(filter_docs=False, hybrid=False, rerank=False, colpali=False),
    "+filter": dict(filter_docs=True, hybrid=False, rerank=False, colpali=False),
    "+bm25": dict(filter_docs=True, hybrid=True, rerank=False, colpali=False),
    "+rerank": dict(filter_docs=True, hybrid=True, rerank=True, colpali=False),
    "+quota": dict(filter_docs=True, hybrid=True, rerank=False, summary=False, colpali=False),
    "+summary": dict(filter_docs=True, hybrid=True, rerank=False, summary=True, colpali=False),
    "+auto": dict(filter_docs=True, hybrid=True, rerank=False, summary=True, colpali=True),  # the default
    "+colpali": dict(filter_docs=True, hybrid=True, rerank=False, summary=True, colpali=True),
    "+colpali2": dict(filter_docs=True, hybrid=True, rerank=False, summary=True, colpali=True, colpali_weight=2),
    "+colpali3": dict(filter_docs=True, hybrid=True, rerank=False, summary=True, colpali=True, colpali_weight=3),
}


def main(names: list[str]) -> None:
    rows = [json.loads(l) for l in (HERE / "seed_questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [q for q in rows if q["answerable"]]
    for name in names:
        by = collections.defaultdict(list)
        ans = collections.defaultdict(list)
        every = collections.defaultdict(list)  # all gold pages retrieved (cross_doc needs both)
        sizes = []
        for q in rows:
            chunks = retrieve(q["question"], **VARIANTS[name])
            got = [(c["doc_id"], c["page"]) for c in chunks]
            gold = [tuple(g) for g in q["gold_pages"]]
            by[q["type"]].append(recall_at_k(got, gold))
            every[q["type"]].append(float(all(g in got for g in gold)))
            sizes.append(len(got))
            if q.get("numeric") and q["type"] != "cross_doc":
                text = " ".join(c["text"] for c in chunks)
                ans[q["type"]].append(float(numeric_match(text, q["gold_answer"])))
        allv = [v for vs in by.values() for v in vs]
        cells = "  ".join(f"{t}={sum(v)/len(v):.2f}" for t, v in by.items())
        acells = "  ".join(f"{t}={sum(v)/len(v):.2f}" for t, v in ans.items())
        print(f"{name:8s} overall={sum(allv)/len(allv):.2f}  {cells}", flush=True)
        print(f"{'':8s} answer-in-context: {acells}", flush=True)
        ecells = "  ".join(f"{t}={sum(v)/len(v):.2f}" for t, v in every.items())
        print(f"{'':8s} all-gold-in-context: {ecells}  (max pages {max(sizes)})", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
