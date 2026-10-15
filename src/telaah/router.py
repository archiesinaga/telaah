"""Send multi-step questions to the agent and single-fact questions to plain RAG (no extra LLM call)."""
import re

from telaah.agent import DERIVE_RE, run_agent
from telaah.answer import ask
from telaah.retrieve import entity_groups

# narrower than agent.CALC_RE: "jumlah" and "rata-rata" also appear in plain single-fact questions
CALC_RE = re.compile(r"selisih|perbedaan|beda\b|berapa kali|total gabungan", re.I)  # "dibandingkan 2024" is a plain growth question
TREND_RE = re.compile(r"tren|selama|dari tahun|antara tahun|20[0-9]{2}\s*(?:-|–|sampai|hingga|s\.d\.?)\s*20[0-9]{2}", re.I)


def route(question: str) -> str:
    """'agent' for comparisons across documents, arithmetic over several facts, or multi-year trends; else 'rag'."""
    if entity_groups(question) or CALC_RE.search(question) or DERIVE_RE.search(question) or TREND_RE.search(question):
        return "agent"
    return "rag"


def run_routed(question: str) -> dict:
    """Same result keys as `agent.run_agent`; `route` says which path answered."""
    if route(question) == "agent":
        return {**run_agent(question), "route": "agent"}
    r = ask(question)
    return {**r, "route": "rag", "verified": None, "unsupported": [], "calc_result": None, "steps": [], "trace": []}
