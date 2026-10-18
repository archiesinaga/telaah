"""Send multi-step questions to the agent, single figures in the facts table to a table lookup, and other
single-fact questions to plain RAG (no extra LLM call)."""
import re

from telaah import facts, regulation
from telaah.agent import DERIVE_RE, USE_FACTS, run_agent
from telaah.answer import ask
from telaah.retrieve import entity_groups

# narrower than agent.CALC_RE: "jumlah" and "rata-rata" also appear in plain single-fact questions
CALC_RE = re.compile(r"selisih|perbedaan|beda\b|berapa kali|total gabungan", re.I)  # "dibandingkan 2024" is a plain growth question
# a regulation threshold (with or without a bank figure) reads better through plain RAG on the 7B (0.63 vs 0.13 on the regulation tasks)
REGULATION_RE = re.compile(r"\b(?:POJK|PADG|PBI|SEOJK)\b", re.I)


def route(question: str) -> str:
    """'agent' for comparisons across documents or arithmetic over several facts, 'facts' for one figure the
    facts table holds (RAG sometimes reads a neighbouring page: q002 took 60,64 T from p42), else 'rag'.

    A multi-year trend of one bank is 'rag' unless the table covers it (7B: 0.50 vs 0.00 through the LLM-planned agent)."""
    if REGULATION_RE.search(question):
        # threshold vs one bank figure in the table: split (`regulation.answer`); other regulation questions: RAG
        return "regulation" if USE_FACTS and regulation.applies(question) else "rag"
    if USE_FACTS and facts.sheet(question):  # every figure is in the facts table: lookups + Python arithmetic
        return "agent"
    if entity_groups(question) or CALC_RE.search(question) or DERIVE_RE.search(question):
        return "agent"
    if USE_FACTS and facts.answer_step(question):
        return "facts"
    return "rag"


def run_routed(question: str) -> dict:
    """Same result keys as `agent.run_agent`; `route` says which path answered."""
    path = route(question)
    if path == "agent":
        return {**run_agent(question), "route": "agent"}
    r = facts.answer_step(question) if path == "facts" else regulation.answer(question) if path == "regulation" else None
    if r is None:
        path, r = "rag", ask(question)
    return {**r, "route": path, "verified": None, "unsupported": [], "calc_result": None, "steps": [], "trace": []}
