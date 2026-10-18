"""Planner -> executor -> verifier agent (LangGraph) on top of the RAG pipeline and the tools.

plan     : LLM splits the question into standalone fact lookups (+ whether a calculation is needed)
execute  : each pending step runs the normal `ask` pipeline (retry steps use a larger top-k)
verify   : every sentence with a citation is checked against the cited page (`tools.check_citation`);
           a step that fails is retried once, then dropped
compute  : LLM writes one arithmetic expression over the verified facts; `tools.calculate` evaluates it
compose  : final answer from verified facts (+ calculator result)
final    : the final answer is checked the same way; results of the calculator are allowed
"""
import json
import os
import re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from telaah import facts, tools, vision
from telaah.answer import CITE_RE, REFUSAL, SYSTEM, _chat, answer_entity, ask, parse_citations, refine_step, split_question
from telaah.config import LLM_API_KEY, LLM_BASE_URL, LLM_MAX_RETRIES, ROOT
from telaah.retrieve import entity_groups

MAX_STEPS = 5
# one-figure steps (bank, indicator, year) are read from the facts table instead of RAG; TELAAH_FACTS=0 disables
USE_FACTS = os.environ.get("TELAAH_FACTS", "1") == "1"
RETRY_K = 8
RETRY_ENTITY_PAGES = 8
CALC_RE = re.compile(r"selisih|perbedaan|beda\b|berapa kali|rata-rata|total gabungan|jumlah", re.I)
# questions that need arithmetic over several figures: the 7B must not compute these itself
DERIVE_RE = re.compile(r"\bhitung\b|dibagi|rata-rata sederhana|dua desimal|gabungan\b|selisih", re.I)
NUM_RE = tools.NUM_RE
TRACE_DIR = ROOT / "data" / "agent_traces"
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

PLAN_SYSTEM = f"""Kamu perencana untuk asisten riset dokumen keuangan Indonesia.
Pecah pertanyaan menjadi langkah pencarian angka/fakta yang berdiri sendiri. Keluarkan HANYA JSON:
{{"steps": ["pertanyaan 1", ...], "calc": true/false}}
Aturan:
- Maksimal {MAX_STEPS} langkah; setiap langkah menanyakan SATU nilai ("Berapa ...") dan menyebut nama bank/peraturan, indikator, dan periode secara lengkap.
- calc=true bila jawaban akhir butuh hitungan dari angka-angka itu (selisih, rasio, rata-rata, pertumbuhan); selain itu false.
- Hitungan (pertumbuhan, jumlah, rasio, rata-rata) SELALU dipecah: satu langkah per angka mentah per bank per tahun; jangan minta hasil hitungan di langkah pencarian.
- Pertanyaan yang sudah sederhana: satu langkah berisi pertanyaan aslinya.
Contoh: "Berapa selisih NPL gross BRI dan BNI tahun 2024?" ->
{{"steps": ["Berapa NPL gross BRI tahun 2024?", "Berapa NPL gross BNI tahun 2024?"], "calc": true}}
Contoh: "Berapa pertumbuhan total aset BTN 2025 dibanding 2024 dalam persen?" ->
{{"steps": ["Berapa total aset BTN pada akhir 2024?", "Berapa total aset BTN pada akhir 2025?"], "calc": true}}
Contoh: "Berapa laba bersih 2025 BCA dibagi total asetnya?" ->
{{"steps": ["Berapa laba bersih BCA tahun 2025?", "Berapa total aset BCA pada akhir 2025?"], "calc": true}}"""
CALC_SYSTEM = """Dari fakta terverifikasi, tulis SATU ekspresi aritmetika untuk menjawab pertanyaan.
Keluarkan HANYA JSON: {"expression": "...", "unit": "satuan hasil"}. Pakai titik sebagai desimal, tanpa pemisah ribuan,
hanya angka dan + - * / ( ). Contoh: {"expression": "2.1 - 1.8", "unit": "poin persentase"}
Satuan laporan: BRI, Bank Mandiri, dan BTN dalam JUTA Rupiah; BCA dan BNI dalam MILIAR Rupiah. 1 triliun = 1000000 juta = 1000 miliar.
Bila pertanyaan meminta triliun, konversikan di dalam ekspresi: juta -> bagi 1000000, miliar -> bagi 1000.
Pertumbuhan persen = (baru / lama - 1) * 100. Rasio persen = (a / b) * 100. Gunakan angka mentah dari fakta, jangan angka hasil bulatan."""


