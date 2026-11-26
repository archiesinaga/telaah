"""Local review app for drafted questions (the user checks every gold; see eval/BENCHMARK.md).

    .venv/Scripts/python eval/bench/review_app.py      # opens http://127.0.0.1:7861

Shows the page image(s) next to each draft. Fix the question, answer and gold pages, then Accept or Reject.
Calculation/cross_doc golds are recomputed from the figures (JSON) on Accept. Decisions are appended to
reviewed_{split}.jsonl; restarting continues where you stopped. The "Unanswerable" tab adds your own refusal questions; "Cross-doc (write your own)" adds a two-bank comparison.
"""
import io
import json
import re
import sys
import time
from collections import Counter

import gradio as gr
from PIL import Image

from common import HERE, QUOTA, ROOT, append_jsonl, docs, is_report, pages, read_jsonl
from draft import OPS
from gold import compute, fmt_id
from audit import audit_file, sample_file
from userq import UNITS, cross_doc_row, parse_pages

sys.path.insert(0, str(ROOT / "src"))
from telaah.vision import render_page  # noqa: E402

REASONS = ["wrong or unsupported answer", "ambiguous / several answers", "not self-contained",
           "trivial", "chart not readable", "duplicate", "other"]
TYPES = ["text_fact", "table_lookup", "chart", "calculation", "cross_doc", "regulation"]


def cand_file(split): return HERE / f"candidates_{split}.jsonl"
def rev_file(split): return HERE / f"reviewed_{split}.jsonl"
def user_file(split): return HERE / f"user_{split}.jsonl"


def queue(split: str, only: str = "all") -> list[dict]:
    done = {r["cid"] for r in read_jsonl(rev_file(split))}
    rows = [c for c in read_jsonl(cand_file(split)) if c["cid"] not in done and only in ("all", c["type"])]
    return sorted(rows, key=lambda c: (bool(c["problems"]), c["cid"]))  # clean drafts first


def progress(split: str) -> str:
    acc = [r for r in read_jsonl(rev_file(split)) if r["decision"] == "accept"]
    rej = sum(r["decision"] == "reject" for r in read_jsonl(rev_file(split)))
    col = 1 if split == "dev" else 2
    seed = {"text_fact": 12, "table_lookup": 15, "chart": 5, "cross_doc": 8, "unanswerable": 10} if split == "dev" else {}
    user = Counter(r["type"] for r in read_jsonl(user_file(split)))
    cells = []
    for t, q in QUOTA.items():
        n = sum(r["type"] == t for r in acc) + seed.get(t, 0) + user[t]
        cells.append(f"{t} {n}/{q[col]}")
    return f"**{split}**: accepted {len(acc)}, rejected {rej}, left {len(queue(split))} · " + " · ".join(cells)


def image(doc: str, page: int):
    return Image.open(io.BytesIO(render_page(doc, page, dpi=130)))


def also_on(answer: str, gold: list) -> str:
    """Other pages of the same bank that print the answer figure (candidate extra gold pages)."""
    m = re.search(r"\d[\d.,]{4,}\d", answer or "")
    if not m or not gold:
        return ""
    bank = gold[0][0].split("_")[0]
    hits = [f"{d}:{p}" for d in docs() if is_report(d) and d.startswith(bank + "_")
            for p, t in pages(d).items() if m.group(0) in t and [d, p] not in gold]
    return ("Same figure also on: " + ", ".join(hits[:10])) if hits else "Figure not printed on other pages."


