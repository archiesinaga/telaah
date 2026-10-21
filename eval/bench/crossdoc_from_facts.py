"""Cross-document candidates from the facts table: two banks, one indicator, one year, both from the same report year.

The free-drafting route gave comparisons with mismatched units and periods (BENCHMARK.md, round 1). Here both
figures come from table rows with a known page, in one unit, for one year; the gold (higher bank, difference) is
computed in Python. Candidates go to candidates_{dev,test}.jsonl in the draft format, so review is the same.
Only rows the facts table is sure of are used (not inherited, one value, seen in the named report), and the raw
cell text must occur on the cited page.

    .venv/Scripts/python eval/bench/crossdoc_from_facts.py        # prints counts only
"""
import itertools
import json
import random
import re
import sys
from collections import Counter

from common import HERE, ROOT, SEED, append_jsonl, norm, pages, split_of, tuned_pages

sys.path.insert(0, str(ROOT / "src"))
from telaah import facts  # noqa: E402
from gold import fmt_id  # noqa: E402

BANKS = ["bri", "mandiri", "bni", "btn", "bca"]
NAME = {"bri": "BRI", "mandiri": "Bank Mandiri", "bni": "BNI", "btn": "BTN", "bca": "BCA"}
LABEL = {"roa": "ROA", "roe": "ROE", "car": "rasio KPMM (CAR)", "ldr": "LDR", "nim": "NIM", "bopo": "BOPO",
         "npl_gross": "rasio NPL gross", "npl_net": "rasio NPL net", "casa": "rasio CASA", "tier1": "CAR Tier 1",
         "cet1": "rasio CET1", "total_aset": "total aset", "laba": "laba bersih", "ekuitas": "total ekuitas"}
MONEY = {"total_aset", "laba", "ekuitas"}
TEMPLATES = [
    "Bandingkan {ind} {a} dan {b} pada tahun {y} menurut Laporan Tahunan {ry} masing-masing. Bank mana yang lebih tinggi, dan berapa selisihnya?",
    "Berapa selisih {ind} antara {a} dan {b} pada tahun {y} (Laporan Tahunan {ry}), dan bank mana yang lebih tinggi?",
    "Mana yang lebih tinggi, {ind} {a} atau {b} pada tahun {y} menurut Laporan Tahunan {ry}? Sebutkan nilai keduanya dan selisihnya.",
]
QUOTA = {"dev": 57, "test": 22}


def hit_ok(h: dict | None) -> bool:
    if not h or h["inherited"] or h["alternatives"]:
        return False
    page = norm(pages(h["doc"]).get(h["page"], "").replace("|", " "))
    return norm(h["raw"]) in page and h["page"] > 4


def figure(h: dict, ind: str) -> tuple[float, str]:
    """Value in the unit used in the question and its printed form."""
    if ind in MONEY:
        v = facts.to_unit(h, "tn")
        return v, f"Rp{fmt_id(round(v, 2))} triliun"
    return h["value"], fmt_id(h["value"]) + "%"


def candidates() -> list[dict]:
    out = []
    tuned = tuned_pages()
    for ind, ry, y in itertools.product(LABEL, (2024, 2025), range(2020, 2026)):
        if y > ry or ry - y > 4:
            continue
        got = {b: h for b in BANKS if hit_ok(h := facts.lookup(b, ind, y, ry)) and h["report_year"] == ry}
        for a, b in itertools.combinations(sorted(got), 2):
            ha, hb = got[a], got[b]
            split = split_of((ha["doc"], ha["page"]), (hb["doc"], hb["page"]))
            if split == "mixed" or ha["value"] == hb["value"]:
                continue
            (va, sa), (vb, sb) = figure(ha, ind), figure(hb, ind)
            hi, lo = (a, b) if va > vb else (b, a)
            gap = abs(round(va, 2) - round(vb, 2)) if ind in MONEY else abs(va - vb)
            unit = "triliun Rupiah" if ind in MONEY else "poin persentase"
            ans = f"{NAME[hi]} lebih tinggi: {LABEL[ind]} {NAME[a]} {sa} vs {NAME[b]} {sb} (selisih {fmt_id(round(gap, 2))} {unit})."
            out.append({
                "split": split, "ind": ind, "pair": (a, b), "year": y, "ry": ry,
                "fresh": not ({(ha["doc"], ha["page"]), (hb["doc"], hb["page"])} & tuned),
                "pages": [[ha["doc"], ha["page"]], [hb["doc"], hb["page"]]],
                "answer": ans, "op": "difference",
                "figures": [{"bank": NAME[a], "label": LABEL[ind], "value": sa, "value_float": round(va, 4), "unit": unit, "page": "A"},
                            {"bank": NAME[b], "label": LABEL[ind], "value": sb, "value_float": round(vb, 4), "unit": unit, "page": "B"}],
                "evidence": [ha["raw"], hb["raw"]],
            })
    return out


def main() -> None:
    rng = random.Random(SEED)
    cands = candidates()
    print("possible pairs:", dict(Counter((c["split"], c["fresh"]) for c in cands)))
    done = {json.loads(l)["cid"] for f in ("candidates_dev.jsonl", "candidates_test.jsonl") if (HERE / f).exists()
            for l in open(HERE / f, encoding="utf-8")}
    n = 0
    for split, quota in QUOTA.items():
        pool = [c for c in cands if c["split"] == split]
        rng.shuffle(pool)
        pool.sort(key=lambda c: not c["fresh"])  # untuned pages first
        picked, per_ind, per_pair = [], Counter(), Counter()
        for c in pool:  # spread over indicators and bank pairs
            if len(picked) >= int(quota * 1.4):
                break
            if per_ind[c["ind"]] >= 6 or per_pair[c["pair"]] >= 8:
                continue
            picked.append(c)
            per_ind[c["ind"]] += 1
            per_pair[c["pair"]] += 1
        for c in picked:
            n += 1
            cid = f"x{n:04d}-1"
            if cid in done:
                continue
            q = rng.choice(TEMPLATES).format(ind=LABEL[c["ind"]], a=NAME[c["pair"][0]], b=NAME[c["pair"][1]], y=c["year"], ry=c["ry"])
            append_jsonl(HERE / f"candidates_{split}.jsonl", {
                "cid": cid, "page_id": "facts", "type": "cross_doc", "split": split, "pages": c["pages"],
                "draft": {"question": q, "answer": c["answer"], "figures": c["figures"], "op": "difference",
                          "evidence": c["evidence"], "numeric": True},
                "problems": [], "model": "facts-table"})
        print(split, "candidates written:", len(picked), "by indicator:", dict(per_ind))


if __name__ == "__main__":
    main()
