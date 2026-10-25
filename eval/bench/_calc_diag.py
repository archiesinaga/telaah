"""Calculation diagnosis (dev only): gold check on the page, step retrieval, step answers -> one bucket each."""
import collections, json, re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from common import HERE, ROOT, pages, read_jsonl
from telaah.retrieve import retrieve

run = {r["id"]: r for r in json.load(open(ROOT / "eval/runs/bench-dev-20261022-001829.json"))["results"]}
dev = {q["question"]: q for q in read_jsonl(HERE / "dev.jsonl") if q["type"] == "calculation"}
rev = {r["question"]: r for r in read_jsonl(HERE / "reviewed_dev.jsonl") if r.get("type") == "calculation" and r["decision"] == "accept"}
traces = {}
for f in sorted((ROOT / "data/agent_traces").glob("2026102[12].jsonl")):
    for t in read_jsonl(f):
        traces[t["question"]] = t  # latest wins
extra = json.loads((HERE / "extra_gold_dev.json").read_text(encoding="utf-8"))


def digits(s): return {re.sub(r"\D", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", s)}


out = []
for qt, q in dev.items():
    r, rv, t = run[q["id"]], rev.get(qt), traces.get(qt)
    gold = [tuple(g) for g in q["gold_pages"] + extra.get(q["id"], [])]
    figs = [re.sub(r"\D", "", f["value"]) for f in (rv or {}).get("figures", [])]
    on_page = [any(fd in digits(pages(d).get(p, "")) for d, p in gold) for fd in figs]
    steps = (t or {}).get("steps", []) if r["route"] == "agent" else []
    step_info = []
    for s in steps:
        got = [(c["doc_id"], c["page"]) for c in retrieve(s["q"])]
        step_info.append({"q": s["q"], "status": s["status"], "hit": any(g in got for g in gold),
                          "has_fig": bool(digits(s["answer"]) & set(figs)), "ans": s["answer"][:90]})
    if r["route"] == "rag":
        got = [(c["doc_id"], c["page"]) for c in retrieve(qt)]
        step_info.append({"q": "(rag)", "hit": any(g in got for g in gold), "status": "-", "has_fig": None, "ans": r["answer"][:90]})
    if r["correct_numeric"] == 1:
        b = "ok"
    elif figs and not all(on_page):
        b = "gold: figure not on gold page"
    elif r["route"] == "agent" and not t:
        b = "no trace"
    elif r["route"] == "agent" and len(steps) != len(figs):
        b = f"plan: {len(steps)} steps for {len(figs)} figures"
    elif any(not s["hit"] for s in step_info):
        b = "retrieval: a step misses the page"
    elif r["route"] == "agent" and any(not s["has_fig"] for s in step_info):
        b = "read: page found, step value wrong/refused"
    else:
        b = "compute/compose: steps right, final wrong"
    out.append({"id": q["id"], "route": r["route"], "bucket": b, "op": (rv or {}).get("op"), "q": qt, "gold": q["gold_answer"],
                "figs": figs, "on_page": on_page, "steps": step_info, "answer": r["answer"][:120]})
c = collections.Counter(o["bucket"] for o in out)
for k, v in c.most_common():
    print(f"{v:3}  {k}")
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
