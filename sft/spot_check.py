"""Write sft/spot_check.md: a fixed random sample of sft.jsonl for a human check (DESIGN.md step 5).

Each answer item shows the question, the training answer and the lines of the cited page that hold the value
(table rows come with their header). Mark each item OK / WRONG and note why.

    .venv/Scripts/python sft/spot_check.py
"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "eval" / "bench"))
from common import read_jsonl  # noqa: E402

PLAN = {"calculation": 13, "table_lookup": 13, "text_fact": 6, "chart": 5, "regulation": 5}  # answers; + refusals
REFUSALS = 8
OUT = HERE / "spot_check.md"


def source_lines(block: str, value: str) -> list[str]:
    lines = block.split("\n")
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 2:
        hit = [i for i, line in enumerate(lines) if digits in re.sub(r"\D", "", line)]
    else:
        hit = [i for i, line in enumerate(lines) if value.lower()[:30] in line.lower()]
    header = next((line for line in lines if line.startswith("|") and re.search(r"20\d\d", line)), "")
    rows = [lines[i] for i in hit[:2]]
    return ([header] if header and hit and lines[hit[0]].startswith("|") and header not in rows else []) + rows


def main() -> None:
    drafts = {r["cid"]: r["draft"] for r in read_jsonl(HERE / "drafts.jsonl")}
    rows = list(read_jsonl(HERE / "sft.jsonl"))
    rng = random.Random(29)
    picked = []
    for kind, n in PLAN.items():
        pool = [r for r in rows if r["mix"].startswith("answer") and r["kind"] == kind]
        picked += rng.sample(pool, min(n, len(pool)))
    picked += rng.sample([r for r in rows if r["mix"].startswith("refusal")], REFUSALS)
    out = ["# SFT spot check", "", f"{len(picked)} examples from sft/sft.jsonl. Mark each: OK / WRONG + why.", ""]
    for i, r in enumerate(picked, 1):
        user = r["messages"][1]["content"]
        ctx, question = user.split("\n\nPertanyaan: ", 1)
        doc, page = r["page"]
        out += [f"## {i}. {r['cid']} | {r['kind']} | {r['mix']}", "", f"**Q:** {question}", "",
                f"**A:** {r['messages'][2]['content']}", ""]
        if r["mix"].startswith("answer"):
            head = f"[{doc} p.{page}]\n"
            block = ctx.split(head, 1)[1] if head in ctx else ""
            block = re.split(r"\n\n\[\w+ p\.\d+\]\n", block, maxsplit=1)[0]
            out += [f"Source [{doc} p.{page}]:", "```"] + [ln[:400] for ln in source_lines(block, str(drafts[r["cid"]]["value"]))] + ["```"]
        else:
            pages = re.findall(r"^\[(\w+ p\.\d+)\]$", ctx, re.M)
            out += [f"Context pages (the value was on [{doc} p.{page}], removed or bank swapped): {', '.join(pages)}"]
        out += ["", "Verdict: ", ""]
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(picked)} examples -> {OUT}")


if __name__ == "__main__":
    main()
