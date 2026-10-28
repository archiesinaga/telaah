"""Wrap the checked drafts in real retrieval -> sft/sft.jsonl (sft/DESIGN.md, steps 3-4: context, mix, filters).

Each example is exactly what `answer.ask` sends: system `answer.SYSTEM`, user `Konteks:\n{build_context(top 5)}\n\n
Pertanyaan: {question}`, assistant the draft's cited answer or `TIDAK DITEMUKAN`. Mix (DESIGN.md):
- answer: real top 5; if the gold page is not in it, the gold page replaces a random rank 1-5 ("pushed");
  tagged `lookalike` when another context page carries the same row label without the answer value
- refusal_removed: every page holding the value dropped from the top 20, the next 5 kept
- refusal_scope: the bank name swapped for a bank outside the corpus (bank questions only)
Retrieval needs the vector store (one process at a time: never while an eval runs); results are cached in
sft/retrieved.jsonl, so a rebuild with other shares or filters does not retrieve again.

    .venv/Scripts/python sft/build_sft.py
"""
import os

os.environ.setdefault("TELAAH_TRANSCRIPTS", "1")  # the shipped eval setup (DESIGN.md: transcripts ON)
os.environ.setdefault("TELAAH_COLPALI_CACHE_ONLY", "1")

import hashlib  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "eval" / "bench"))
from common import append_jsonl, norm, read_jsonl  # noqa: E402
from draft_sft import covered  # noqa: E402
from telaah import transcripts  # noqa: E402
from telaah.answer import REFUSAL, SYSTEM, build_context  # noqa: E402
from telaah.config import MAX_ANSWER_TOKENS, TOP_K  # noqa: E402
from telaah.metrics import numeric_match  # noqa: E402
from telaah.retrieve import YEAR_RE, _page_lookup, entity_groups, retrieve  # noqa: E402

DRAFTS = HERE / "drafts.jsonl"
CACHE = HERE / "retrieved.jsonl"
OUT = HERE / "sft.jsonl"
DEV = HERE.parent / "eval" / "bench" / "dev.jsonl"
POOL = 20  # retrieved pages kept per question (refusal_removed refills from ranks 6+)
SHARE = {"refusal_removed": 0.12, "refusal_scope": 0.08}  # of all drafts; the rest are answers
MAX_PROMPT_CHARS = 21000  # ~7k tokens at ~3 chars per token (training max length, DESIGN.md)
OTHER_BANKS = ["Bank Danamon", "CIMB Niaga", "Bank Permata", "OCBC NISP", "Bank Mega"]
BANK_RE = re.compile(
    r"PT Bank (?:Rakyat Indonesia|Negara Indonesia|Tabungan Negara|Mandiri|Central Asia)(?: \(Persero\))?(?: Tbk)?"
    r"|Bank (?:Rakyat Indonesia|Negara Indonesia|Tabungan Negara|Mandiri|Central Asia)|\b(?:BRI|BNI|BTN|BCA|Mandiri)\b")


def mix_of(cid: str) -> str:
    """Deterministic share draw per draft, so rebuilds give the same split."""
    u = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if u < SHARE["refusal_removed"]:
        return "refusal_removed"
    return "refusal_scope" if u < SHARE["refusal_removed"] + SHARE["refusal_scope"] else "answer"


def out_of_scope(question: str, cid: str) -> str | None:
    if not BANK_RE.search(question):
        return None
    bank = OTHER_BANKS[int(hashlib.md5(cid.encode()).hexdigest()[:4], 16) % len(OTHER_BANKS)]
    return BANK_RE.sub(bank, question)


def holds(text: str, value: str) -> bool:
    """The answer value is on this page (same tests as draft_sft.check)."""
    if len(value.split()) > 6:
        return covered(value, text) >= 0.9
    return numeric_match(text, value) if re.search(r"\d", value) else norm(value) in norm(text)


def retrieved(questions: list[str]) -> dict[str, list[list]]:
    cache = {r["question"]: r["pages"] for r in read_jsonl(CACHE)} if CACHE.exists() else {}
    todo = [q for q in dict.fromkeys(questions) if q not in cache]
    for i, q in enumerate(todo, 1):
        pages = [[c["doc_id"], c["page"]] for c in retrieve(q, k=POOL)]
        append_jsonl(CACHE, {"question": q, "pages": pages})
        cache[q] = pages
        if i % 50 == 0 or i == len(todo):
            print(f"retrieved {i}/{len(todo)}", flush=True)
    return cache


