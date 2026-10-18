"""Regulation threshold vs one bank figure ("selisih KPMM BRI 2025 terhadap batas POJK 11/2016").

The 7B fails these as one RAG question (refuses, or mixes the arithmetic), so they are split:
  bank figure : the facts table
  threshold   : a percentage the RAG answer gives for the regulation, found on a regulation page; else one the
                question states ("angka 14% itu"); else RAG over the regulation's documents only.
  comparison  : Python; the answer is a template, so the 7B writes no number.
No threshold is typed in by hand.
"""
import re

from openai import OpenAI

from telaah import facts, tools
from telaah.answer import REFUSAL, answer_entity, ask, parse_citations
from telaah.config import LLM_API_KEY, LLM_BASE_URL, LLM_MAX_RETRIES
from telaah.filters import REG_RE, detect_groups

PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|persen\b)", re.I)
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
REG_WORD_RE = re.compile(r"\b(?:POJK|PADG|PBI|SEOJK|peraturan)\b", re.I)


def bank_fact(question: str) -> tuple[str, str, int, dict] | None:
    """(bank, indicator, year, hit) for the one ratio a regulation question compares; years inside the regulation
    reference ("POJK 11/POJK.03/2016", "PADG 23 Tahun 2025") are not the figure's year."""
    p = facts.parse_question(REG_RE.sub(" ", question))
    if not p:
        return None
    banks, inds, years, report_year = p
    if len(banks) != 1 or len(inds) != 1 or len(years) != 1:
        return None
    ind = next(iter(inds))
    if facts.INDICATORS[ind][0] != "pct":
        return None
    hit = facts.lookup(banks[0], ind, years[0], report_year or years[0])
    return (banks[0], ind, years[0], hit) if hit else None


def reg_group(question: str) -> tuple[str, list[str]] | None:
    """The regulation reference as written and its documents."""
    m = REG_RE.search(question)
    if not m:
        return None
    groups = detect_groups(m.group(0))
    return (m.group(0).strip(), groups[0]) if groups else None


def applies(question: str) -> bool:
    return bool(reg_group(question) and bank_fact(question))


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def states_pct(doc: str, page: int, num: str) -> bool:
    """The page writes `num` as a percentage ("14% (empat belas persen)"); a bare 14 is often an article or item
    number (POJK 11/2016 p.43 holds "14" but not the 14% threshold, which is on p.7)."""
    try:
        text = tools.read_page_text(doc, page)
    except KeyError:
        return False
    return bool(re.search(r"(?<![\d.,])" + re.escape(num) + r"\s*(?:%|persen\b)", text, re.I))


def find_threshold(answer: str, docs: list[str], pages: list[tuple[str, int]] | None = None,
                   skip: float | None = None) -> tuple[str, str, int] | None:
    """(number as written, doc, page): the first percentage in a sentence that cites or names the regulation,
    found on the cited regulation page or else on a retrieved regulation page (the 7B often cites a neighbour).
    `skip`: the bank's own figure, which such a sentence may also quote."""
    pages = [x for x in (pages or []) if x[0] in docs]
    for sent in SENT_RE.split(answer):
        cites = [(d, p) for d, p in parse_citations(sent) if d in docs]
        if not cites and not REG_WORD_RE.search(sent):
            continue
        for m in PCT_RE.finditer(sent):
            if skip is not None and abs(_num(m.group(1)) - skip) < 1e-9:
                continue
            for d, p in dict.fromkeys(cites + pages):
                if states_pct(d, p, m.group(1)):
                    return m.group(1), d, p
    return None


def answer(question: str) -> dict | None:
    """Same keys as `answer.ask`. Threshold, in order: the full-question RAG answer (reads the right rule most
    often), a percentage the question states, a regulation-only RAG answer (only when the first refused).
    No threshold -> the plain RAG answer unchanged; None only when the question is not of this kind."""
    rg, bf = reg_group(question), bank_fact(question)
    if not rg or not bf:
        return None
    reg, docs = rg
    bank, _, year, hit = bf
    r = ask(question)
    pages = list(r["retrieved"])
    found, source = find_threshold(r["answer"], docs, pages, hit["value"]), "rag"
    stated = sorted({m.group(1) for m in PCT_RE.finditer(REG_RE.sub(" ", question))})
    if not found and len(stated) == 1:
        found, source = (stated[0], None, None), "question"
    if not found and r["refused"]:
        llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
        sub = (f"{question}\nJawab HANYA angka batas/ambang yang ditetapkan {reg} (dalam persen) beserta "
               "sitasinya. Jangan menghitung dan jangan membahas data bank.")
        got, chunks, _, _ = answer_entity(llm, sub, docs)
        pages += [(c["doc_id"], c["page"]) for c in chunks]
        found = None if REFUSAL in got else find_threshold(got, docs, pages, hit["value"])
        source = "regulation_only"
    if not found:
        return {**r, "threshold_source": None}
    thr_raw, rdoc, rpage = found
    thr_txt = f"{thr_raw}% [{rdoc} p.{rpage}]" if rdoc else f"{thr_raw}% (angka yang disebut dalam pertanyaan)"
    diff = hit["value"] - _num(thr_raw)
    side = "di atas" if diff > 0 else "di bawah" if diff < 0 else "sama dengan"
    name = facts.BANK_NAME[bank]
    text = (f"Batas/ambang menurut {reg}: {thr_txt}. "
            f"{hit['label']} {name} tahun {year}: {facts.shown(hit)} [{hit['doc']} p.{hit['page']}]. "
            f"Selisihnya {facts.fmt(abs(diff))} poin persen, sehingga {name} berada {side} batas tersebut.")
    parts = [f"[{rdoc} p.{rpage}]\n{tools.read_page_text(rdoc, rpage)[:3000]}"] if rdoc and rpage else []
    parts += [f"[{hit['doc']} p.{hit['page']}]\n{facts.row_excerpt(hit['doc'], hit['page'], hit['label'])}",
              f"Hasil hitung (kalkulator): {facts.shown(hit)} - {thr_raw}% = {facts.fmt(diff)} poin persen"]
    return {"answer": text, "citations": ([(rdoc, rpage)] if rdoc else []) + [(hit["doc"], hit["page"])],
            "retrieved": pages + [(hit["doc"], hit["page"])], "context": "\n\n".join(parts),
            "refused": False, "threshold_source": source}


