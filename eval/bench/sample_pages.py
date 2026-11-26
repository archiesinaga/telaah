"""Sample the pages the drafter writes questions from -> eval/bench/pages.jsonl (see eval/BENCHMARK.md).

Each sampled page (or page pair) is used once, by one question kind, and its split is fixed here, before any
draft exists. Deterministic (seed in common.SEED); rerunning rewrites the same file.

    .venv/Scripts/python eval/bench/sample_pages.py
"""
import json
import random
import re
import sys
from collections import Counter

from common import BANK, HERE, SEED, docs, read_jsonl, is_regulation, is_report, page_split, pages, split_of

OUT = HERE / "pages.jsonl"
# pages (pairs for cross_doc) per kind: about 1.4x the new questions needed, 2 drafts per page
COUNT = {"text_fact": 75, "table_lookup": 75, "calculation": 63, "chart": 120, "regulation": 42, "cross_doc": 115}
TEST_SHARE_PAIRS = 0.25
NUM_LINE = re.compile(r"^\|.*\d", re.M)
YEAR = re.compile(r"\b20[12]\d\b")
CHARTISH = re.compile(r"grafik|chart|diagram|pertumbuhan|triliun|miliar|%", re.I)
TOC = re.compile(r"daftar isi|table of contents", re.I)
# figures that most banks publish, to pair pages across banks
TERMS = ["Kredit yang Diberikan", "Dana Pihak Ketiga", "Giro", "Tabungan", "Deposito", "Jumlah Karyawan",
         "Jaringan Kantor", "ATM", "CASA", "Liquidity Coverage Ratio", "Net Stable Funding Ratio", "Laba Bersih",
         "Total Aset", "Ekuitas", "Cost to Income", "Pendapatan Bunga Bersih", "Kredit UMKM", "Pembiayaan Berkelanjutan",
         "Agen", "Pendapatan Non Bunga", "Beban Operasional", "Dividen", "Kredit Konsumer", "Kredit Korporasi"]


def kind_pools() -> dict[str, list[tuple[str, int]]]:
    pools = {k: [] for k in COUNT if k != "cross_doc"}
    for doc in docs():
        for page, text in pages(doc).items():
            if page <= 4 or TOC.search(text):
                continue
            nums = len(NUM_LINE.findall(text))
            if is_regulation(doc):
                if len(text) >= 800:
                    pools["regulation"].append((doc, page))
            elif is_report(doc):
                if nums == 0 and len(text) >= 1200 and "<!-- image -->" not in text[:200]:
                    pools["text_fact"].append((doc, page))
                elif nums >= 4:
                    years = len(set(YEAR.findall("\n".join(l for l in text.splitlines() if l.startswith("|")))))
                    pools["calculation" if years >= 2 else "table_lookup"].append((doc, page))
                if "<!-- image -->" in text and nums < 3 and CHARTISH.search(text) and re.search(r"\d", text):
                    pools["chart"].append((doc, page))
    return pools


def round_robin(pool: list[tuple[str, int]], n: int, used: set, rng: random.Random) -> list[tuple[str, int]]:
    """n pages spread evenly over documents, none used before."""
    by_doc: dict[str, list] = {}
    for dp in pool:
        by_doc.setdefault(dp[0], []).append(dp)
    for v in by_doc.values():
        rng.shuffle(v)
    out, order = [], sorted(by_doc)
    while len(out) < n and any(by_doc.values()):
        for d in order:
            while by_doc[d] and by_doc[d][-1] in used:
                by_doc[d].pop()
            if by_doc[d] and len(out) < n:
                out.append(by_doc[d].pop())
                used.add(out[-1])
    return out


def term_pages(term: str) -> dict[str, list[int]]:
    """Report -> pages with the term in a table row."""
    pat = re.compile(r"^\|[^|\n]*" + re.escape(term), re.I | re.M)
    out = {}
    for doc in filter(is_report, docs()):
        hits = [p for p, t in pages(doc).items() if p > 4 and pat.search(t)]
        if hits:
            out[doc] = hits
    return out


def pairs(n: int, used: set, rng: random.Random, test_only: bool = False) -> list[dict]:
    """Two banks, same report year, same term; the split is chosen first, then both pages come from it."""
    by_term = {t: term_pages(t) for t in TERMS}
    out, tries = [], 0
    while len(out) < n and tries < 20000:
        tries += 1
        split = "test" if test_only or len(out) % round(1 / TEST_SHARE_PAIRS) == 0 else "dev"
        term = rng.choice(TERMS)
        year = rng.choice(["2024", "2025"])
        cands = {d: [p for p in ps if page_split(d, p) == split and (d, p) not in used]
                 for d, ps in by_term[term].items() if d.endswith(year)}
        cands = {d: ps for d, ps in cands.items() if ps}
        if len(cands) < 2:
            continue
        a, b = rng.sample(sorted(cands), 2)
        dp = [(a, rng.choice(cands[a])), (b, rng.choice(cands[b]))]
        used.update(dp)
        out.append({"kind": "cross_doc", "pages": dp, "split": split, "term": term})
    return out


