"""Where does the gold page rank? recall@5/10/25 on dev (extra gold) with the current retrieval."""
import collections, json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from common import HERE, read_jsonl
import telaah.retrieve as R

extra = json.loads((HERE / "extra_gold_dev.json").read_text(encoding="utf-8"))
rows = [q for q in read_jsonl(HERE / "dev.jsonl") if q["answerable"] and q["source"] != "seed"
        and q["type"] in {"text_fact", "table_lookup", "calculation", "regulation"}]
out, by = [], collections.defaultdict(lambda: collections.Counter())
for q in rows:
    got = [(c["doc_id"], c["page"]) for c in R.retrieve(q["question"], k=25)]
    gold = {tuple(g) for g in q["gold_pages"] + extra.get(q["id"], [])}
    rank = next((i + 1 for i, g in enumerate(got) if g in gold), None)
    for k in (5, 10, 25):
        by[q["type"]][k] += bool(rank and rank <= k)
    by[q["type"]]["n"] += 1
    if not rank or rank > 5:
        out.append({"id": q["id"], "type": q["type"], "rank": rank, "q": q["question"], "gold": q["gold_pages"], "ans": q["gold_answer"], "got": got[:8]})
for t, c in sorted(by.items()):
    print(f"{t:13} n={c['n']:3} @5={c[5]/c['n']:.2f} @10={c[10]/c['n']:.2f} @25={c[25]/c['n']:.2f}")
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "not in top 5")
