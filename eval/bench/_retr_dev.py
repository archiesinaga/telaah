"""Retrieval-only recall@5 on dev (no LLM) per pipeline variant, scored with extra gold."""
import collections, json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from common import HERE, read_jsonl
from retrieval_eval import VARIANTS
from telaah.metrics import recall_at_k
from telaah.retrieve import retrieve

from telaah.metrics import load_extra_gold
extra = load_extra_gold(HERE / "extra_gold_dev.json", read_jsonl(HERE / "dev.jsonl"))
rows = [q for q in read_jsonl(HERE / "dev.jsonl") if q["answerable"] and q["source"] != "seed"
        and q["type"] in {"text_fact", "table_lookup", "calculation", "regulation"}]
for name in sys.argv[1:]:
    by = collections.defaultdict(list)
    for q in rows:
        got = [(c["doc_id"], c["page"]) for c in retrieve(q["question"], **VARIANTS[name])]
        gold = [tuple(g) for g in q["gold_pages"] + extra.get(q["id"], [])]
        by[q["type"]].append(recall_at_k(got, gold))
    allv = [v for vs in by.values() for v in vs]
    print(f"{name:9} all={sum(allv)/len(allv):.3f}  " + "  ".join(f"{t}={sum(v)/len(v):.3f}" for t, v in sorted(by.items())), flush=True)
