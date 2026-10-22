"""One figure of one bank in two years (growth or difference): read both numbers in ONE call over the pages the
whole question finds, then compute in Python. The agent's one-step-per-year plan loses the page (the later report
prints both years side by side; dev calculation: every step hit the gold page 4/19 vs 13/27 for the whole question).
Off unless TELAAH_TWOYEAR=1; any failed check returns None and the normal path answers."""
import json
import os
import re

from openai import OpenAI

from telaah import facts, tools, vision
from telaah.answer import REFUSAL, _chat, build_context, parse_citations
from telaah.config import LLM_API_KEY, LLM_BASE_URL, LLM_MAX_RETRIES
from telaah.filters import detect_groups
from telaah.retrieve import REPORT_RE, retrieve

USE_TWOYEAR = os.environ.get("TELAAH_TWOYEAR", "0") == "1"
GROWTH_RE = re.compile(r"pertumbuhan|tumbuh|kenaikan|penurunan|naik|turun", re.I)
DIFF_RE = re.compile(r"selisih|perbedaan|beda\b", re.I)
YEAR_RE = re.compile(r"\b20\d\d\b")
SYSTEM = """Kamu membaca tabel laporan keuangan. Dari konteks, ambil nilai item yang ditanyakan pada dua periode: {old} dan {new}.
Salin angka PERSIS seperti tertulis di dokumen (jangan dikonversi, jangan dihitung). Jika salah satu nilai tidak ada di konteks, isi null.
Keluarkan HANYA JSON: {{"old": "angka periode {old}", "new": "angka periode {new}", "doc": "doc_id halaman sumber", "page": nomor halaman}}"""


def applies(question: str) -> dict | None:
    """{'op', 'old', 'new'} for a single-bank question about growth/difference of one item between two years."""
    years = sorted(set(YEAR_RE.findall(question)))
    grow, diff = bool(GROWTH_RE.search(question)), bool(DIFF_RE.search(question))
    if len(years) != 2 or grow == diff or vision.wants_image(question):
        return None
    docs = {d for g in detect_groups(question) for d in g}  # 'Bank X 2024 ke 2025' names two reports of ONE bank
    if not docs or not all(REPORT_RE.match(d) for d in docs) or len({d.split("_")[0] for d in docs}) != 1:
        return None
    if facts.sheet(question, partial=True):
        return None
    return {"op": "growth_pct" if grow else "difference", "old": years[0], "new": years[1]}


def to_float(s: str) -> float | None:
    """'2.304.524' / '2,304,524' -> 2304524.0; '4,87' / '4.87' -> 4.87; None if not a plain figure."""
    s = s.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    if re.fullmatch(r"\d+[.,]\d+", s):
        return float(s.replace(",", "."))
    return float(s) if re.fullmatch(r"\d+", s) else None


def fmt(x: float) -> str:
    """Indonesian number, two decimals, integers bare (same as the benchmark golds)."""
    s = f"{x:,.2f}" if abs(x - round(x)) > 1e-9 else f"{round(x):,}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def compute(op: str, old: float, new: float) -> str | None:
    if op == "growth_pct":
        return fmt(round((new - old) / abs(old) * 100, 2)) + "%" if old else None
    return fmt(round(abs(new - old), 2))


def answer(question: str) -> dict | None:
    plan = applies(question)
    if not plan:
        return None
    chunks = retrieve(question)
    context = build_context(chunks, question)
    llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
    raw = _chat(llm, SYSTEM.format(old=plan["old"], new=plan["new"]), f"Konteks:\n{context}\n\nPertanyaan: {question}")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        old, new = to_float(str(data["old"])), to_float(str(data["new"]))
        cite = (re.match(r"[a-z]+_\d{4}", str(data["doc"])).group(0), int(data["page"]))  # the 7B writes "btn_2024 p.25"
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    retrieved = [(c["doc_id"], c["page"]) for c in chunks]
    if old is None or new is None or old == new or cite not in retrieved:
        return None
    if not tools.check_citation(*cite, f"{data['old']} {data['new']}")["supported"]:  # both numbers on the cited page
        return None
    result = compute(plan["op"], old, new)
    if result is None:
        return None
    what = "Pertumbuhan" if plan["op"] == "growth_pct" else "Selisih"
    text = (f"{what} antara {plan['old']} dan {plan['new']} adalah {result} "
            f"(nilai {plan['old']}: {data['old']}; nilai {plan['new']}: {data['new']}) [{cite[0]} p.{cite[1]}].")
    return {"answer": text, "citations": parse_citations(text), "retrieved": retrieved, "context": context,
            "refused": REFUSAL in text}