def show(split: str, only: str = "all"):
    q = queue(split, only)
    if not q:
        return [None, None, "", "No drafts left in this split.", None, "", "", True, "", "[]", None, "", "", progress(split)]
    c = q[0]
    d = c["draft"]
    imgs = [image(doc, p) for doc, p in c["pages"]] + [None]
    gold_pages = "; ".join(f"{doc}:{p}" for doc, p in c["pages"])
    ev = d.get("evidence")
    ev = "\n".join(ev) if isinstance(ev, list) else (ev or "")
    figs = json.dumps(d.get("figures") or [], ensure_ascii=False, indent=1)
    info = f"`{c['cid']}` · {c['type']} · pages {gold_pages}" + (
        f"\n\n⚠️ {'; '.join(c['problems'])}" if c["problems"] else "")
    return [imgs[0], imgs[1], c["cid"], info, c["type"], d.get("question", ""), d.get("answer", ""),
            bool(d.get("numeric", True)), gold_pages, figs, d.get("op") if d.get("op") in OPS else None, ev,
            also_on(d.get("answer", ""), c["pages"]), progress(split)]


def decide(split, cid, decision, reason, typ, question, answer, numeric, gold_pages, figs, op):
    row = {"cid": cid, "split": split, "decision": decision, "reviewed_at": time.strftime("%Y-%m-%d %H:%M")}
    if decision == "reject":
        row["reason"] = reason or "other"
    else:
        row.update({"type": typ, "question": question.strip(), "gold_pages": parse_pages(gold_pages),
                    "answerable": True, "numeric": bool(numeric)})
        if typ in ("calculation", "cross_doc") and op:
            figures = json.loads(figs)
            x, gold = compute(figures, op)
            if typ == "cross_doc":  # two banks have no "old/new" order: report the size of the gap
                gold = fmt_id(round(abs(x), 2))
            row.update({"figures": figures, "op": op, "computed": gold})
            # calculation: the computed number is the gold; cross_doc keeps the sentence and adds the difference
            row["gold_answer"] = gold if typ == "calculation" else f"{answer.strip()} (selisih {gold})"
        else:
            row["gold_answer"] = answer.strip()
    append_jsonl(rev_file(split), row)


def preview(figs, op):
    try:
        return compute(json.loads(figs), op)[1] if op else ""
    except Exception as e:
        return f"error: {e}"


def add_cross_doc(split, question, ref_a, ref_b, bank_a, bank_b, label, val_a, val_b, unit):
    try:
        n = len(read_jsonl(user_file(split)))
        row = cross_doc_row(split, n + 1, question, ref_a, ref_b, bank_a, bank_b, label, val_a, val_b, unit)
        append_jsonl(user_file(split), row)
        return f"Added cross_doc #{n + 1} in {split}. Gold: {row['gold_answer']}", "", "", "", ""
    except ValueError as e:
        return f"⚠️ Not saved: {e}", question, ref_a, ref_b, label


def audit_queue(split: str) -> list[dict]:
    """Sampled rows not yet judged (the sample holds cids only; see audit.py)."""
    if not sample_file(split).exists():
        return []
    sample = set(json.loads(sample_file(split).read_text(encoding="utf-8")))
    done = {r["cid"] for r in read_jsonl(audit_file(split))}
    rows = [r for r in read_jsonl(rev_file(split)) if r["cid"] in sample and r["decision"] == "accept"]
    return sorted((r for r in rows if r["cid"] not in done), key=lambda r: (r["type"], r["cid"]))


def audit_progress(split: str) -> str:
    sample = json.loads(sample_file(split).read_text(encoding="utf-8")) if sample_file(split).exists() else []
    verdicts = [r["verdict"] for r in read_jsonl(audit_file(split))]
    wrong = verdicts.count("wrong")
    return (f"**{split} audit**: sample {len(sample)}, judged {len(verdicts)} (wrong {wrong}), "
            f"left {len(audit_queue(split))}" + (f" · error rate {wrong / len(verdicts):.0%}" if verdicts else ""))