class State(TypedDict, total=False):
    question: str
    steps: list[dict]  # {q, answer, citations, retrieved, context, status: pending|ok|failed, attempts, issues}
    calc: bool
    calc_result: dict | None
    derived: list[str]  # figures computed in Python from a facts sheet (facts.derive)
    answer: str
    unsupported: list[dict]
    trace: list[dict]


def _llm() -> OpenAI:
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)


def _log(state: State, node: str, t0: float, **info) -> list[dict]:
    return state.get("trace", []) + [{"node": node, "s": round(time.time() - t0, 2), **info}]


def _json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


FIG_RE = re.compile(r"(Rp\s?)?(\d[\d.,]*\d|\d)(\s?%)?(\s+(?:juta|miliar|triliun|ribu|persen|kali|poin|bps|rupiah|usd)\b)?", re.I)
DATE_RE = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")


def _claim(sent: str, allowed: set[str]) -> str:
    """The figures a sentence asserts: numbers with Rp, %, a unit word or a separator. Bare integers (dates,
    article numbers, 'ayat 2') and years are not figures; `allowed` (calculator results) are skipped."""
    text = YEAR_RE.sub("", CITE_RE.sub("", sent))
    figs = []
    for m in FIG_RE.finditer(text):
        num = m.group(2)
        if DATE_RE.fullmatch(num) or tools.number_variants(num) & allowed:
            continue
        if m.group(1) or m.group(3) or m.group(4) or re.search(r"[.,]", num):
            figs.append(num)
    return " ".join(figs)


def repair_text(text: str, candidates: list[tuple[str, int]], allowed: set[str] = frozenset()) -> str:
    """Models often cite a neighbouring page. When a cited page does not hold a sentence's numbers but a
    retrieved page does, point the citation to that page; otherwise leave the sentence for the check."""
    out = []
    for sent in SENT_RE.split(text):
        cites = parse_citations(sent)
        claim = _claim(sent, allowed)
        if cites and NUM_RE.search(claim) and not any(tools.check_citation(d, p, claim)["supported"] for d, p in cites):
            for d, p in dict.fromkeys(candidates):
                if tools.check_citation(d, p, claim)["supported"]:
                    sent = CITE_RE.sub("", sent).rstrip() + f" [{d} p.{p}]"
                    break
        out.append(sent)
    return " ".join(out)


def check_text(text: str, allowed: set[str] = frozenset()) -> list[dict]:
    """Sentences with a citation whose numbers are not on any cited page. Years and numbers in `allowed`
    (e.g. calculator results) are ignored."""
    bad = []
    for sent in SENT_RE.split(text):
        cites = parse_citations(sent)
        if not cites:
            continue
        claim = _claim(sent, allowed)
        results = [tools.check_citation(d, p, claim) for d, p in cites]
        # a sentence may combine figures from several cited pages: a number only counts as missing
        # when NO cited page holds it
        missing = set.intersection(*(set(r["missing_numbers"]) for r in results))
        if not any(r["page_found"] for r in results) or missing:
            bad.append({"sentence": sent.strip(), "missing": sorted(missing), "reason": results[0]["reason"]})
    return bad


def plan(state: State) -> dict:
    t0 = time.time()
    q = state["question"]
    sh = facts.sheet(q, partial=True) if USE_FACTS else None
    if sh:  # one indicator over banks x years: no LLM plan; lookups are the steps, missing figures RAG steps
        steps = []
        for (b, y), h in sh["hits"].items():
            r = facts.as_answer(b, y, h)
            steps.append({"q": f"{facts.BANK_NAME[b]} {sh['indicator']} {y}", "status": "ok", "attempts": 1,
                          "issues": [], "fact": r["fact"], **{k: r[k] for k in ("answer", "citations", "retrieved", "context", "refused")}})
        for b, y in sh["missing"]:
            steps.append({"q": facts.step_question(b, sh["indicator"], y, sh["report_year"]), "status": "pending", "attempts": 0})
        # all figures in the table: arithmetic in Python; some read by RAG: the calculator step does it
        derived = [] if sh["missing"] else facts.derive(q, sh)
        calc = bool(sh["missing"]) and bool(CALC_RE.search(q) or DERIVE_RE.search(q) or facts.CHANGE_RE.search(q)
                                             or facts.GAP_RE.search(q) or facts.MEAN_RE.search(q))
        return {"steps": steps, "calc": calc, "derived": derived,
                "trace": _log(state, "plan", t0, sheet=sh["indicator"], steps=[s["q"] for s in steps], derived=derived,
                              missing=sh["missing"])}
    groups = entity_groups(q)
    if groups:  # comparison across documents: the tuned one-question-per-entity split, each read from its own docs
        steps = [{"q": s, "docs": g, "status": "pending", "attempts": 0}
                 for s, g in zip(split_question(_llm(), q, groups), groups)]
        calc = bool(CALC_RE.search(q) or DERIVE_RE.search(q))
    else:
        data = _json(_chat(_llm(), PLAN_SYSTEM, q))
        subs = [s for s in data.get("steps", []) if isinstance(s, str) and s.strip()][:MAX_STEPS]
        if len(subs) <= 1:  # nothing to decompose: the original wording is the tuned one
            subs = [q]
        elif vision.wants_image(q):
            subs = [s if vision.wants_image(s) else s.rstrip(" ?") + " (menurut grafik)?" for s in subs]
        if len(subs) > 1:
            subs = [refine_step(s, q) for s in subs]
        steps = [{"q": s, "status": "pending", "attempts": 0} for s in subs]
        calc = (bool(data.get("calc")) or bool(DERIVE_RE.search(q))) and len(subs) > 1
    return {"steps": steps, "calc": calc,
            "trace": _log(state, "plan", t0, steps=[s["q"] for s in steps], calc=calc)}