def chunks(pages: list[list]) -> list[dict]:
    """Retrieval-shaped page dicts (text as indexed, plus the chart transcription the pipeline adds)."""
    lookup = _page_lookup()
    out = [lookup[(d, p)] for d, p in pages if (d, p) in lookup]
    return transcripts.annotate(out) if transcripts.USE else out


def dev_figures() -> dict[tuple[str, str], list[str]]:
    """(bank, year) -> dev gold answers, for the leakage filter (DESIGN.md: same figure on another page)."""
    out: dict = {}
    for q in read_jsonl(DEV):
        if not q.get("answerable") or not q.get("gold_pages"):
            continue
        bank = q["gold_pages"][0][0].split("_")[0]
        for y in set(YEAR_RE.findall(q["question"])):
            out.setdefault((bank, y), []).append(q["gold_answer"])
    return out


def dev_pages() -> dict[str, list[str]]:
    """bank -> text of every dev gold page, for the same-table filter (a training cell next to a dev answer)."""
    out: dict = {}
    for q in read_jsonl(DEV):
        for doc, page in q.get("gold_pages") or []:
            out.setdefault(doc.split("_")[0], {})[(doc, page)] = None
    return {b: [c["text"] + c.get("transcript", "") for c in chunks(list(map(list, ps)))] for b, ps in out.items()}


def block_of(context: str, doc: str, page: int) -> str:
    """The text the model actually sees for one page (build_context keeps only an excerpt of long pages)."""
    head = f"[{doc} p.{page}]\n"
    if head not in context:
        return ""
    rest = context.split(head, 1)[1]
    m = re.search(r"\n\n\[\w+ p\.\d+\]\n", rest)
    return rest[:m.start()] if m else rest


# review 10-29 (Opus 5.5): questions that leak the page or point at table layout, English-format figures with an
# Indonesian unit ("35,415,779 miliar" reads 1,000x off in Indonesian)
PAGE_REF_RE = re.compile(r"\b(?:bri|bni|btn|bca|mandiri)_20\d\d\b|\bp\.\s?\d", re.I)
LAYOUT_RE = re.compile(r"baris (?:pertama|kedua|ketiga|keempat|terakhir|tersebut|ini)|kolom (?:pertama|kedua|ini)"
                       r"|tabel (?:ini|tersebut|di atas)|halaman (?:ini|tersebut)|grafik (?:ini|tersebut)", re.I)
EN_FIGURE_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*(?:miliar|triliun|juta)")
DATE_RE = re.compile(r"januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember"
                     r"|tahun|\b(?:19|20)\d\d\b", re.I)


def label_of(evidence: str) -> str:
    """Row label: the evidence text before its first figure ("Nasabah non-bank 9.222.508" -> "nasabahnonbank")."""
    return re.sub(r"[^a-z]", "", re.split(r"\d", evidence.lower(), maxsplit=1)[0])


def example(system_user: tuple[str, str], answer: str) -> list[dict]:
    return [{"role": "system", "content": system_user[0]}, {"role": "user", "content": system_user[1]},
            {"role": "assistant", "content": answer}]