def audit_show(split: str):
    q = audit_queue(split)
    if not q:
        return [None, None, "", "No rows left to audit (run `audit.py make " + split + "` first if the sample is empty).",
                "", "", "", audit_progress(split)]
    r = q[0]
    pgs = r["gold_pages"]
    imgs = [image(d, p) for d, p in pgs] + [None]
    figs = ""
    if r.get("figures"):
        figs = "\n\n" + "; ".join(f"{f.get('bank', '')} {f.get('label', '')} = {f.get('value', f.get('value_float'))}"
                                  for f in r["figures"])
    return [imgs[0], imgs[1], r["cid"], f"`{r['cid']}` · {r['type']} · pages " + "; ".join(f"{d}:{p}" for d, p in pgs),
            r["question"], r["gold_answer"] + figs, "", audit_progress(split)]


def audit_judge(split, cid, verdict, note):
    if cid:
        append_jsonl(audit_file(split), {"cid": cid, "split": split, "verdict": verdict, "note": (note or "").strip(),
                                         "audited_at": time.strftime("%Y-%m-%d %H:%M")})
    return audit_show(split)


with gr.Blocks(title="Telaah benchmark review") as app:
    with gr.Tab("Review drafts"):
        with gr.Row():
            split = gr.Radio(["dev", "test"], value="dev", label="Split")
            only = gr.Dropdown(["all"] + TYPES, value="all", label="Show type")
            prog = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=3):
                img_a = gr.Image(label="Page A", type="pil", height=900)
                img_b = gr.Image(label="Page B (cross_doc)", type="pil", height=900)
            with gr.Column(scale=2):
                cid = gr.Textbox(visible=False)
                info = gr.Markdown()
                typ = gr.Dropdown(TYPES, label="Type")
                question = gr.Textbox(label="Question", lines=4)
                answer = gr.Textbox(label="Gold answer (calculation: computed from figures)", lines=2)
                numeric = gr.Checkbox(label="Numeric answer")
                gold_pages = gr.Textbox(label="Gold pages (doc:page; doc:page)")
                hint = gr.Markdown()
                evidence = gr.Textbox(label="Drafter's evidence", lines=3, interactive=False)
                figs = gr.Code(label="Figures (calculation / cross_doc): check every value_float", language="json")
                with gr.Row():
                    op = gr.Dropdown(OPS, label="Operation")
                    computed = gr.Textbox(label="Computed", interactive=False)
                with gr.Row():
                    accept = gr.Button("Accept", variant="primary")
                    reason = gr.Dropdown(REASONS, label="Reject reason")
                    reject = gr.Button("Reject", variant="stop")
    with gr.Tab("Unanswerable (write your own)"):
        gr.Markdown("Questions the corpus cannot answer; the right answer is a refusal. Ideas: figures for 2026 or "
                    "later, quarterly figures, banks or regulations not in the corpus, metrics a bank does not "
                    "publish. Check with a quick search that the corpus really does not contain it. "
                    "Target: 12 dev + 8 test.")
        u_split = gr.Radio(["dev", "test"], value="dev", label="Split")
        u_q = gr.Textbox(label="Question", lines=3)
        u_why = gr.Textbox(label="Why it is unanswerable (for the dataset card)")
        u_add = gr.Button("Add", variant="primary")
        u_msg = gr.Markdown()

    with gr.Tab("Cross-doc (write your own)"):
        gr.Markdown("Two banks, one indicator, one year, both pages in the chosen split (test pages only for test; "
                    "pages seen through the retired test v1 are refused). Type each value **exactly as printed** on "
                    "the page (e.g. `3,29` or `1.234.567`). The gold answer and the difference are computed here. "
                    "Pages as `doc:page`, e.g. `bri_2025:145`. Target: about 10 test questions.")
        c_split = gr.Radio(["test", "dev"], value="test", label="Split")
        c_q = gr.Textbox(label="Question (name both banks, the year and the report year; e.g. 'Bandingkan total aset "
                               "BRI dan BNI per 31 Desember 2025 menurut Laporan Tahunan 2025 masing-masing. Bank mana "
                               "yang lebih besar, dan berapa selisihnya?')", lines=3)
        with gr.Row():
            c_ref_a = gr.Textbox(label="Page A (doc:page)")
            c_ref_b = gr.Textbox(label="Page B (doc:page)")
        with gr.Row():
            c_bank_a = gr.Textbox(label="Bank A name (as in the question, e.g. BRI)")
            c_bank_b = gr.Textbox(label="Bank B name (e.g. Bank Mandiri)")
        c_label = gr.Textbox(label="Indicator label (e.g. total aset, rasio NPL gross)")
        with gr.Row():
            c_val_a = gr.Textbox(label="Value A as printed")
            c_val_b = gr.Textbox(label="Value B as printed")
            c_unit = gr.Dropdown(UNITS, value="%", label="Unit")
        c_add = gr.Button("Add cross_doc", variant="primary")
        c_msg = gr.Markdown()

    with gr.Tab("Audit sample"):
        gr.Markdown("Check a random sample of the rows the reviewer subagent accepted. For each row: look at the page, "
                    "decide whether the question and gold answer are **correct** (answer on the page, unambiguous, "
                    "self-contained). Wrong rows are dropped from the benchmark. Make the sample first with "
                    "`python eval/bench/audit.py make test`.")
        a_split = gr.Radio(["test", "dev"], value="test", label="Split")
        a_prog = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=3):
                a_img_a = gr.Image(label="Page A", type="pil", height=900)
                a_img_b = gr.Image(label="Page B (cross_doc)", type="pil", height=900)
            with gr.Column(scale=2):
                a_cid = gr.Textbox(visible=False)
                a_info = gr.Markdown()
                a_q = gr.Textbox(label="Question", lines=4, interactive=False)
                a_gold = gr.Textbox(label="Gold answer", lines=3, interactive=False)
                a_note = gr.Textbox(label="Note (why wrong, optional)")
                with gr.Row():
                    a_ok = gr.Button("Correct", variant="primary")
                    a_bad = gr.Button("Wrong", variant="stop")

    fields = [img_a, img_b, cid, info, typ, question, answer, numeric, gold_pages, figs, op, evidence, hint, prog]
    inputs = [split, only, cid, typ, question, answer, numeric, gold_pages, figs, op]
    app.load(show, [split, only], fields)
    split.change(show, [split, only], fields)
    only.change(show, [split, only], fields)
    op.change(preview, [figs, op], computed)
    figs.change(preview, [figs, op], computed)

    def _accept(s, f, c, *rest):
        if c:
            decide(s, c, "accept", None, *rest)
        return show(s, f)

    def _reject(s, f, c, r):
        if c:
            decide(s, c, "reject", r, None, "", "", False, "", "[]", None)
        return show(s, f)

    accept.click(_accept, inputs, fields)
    reject.click(_reject, [split, only, cid, reason], fields)

    def _add(s, q, why):
        if not q.strip():
            return "Empty question.", q
        n = len(read_jsonl(user_file(s)))
        append_jsonl(user_file(s), {"cid": f"u-{s}-{n + 1:03d}", "split": s, "type": "unanswerable",
                                    "question": q.strip(), "why": why.strip(), "gold_answer": "", "gold_pages": [],
                                    "answerable": False, "numeric": False})
        return f"Added ({n + 1} in {s}).", ""

    u_add.click(_add, [u_split, u_q, u_why], [u_msg, u_q])
    c_add.click(add_cross_doc, [c_split, c_q, c_ref_a, c_ref_b, c_bank_a, c_bank_b, c_label, c_val_a, c_val_b, c_unit],
                [c_msg, c_q, c_ref_a, c_ref_b, c_label])

    a_fields = [a_img_a, a_img_b, a_cid, a_info, a_q, a_gold, a_note, a_prog]
    app.load(audit_show, [a_split], a_fields)
    a_split.change(audit_show, [a_split], a_fields)
    a_ok.click(lambda s_, c, n: audit_judge(s_, c, "correct", n), [a_split, a_cid, a_note], a_fields)
    a_bad.click(lambda s_, c, n: audit_judge(s_, c, "wrong", n), [a_split, a_cid, a_note], a_fields)

if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7861, inbrowser=True)