def execute(state: State) -> dict:
    t0 = time.time()
    steps = []
    for st in state["steps"]:
        if st["status"] == "pending":
            retry = bool(st["attempts"])
            hit = None if retry or not USE_FACTS else facts.answer_step(st["q"], state["question"], st.get("docs"))
            if hit:
                r = hit
                st = {**st, "fact": hit["fact"]}
            elif st.get("docs"):
                got, chunks, vp, ctx = answer_entity(_llm(), st["q"], st["docs"], RETRY_ENTITY_PAGES if retry else None)
                r = {"answer": got, "citations": parse_citations(got), "context": ctx, "refused": REFUSAL in got,
                     "retrieved": [(c["doc_id"], c["page"]) for c in chunks], "vision": vp}
            else:
                r = ask(st["q"], k=RETRY_K if retry else None)
            st = {**st, "vision": bool(r.get("vision"))}
            st = {**st, "attempts": st["attempts"] + 1, "answer": r["answer"], "citations": r["citations"],
                  "retrieved": r["retrieved"], "context": r["context"], "refused": r["refused"]}
        steps.append(st)
    return {"steps": steps, "trace": _log(state, "execute", t0, answers=[s.get("answer", "")[:200] for s in steps])}


def verify_steps(state: State) -> dict:
    t0 = time.time()
    steps = []
    for st in state["steps"]:
        if st["status"] == "pending":
            if st["refused"]:
                st = {**st, "issues": ["refused"], "status": "pending" if st["attempts"] < 2 else "failed"}
            else:
                st = {**st, "answer": repair_text(st["answer"], st["retrieved"])}
                # figures read from a page IMAGE are not in the page text: accept those found in the
                # vision-augmented context
                seen = {v for tok in NUM_RE.findall(st["context"]) for v in tools.number_variants(tok)} if st.get("vision") else set()
                issues = check_text(st["answer"], seen)
                if not issues:
                    st = {**st, "status": "ok", "issues": []}
                elif st["attempts"] < 2:
                    st = {**st, "issues": issues}  # stays pending -> retried with larger k
                else:
                    st = {**st, "status": "failed", "issues": issues}
        steps.append(st)
    return {"steps": steps, "trace": _log(state, "verify_steps", t0, status=[s["status"] for s in steps])}


def after_verify(state: State) -> str:
    if any(s["status"] == "pending" for s in state["steps"]):
        return "execute"
    return "compute" if any(s["status"] == "ok" for s in state["steps"]) else "refuse"


def split_cites(text: str) -> str:
    """'[a p.1, b p.2]' -> '[a p.1] [b p.2]' so every citation parses."""
    return re.sub(r"(p\.\d+)\s*[,;]\s*(?=[\w-]+\s+p\.\d)", r"\1] [", text)


def plain_numbers(text: str) -> str:
    """Indonesian numbers to plain ones for the calculator prompt: '61.346.133' -> '61346133', '3,29' -> '3.29'.
    The 7B otherwise reads the dots as decimal points."""
    def fix(m):
        t = m.group(0)
        if t.count(".") >= 2 or re.fullmatch(r"\d{1,3}\.\d{3}", t) or "," in t:
            t = t.replace(".", "").replace(",", ".")
        return t
    return NUM_RE.sub(fix, CITE_RE.sub("", text))


def _facts(state: State) -> str:
    ok = "\n\n".join(f"[Jawaban untuk: {s['q']}]\n{s['answer'].strip()}" for s in state["steps"] if s["status"] == "ok")
    missing = [s["q"] for s in state["steps"] if s["status"] != "ok"]
    return ok + "".join(f"\n\n[Tidak ditemukan: {q}]" for q in missing)