COUNT2 = {"text_fact": 0, "table_lookup": 60, "calculation": 100, "chart": 180, "regulation": 30, "cross_doc": 60}
# round 3 (2026-11-16): dev only, to fill the last dev gaps (table_lookup 6, chart 5); test pages are dropped
COUNT3 = {"text_fact": 0, "table_lookup": 40, "calculation": 0, "chart": 80, "regulation": 0, "cross_doc": 0}
# round 4 (2026-11-26): test v2, TEST pages only. Test v1 was retired (Claude read it, BENCHMARK.md Status), so
# every page used by rounds 1-3 or referenced anywhere in the archived test v1 files is excluded. Pages per kind
# ~1.3-1.5x the test quota (text 30, table 30, chart 23, calculation 22, regulation 15, cross_doc 22).
COUNT4 = {"text_fact": 40, "table_lookup": 40, "calculation": 35, "chart": 40, "regulation": 22, "cross_doc": 32}
ARCHIVE_V1 = HERE / "archive_test_v1"


def referenced_pages(obj, out: set) -> set:
    """Every (doc, page) anywhere in a JSON value: [doc, page] pairs and {"doc", "page"} dicts. Never printed."""
    known = set(docs())
    if isinstance(obj, dict):
        if isinstance(obj.get("doc"), str) and str(obj.get("page", "")).isdigit():
            out.add((obj["doc"], int(obj["page"])))
        for v in obj.values():
            referenced_pages(v, out)
    elif isinstance(obj, list):
        if len(obj) == 2 and isinstance(obj[0], str) and obj[0] in known and str(obj[1]).isdigit():
            out.add((obj[0], int(obj[1])))
        else:
            for v in obj:
                referenced_pages(v, out)
    return out


def test_v1_pages() -> set:
    """Pages a Claude session may have seen through test v1 (questions, golds, extra gold pages)."""
    seen: set = set()
    for path in sorted(ARCHIVE_V1.glob("*.jsonl")):
        for row in read_jsonl(path):
            referenced_pages(row, seen)
    return seen


def main() -> None:
    """Round 1 (default) or `--round 2`: new pages for the types still short, never reusing a page of round 1.
    Round 2 cross_doc pairs are test-only (dev cross_doc comes from the facts table, crossdoc_from_facts.py)."""
    rnd = int(sys.argv[sys.argv.index("--round") + 1]) if "--round" in sys.argv else 1
    rng = random.Random(SEED + (rnd - 1) * 2)
    used: set = set()
    out_path, prefix, count = OUT, "p", COUNT
    if rnd == 2:
        used = {tuple(dp) for r in read_jsonl(OUT) for dp in r["pages"]}
        out_path, prefix, count = HERE / "pages2.jsonl", "q", COUNT2
    if rnd == 3:
        used = {tuple(dp) for f in ("pages.jsonl", "pages2.jsonl") for r in read_jsonl(HERE / f) for dp in r["pages"]}
        out_path, prefix, count = HERE / "pages3.jsonl", "r", COUNT3
    if rnd == 4:
        prior = {tuple(dp) for f in ("pages.jsonl", "pages2.jsonl", "pages3.jsonl")
                 for r in read_jsonl(HERE / f) for dp in r["pages"]}
        v1 = test_v1_pages()
        used = prior | v1
        print(f"excluded pages: rounds 1-3 {len(prior)}, test v1 references {len(v1)}, union {len(used)}")
        out_path, prefix, count = HERE / "pages4.jsonl", "s", COUNT4
    pools = kind_pools()
    if rnd == 4:  # test pages only, before sampling, so the counts are not spent on dev pages
        pools = {k: [dp for dp in v if split_of(dp) == "test"] for k, v in pools.items()}
    rows = []
    for kind, pool in pools.items():
        rows += [{"kind": kind, "pages": [dp], "split": split_of(dp)} for dp in round_robin(pool, count[kind], used, rng)]
    rows += pairs(count["cross_doc"], used, rng, test_only=rnd in (2, 4))
    if rnd == 3:
        rows = [r for r in rows if r["split"] == "dev"]
    if rnd == 4:
        assert all(r["split"] == "test" for r in rows), "round 4 must be test pages only"
        print("test pages left unused after sampling:",{k: len([dp for dp in v if dp not in used]) for k, v in pools.items()})
    if "--dry-run" in sys.argv:
        print("sampled:", dict(Counter((r["kind"], r["split"]) for r in rows)))
        print("dry run: nothing written")
        return
    with open(out_path, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(json.dumps({"id": f"{prefix}{i:04d}", **r}, ensure_ascii=False) + "\n")
    print("pool sizes:", {k: len(v) for k, v in pools.items()})
    print("sampled:", dict(Counter((r["kind"], r["split"]) for r in rows)))
    print("docs:", dict(Counter(dp[0] for r in rows for dp in r["pages"])))
    print("banks in pairs:", dict(Counter(BANK[d.split("_")[0]] for r in rows if r["kind"] == "cross_doc" for d, _ in r["pages"])))
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