def main() -> None:
    drafts = [r for r in read_jsonl(DRAFTS) if not r["problems"]]
    drop: Counter = Counter()
    seen, rows = set(), []
    for r in drafts:
        key = norm(r["draft"]["question"])
        if key in seen:
            drop["duplicate question"] += 1
            continue
        seen.add(key)
        rows.append(r)
    plans = []
    for r in rows:
        q, mix = r["draft"]["question"], mix_of(r["cid"])
        if mix == "refusal_scope":
            q = out_of_scope(q, r["cid"]) or q
            mix = mix if q != r["draft"]["question"] else "answer"  # no bank to swap: keep it as an answer
        if entity_groups(q):  # the pipeline reads these per entity (ask_entities), another prompt
            drop["multi-entity question"] += 1
            continue
        if PAGE_REF_RE.search(q):
            drop["question names a doc id or page"] += 1
            continue
        if LAYOUT_RE.search(q):
            drop["question points at table layout"] += 1
            continue
        plans.append((r, q, mix))
    pools = retrieved([q for _, q, _ in plans])
    dev = dev_figures()
    dev_text = dev_pages()
    rng = random.Random(7)
    counts: Counter = Counter()
    with open(OUT, "w", encoding="utf-8") as f:
        for r, q, mix in plans:
            d = r["draft"]
            doc, page = r["pages"][0]
            value = str(d["value"])
            pool = pools[q]
            info = {"pushed": False, "lookalike": False}
            if mix == "answer":
                top = pool[:TOP_K]
                if [doc, page] not in top:
                    i = rng.randrange(len(top)) if top else 0
                    top = top[:i] + [[doc, page]] + top[i + 1:]
                    info["pushed"] = True
                ctx = chunks(top)
                target = d["answer"].strip()
            else:
                ctx = [c for c in chunks(pool) if not holds(c["text"] + c.get("transcript", ""), value)][:TOP_K]
                target = REFUSAL
            text = {(c["doc_id"], c["page"]): c["text"] + c.get("transcript", "") for c in ctx}
            if mix == "answer":
                if (doc, page) not in text:
                    drop["gold page missing from context"] += 1
                    continue
                label = label_of(str(d.get("evidence", "")))
                info["lookalike"] = len(label) >= 8 and any(
                    label in re.sub(r"[^a-z]", "", t.lower()) and not holds(t, value)
                    for k, t in text.items() if k != (doc, page))
            elif any(holds(t, value) for t in text.values()) or len(ctx) < TOP_K:
                drop["refusal context holds the value or is short"] += 1
                continue
            bank, years = doc.split("_")[0], set(YEAR_RE.findall(q))
            # short figures ("20%") match dates and counts in any answer: only 3+ digit figures can leak a gold answer
            figure = re.search(r"\d[\d.,]*", value)
            if (mix == "answer" and figure and len(re.sub(r"\D", "", figure.group())) >= 3
                    and any(numeric_match(g, value) for y in years for g in dev.get((bank, y), []))):
                drop["figure equals a dev gold answer"] += 1
                continue
            context = build_context(ctx, q)
            if mix == "answer":
                if not holds(block_of(context, doc, page), value):
                    drop["value cut out of the page excerpt"] += 1
                    continue
                if EN_FIGURE_RE.search(target):
                    drop["English-format figure with Indonesian unit"] += 1
                    continue
                q_years, a_years = set(YEAR_RE.findall(q)), set(YEAR_RE.findall(re.sub(r"\[\w+ p\.\d+\]", "", target)))
                if r["kind"] in ("table_lookup", "calculation") and q_years and a_years and not q_years & a_years:
                    drop["question and answer years differ"] += 1
                    continue
                if (not DATE_RE.search(value) and len(re.sub(r"\D", "", value)) >= 5
                        and any(numeric_match(t, value) for t in dev_text.get(bank, []))):
                    drop["figure on a dev gold page"] += 1
                    continue
            user = f"Konteks:\n{context}\n\nPertanyaan: {q}"
            if len(user) > MAX_PROMPT_CHARS or len(target) / 3 > MAX_ANSWER_TOKENS:
                drop["too long"] += 1
                continue
            kind = mix if mix != "answer" else ("answer_pushed" if info["pushed"] else "answer_top5")
            counts[(kind, r["kind"])] += 1
            counts[kind] += 1
            counts["lookalike"] += info["lookalike"]
            f.write(json.dumps({"cid": r["cid"], "mix": kind, "lookalike": info["lookalike"], "kind": r["kind"],
                                "page": [doc, page], "messages": example((SYSTEM, user), target)},
                               ensure_ascii=False) + "\n")
    total = sum(v for k, v in counts.items() if isinstance(k, str) and k != "lookalike")
    print(f"drafts without problems: {len(drafts)}; examples: {total}")
    for k in ("answer_top5", "answer_pushed", "refusal_removed", "refusal_scope", "lookalike"):
        print(f"  {k:16s} {counts[k]:5d}  {counts[k] / max(total, 1):.0%}")
    print("per kind:", {f"{a}/{b}": v for (a, b), v in sorted((k, v) for k, v in counts.items() if isinstance(k, tuple))})
    print("dropped:", dict(drop))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