def compute(state: State) -> dict:
    t0 = time.time()
    result = None
    if state.get("calc") and all(s["status"] == "ok" for s in state["steps"]):
        data = _json(_chat(_llm(), CALC_SYSTEM, f"Fakta:\n{plain_numbers(_facts(state))}\n\nPertanyaan: {state['question']}"))
        try:
            value = tools.calculate(str(data.get("expression", "")))
            result = {"expression": data["expression"], "value": value, "unit": data.get("unit", "")}
        except (ValueError, SyntaxError, ZeroDivisionError, KeyError) as e:
            result = {"error": str(e)}
    return {"calc_result": result, "trace": _log(state, "compute", t0, result=result)}


def compose(state: State) -> dict:
    t0 = time.time()
    calc = state.get("calc_result")
    extra = ""
    if calc and "value" in calc:
        extra = f"\n\nHasil hitung (kalkulator): {calc['expression']} = {fmt_id(calc['value'])} {calc['unit']}"
    if state.get("derived"):
        extra += "\n\nHasil hitung (kalkulator):\n" + "\n".join(f"- {line}" for line in state["derived"])
    text = _chat(
        _llm(), SYSTEM,
        f"Konteks:\n{_facts(state)}{extra}\n\nPertanyaan: {state['question']}\n"
        "Jawab dari jawaban-jawaban di atas dan pertahankan sitasi [doc_id p.N] pada setiap angka dari dokumen. "
        "Pakai hasil kalkulator apa adanya bila ada.",
    )
    text = split_cites(text)
    return {"answer": text, "trace": _log(state, "compose", t0, answer=text[:300])}


def fmt_id(v: float) -> str:
    """1849958023.5 -> '1.849.958.023,5' (Indonesian separators, at most 2 decimals)."""
    s = f"{v:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _allowed(calc: dict | None) -> set[str]:
    if not calc or "value" not in calc:
        return set()
    v = calc["value"]
    return {x for d in range(0, 5) for x in tools.number_variants(f"{v:.{d}f}")} | {str(v)}


def verify_final(state: State) -> dict:
    t0 = time.time()
    allowed = _allowed(state.get("calc_result")) | tools.numbers_in(YEAR_RE.sub("", "\n".join(state.get("derived") or [])))
    bad = check_text(state["answer"], allowed)
    return {"unsupported": bad, "trace": _log(state, "verify_final", t0, unsupported=len(bad))}


def refuse(state: State) -> dict:
    return {"answer": REFUSAL, "unsupported": [], "trace": _log(state, "refuse", time.time())}


def build():
    g = StateGraph(State)
    for name, fn in [("plan", plan), ("execute", execute), ("verify_steps", verify_steps),
                     ("compute", compute), ("compose", compose), ("verify_final", verify_final), ("refuse", refuse)]:
        g.add_node(name, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "verify_steps")
    g.add_conditional_edges("verify_steps", after_verify, {"execute": "execute", "compute": "compute", "refuse": "refuse"})
    g.add_edge("compute", "compose")
    g.add_edge("compose", "verify_final")
    g.add_edge("verify_final", END)
    g.add_edge("refuse", END)
    return g.compile()


def run_agent(question: str) -> dict:
    """Same result keys as `answer.ask`, plus steps / calc_result / unsupported / trace."""
    t0 = time.time()
    s = build().invoke({"question": question, "trace": []})
    steps = s["steps"]
    out = {
        "answer": s["answer"],
        "citations": parse_citations(s["answer"]),
        "retrieved": [r for st in steps for r in st.get("retrieved", [])],
        # figures computed in Python from a facts sheet are tool output: the faithfulness judge must see them
        "context": "\n\n".join([st.get("context", "") for st in steps if st["status"] == "ok"]
                               + (["Hasil hitung (kalkulator):\n" + "\n".join(s["derived"])] if s.get("derived") else [])),
        "refused": REFUSAL in s["answer"],
        "verified": not s["unsupported"] and not s["answer"].startswith(REFUSAL),
        "unsupported": s["unsupported"],
        "calc_result": s.get("calc_result"),
        "steps": [{k: v for k, v in st.items() if k not in ("context", "retrieved")} for st in steps],
        "trace": s["trace"],
    }
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    keep = ("answer", "verified", "unsupported", "calc_result", "steps", "trace")
    with open(TRACE_DIR / f"{time.strftime('%Y%m%d')}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"question": question, "s": round(time.time() - t0, 1), **{k: out[k] for k in keep}},
                           ensure_ascii=False) + "\n")
    return out
