"""Score the facts table against the gold facts of eval/agent_tasks.jsonl (the table is built without them).

    .venv/Scripts/python eval/check_facts.py [--build] [-v]

value_ok: lookup returns the gold value (same number, any page); page_ok: and the gold page.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from telaah import facts

HERE = Path(__file__).parent
METRIC = {"aset": "total_aset", "laba": "laba", "npl": "npl_gross", "ldr": "ldr", "car": "car", "nim": "nim",
          "bopo": "bopo", "casa": "casa", "tier1": "tier1"}


def gold_facts() -> list[dict]:
    seen = {}
    for line in open(HERE / "agent_tasks.jsonl", encoding="utf-8"):
        for f in json.loads(line)["gold_facts"]:
            if f["label"] in METRIC and facts.REPORT_RE.match(f["doc"]):
                seen[(f["doc"], f["label"], f["year"])] = f
    return list(seen.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("-v", action="store_true", help="print every miss")
    a = ap.parse_args()
    if a.build or not facts.DB_PATH.exists():
        print(facts.build(), "facts built")
    c, by = Counter(), Counter()
    for f in gold_facts():
        bank, ry = f["doc"].split("_")
        hit = facts.lookup(bank, METRIC[f["label"]], f["year"], int(ry))
        gold = facts.parse_num(f["value"], facts.number_style([f["value"]]) if bank != "bni" else "en")
        ok = hit is not None and gold is not None and abs(hit["value"] - gold) < 1e-9
        page = ok and hit["page"] == f["page"]
        c["n"] += 1
        c["value_ok"] += ok
        c["page_ok"] += page
        c["contested"] += bool(hit and hit["alternatives"])
        by[(f["label"], ok)] += 1
        if a.v and not ok:
            got = None if hit is None else (hit["value"], hit["doc"], hit["page"], hit["label"], hit["alternatives"])
            print(f"MISS {bank} {f['label']} {f['year']}: gold {f['value']} p{f['page']} -> {got}")
    print({k: c[k] for k in ("n", "value_ok", "page_ok", "contested")},
          f"value acc {c['value_ok'] / c['n']:.3f}")
    print({m: f"{by[(m, True)]}/{by[(m, True)] + by[(m, False)]}" for m in METRIC})


if __name__ == "__main__":
    main()
