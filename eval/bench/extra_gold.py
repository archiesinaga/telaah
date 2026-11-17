"""Find other pages of the same report that state a dev question's gold answer (duplicated facts).

A fact (an executive's age, a table value) is often printed on several pages; the drafter saw only one, so a
correct answer citing another page counts as recall 0 / citation 0. This adds those pages as extra gold.

    .venv/Scripts/python eval/bench/extra_gold.py                    # writes extra_gold_dev.json, prints stats
    .venv/Scripts/python eval/bench/extra_gold.py --rescore <run.json>   # citation_acc with extra gold
    .venv/Scripts/python eval/bench/extra_gold.py --remap    # after dev.jsonl is rebuilt: re-key entries by question text

Format: {id: {"q": question text, "pages": [[doc, page], ...]}}. Eval refuses the file if a text no longer matches
its id (see telaah.metrics.load_extra_gold). Note: a plain rebuild (no flag) overwrites hand edits (bd0224 added).

Dev only: reads dev.jsonl, never test. Seed questions (tuned) and cross_doc/unanswerable are skipped.
A page counts when it has the gold answer text AND enough of the question's content words (same fact, not a
coincidental number). Short golds ("62 tahun", "CISO") need a higher word overlap.
"""
import argparse
import json
import re

from common import HERE, pages, read_jsonl
from telaah.answer import parse_citations
from telaah.metrics import load_extra_gold, remap_extra_gold

OUT = HERE / "extra_gold_dev.json"
MAX_EXTRA = 5  # more matches than this means a generic gold ("Dewan Komisaris", "2 kali"): drop, not a duplicated fact
STOP = set("""berapakah berapa apakah apa siapa yang dalam pada untuk dengan dari menurut berdasarkan laporan tahunan
perseroan tbk persero bank dan atau oleh adalah sebagai tahun nilai jumlah per sebesar terdapat dapat tersebut
mana kapan bagaimana mengapa disebutkan dijelaskan disusun dilakukan digunakan""".split())
NUM = re.compile(r"\d[\d.,]*\d|\d")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def words(question: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", norm(question)) if len(w) >= 5 and w not in STOP}


def gold_token(gold: str) -> tuple[str, bool] | None:
    """(text to look for, is_strong). Numbers are matched as written, with digit boundaries."""
    nums = NUM.findall(gold)
    if nums:
        tok = max(nums, key=len)
        return tok, len(tok) >= 5
    tok = norm(gold).strip(" .")
    return (tok, len(tok) >= 8) if len(tok) >= 4 else None


def has(page: str, tok: str, numeric: bool) -> bool:
    if numeric:
        return re.search(rf"(?<![\d.,]){re.escape(tok)}(?![\d]|[.,]\d)", page) is not None
    return tok in page


def find(q: dict) -> list[list]:
    t = gold_token(q["gold_answer"])
    if not t:
        return []
    tok, strong = t
    numeric = bool(NUM.fullmatch(tok))
    need = 0.5 if strong else 0.8
    qw = words(q["question"])
    gold = {(d, p) for d, p in q["gold_pages"]}
    found = []
    for doc in {d for d, _ in gold}:
        for p, text in pages(doc).items():
            if (doc, p) in gold:
                continue
            t = norm(text)
            if has(t if not numeric else text, tok, numeric) and qw and len(qw & set(re.findall(r"[a-z0-9]+", t))) / len(qw) >= need:
                found.append([doc, p])
    return found


def build() -> dict[str, dict]:
    rows = [q for q in read_jsonl(HERE / "dev.jsonl")
            if q["answerable"] and q["source"] != "seed" and q["type"] in {"text_fact", "table_lookup", "calculation", "regulation", "chart"}]
    extra = {q["id"]: {"q": q["question"], "pages": f} for q in rows if 0 < len(f := find(q)) <= MAX_EXTRA}
    write(extra)
    print(f"{len(rows)} dev questions checked, {len(extra)} gained pages (<= MAX_EXTRA each), "
          f"{sum(len(e['pages']) for e in extra.values())} pages added")
    return extra


def write(extra: dict) -> None:
    OUT.write_text(json.dumps(extra, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def remap() -> None:
    raw = json.loads(OUT.read_text(encoding="utf-8"))
    new, dropped = remap_extra_gold(raw, read_jsonl(HERE / "dev.jsonl"))
    moved = sum(1 for i, e in raw.items() if i not in dropped and new.get(i) is not e)
    write(new)
    print(f"{len(new)} entries kept ({moved} re-keyed), {len(dropped)} dropped (question gone): {dropped}")


def rescore(run_path: str) -> None:
    dev_rows = read_jsonl(HERE / "dev.jsonl")
    extra = load_extra_gold(OUT, dev_rows)
    dev = {q["id"]: q for q in dev_rows}
    res = json.load(open(run_path, encoding="utf-8"))["results"]
    by: dict[str, list] = {}
    for r in res:
        q = dev[r["id"]]
        gold = {tuple(g) for g in q["gold_pages"]} | {tuple(g) for g in extra.get(r["id"], [])}
        cited = parse_citations(r["answer"])
        new = float(bool(cited) and all(c in gold for c in cited)) if q["answerable"] else r["citation_acc"]
        by.setdefault(r["type"], []).append((r["citation_acc"], new))
    for t, v in sorted(by.items()):
        print(f"{t:13} n={len(v):3} citation_acc {sum(a for a, _ in v) / len(v):.3f} -> {sum(b for _, b in v) / len(v):.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", help="eval/runs/bench-dev-*.json")
    ap.add_argument("--remap", action="store_true", help="re-key entries by question text after a dev rebuild")
    a = ap.parse_args()
    if a.remap:
        remap()
    elif a.rescore:
        rescore(a.rescore)
    else:
        build()
