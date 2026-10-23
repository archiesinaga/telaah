import os
import re
from functools import lru_cache

import torch
from qdrant_client import models

from telaah import colpali as colpali_index
from telaah.bm25 import bm25
from telaah.config import COLLECTION, RERANK_MODEL, TOP_K
from telaah.filters import detect_groups, doc_ids
from telaah.index import client, embed

CANDIDATES = 25
RRF_K = 60
PER_ENTITY = 3  # pages kept per entity on the single-prompt multi-entity path
ENTITY_PAGES = 5  # pages per entity when each entity is read on its own (gold pages sit at rank 1-6)
SUMMARY_MAX_PAGE = 45  # front 'highlights' pages of annual reports hold the headline figures
SUMMARY_N = 0  # front-page rankings off: dev recall@5 0.57 -> 0.72, seed 0.90 -> 0.85 (was 8)
REPORT_RE = re.compile(r"^(bri|bni|bca|btn|mandiri)_\d{4}$")
REPLACE_RE = re.compile(r"dicabut|menggantikan|pengganti|digantikan", re.I)
# the named regulation is the revoker ('dicabut oleh PBI X'): its own pages hold the answer
YEAR_RE = re.compile(r"(?<![0-9])(20[12][0-9])(?![0-9])")
TABLE_N = 4  # per-ranking size for the multi-year-table pages
COLPALI_N = 5  # pages taken from the ColPali (page-image) ranking
COLPALI_CHART_WEIGHT = 2  # ablation: weight 2 lifts chart recall 0.40 -> 0.80; weight 1 does nothing,
# weight 3 and weight 2 on every question cost table_lookup recall, so it is used for chart questions only
REVOKER_RE = re.compile(r"dicabut\s+oleh|mencabut", re.I)


def _dense(
    query: str,
    n: int,
    doc_ids: list[str] | None,
    max_page: int | None = None,
    pages: list[int] | None = None,
) -> list[dict]:
    must = []
    if doc_ids:
        must.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids)))
    if max_page:
        must.append(models.FieldCondition(key="page", range=models.Range(lte=max_page)))
    if pages:
        must.append(models.FieldCondition(key="page", match=models.MatchAny(any=pages)))
    flt = models.Filter(must=must) if must else None
    hits = client().query_points(
        COLLECTION, query=embed([query])[0], limit=n, query_filter=flt
    ).points
    return [{**h.payload, "score": h.score} for h in hits]


# Reports spell ratios out ("Non Performing Loan (NPL) Gross"), questions use the abbreviation: BM25 sees them as
# different words. Long forms are appended for the keyword ranking only (dense embeddings already relate them).
ALIASES = [
    (re.compile(r"\bnpl\b", re.I), "non performing loan kredit bermasalah"),
    (re.compile(r"\b(?:car|kpmm)\b", re.I), "kecukupan modal capital adequacy ratio penyediaan modal minimum"),
    (re.compile(r"\bldr\b", re.I), "loan to deposit ratio"),
    (re.compile(r"\bnim\b", re.I), "net interest margin marjin bunga bersih"),
    (re.compile(r"\bbopo\b", re.I), "beban operasional pendapatan operasional"),
    (re.compile(r"\bcasa\b", re.I), "current account saving account"),
]
USE_ALIASES = os.environ.get("TELAAH_ALIASES", "1") == "1"


def expand_aliases(query: str) -> str:
    if not USE_ALIASES:
        return query
    extra = [long for rx, long in ALIASES if rx.search(query)]
    return query + " " + " ".join(extra) if extra else query


def _sparse(
    query: str,
    n: int,
    doc_ids: list[str] | None,
    max_page: int | None = None,
    pages: list[int] | None = None,
) -> list[dict]:
    query = expand_aliases(query)
    idx = bm25()
    if pages:
        keep = set(pages)
        hits = idx.search(query, 400, doc_ids, max_page)
        return [{**idx.pages[i], "score": s} for i, s in hits if idx.pages[i]["page"] in keep][:n]
    return [{**idx.pages[i], "score": s} for i, s in idx.search(query, n, doc_ids, max_page)]


@lru_cache
def table_pages(doc_id: str) -> list[int]:
    """Front pages holding a multi-year table (header row with >=4 distinct years): the
    five-year financial summaries where headline figures live, often without any title."""
    idx = bm25()
    out = []
    for i in sorted(idx.by_doc.get(doc_id, ())):
        pg = idx.pages[i]
        if pg["page"] > SUMMARY_MAX_PAGE + 15:
            continue
        for line in pg["text"].splitlines():
            if line.count("|") >= 4 and len(set(YEAR_RE.findall(line))) >= 4:
                out.append(pg["page"])
                break
    return out


_colpali_warned = False


def _colpali_ranking(query: str, doc_ids: list[str]) -> list[dict]:
    """ColPali page ranking, or [] when the index is missing / does not cover these docs."""
    global _colpali_warned
    try:
        if not colpali_index.covers(doc_ids):
            return []
        return colpali_index.search(query, COLPALI_N, doc_ids)
    except colpali_index.QueryNotCached:  # cache-only mode: skip this query, keep ColPali for the cached ones
        print(f"[telaah] ColPali query not cached, skipped: {query[:80]}")
        return []
    except Exception as e:  # noqa: BLE001 - never let the optional visual path break retrieval
        if not _colpali_warned:
            print(f"[telaah] ColPali retrieval disabled: {type(e).__name__}: {e}")
            _colpali_warned = True
        return []


def _rrf(*rankings: list[dict]) -> list[dict]:
    fused: dict[tuple, float] = {}
    page: dict[tuple, dict] = {}
    for r in rankings:
        for rank, c in enumerate(r):
            key = (c["doc_id"], c["page"])
            fused[key] = fused.get(key, 0.0) + 1 / (RRF_K + rank + 1)
            page[key] = c
    return [{**page[k], "score": s} for k, s in sorted(fused.items(), key=lambda x: -x[1])]


@lru_cache
def reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(
        RERANK_MODEL,
        max_length=1024,
        device=os.environ.get("TELAAH_DEVICE", "cpu"),
        model_kwargs={"torch_dtype": "float16"},
    )


def _rerank(query: str, cands: list[dict]) -> list[dict]:
    if not cands:
        return cands
    scores = reranker().predict(
        [(query, c["text"][:4000]) for c in cands],
        batch_size=4,
        show_progress_bar=False,
        activation_fn=torch.nn.Identity(),  # raw logits: sigmoid saturates to 1.0 and ties
    )
    return [
        {**c, "rerank": float(s)}
        for c, s in sorted(zip(cands, scores), key=lambda x: -x[1])
    ]


def _one_group(query, doc_ids, hybrid, rerank, n, summary=True, colpali=True, colpali_weight=1):
    ranked = _dense(query, CANDIDATES, doc_ids)
    if hybrid:
        rankings = [ranked, _sparse(query, CANDIDATES, doc_ids)]
        if summary and doc_ids and all(REPORT_RE.match(d) for d in doc_ids):
            if SUMMARY_N:  # extra rankings limited to the front pages, so headline-figure pages surface
                rankings.append(_dense(query, SUMMARY_N, doc_ids, SUMMARY_MAX_PAGE))
                rankings.append(_sparse(query, SUMMARY_N, doc_ids, SUMMARY_MAX_PAGE))
            tp = sorted({p for d in doc_ids for p in table_pages(d)})
            if tp:
                rankings.append(_dense(query, TABLE_N, doc_ids, pages=tp))
                rankings.append(_sparse(query, TABLE_N, doc_ids, pages=tp))
        if colpali and doc_ids and colpali_weight > 0:
            rankings += [_colpali_ranking(query, doc_ids)] * colpali_weight
        ranked = _rrf(*rankings)
        if not rerank:
            ranked = ranked[:CANDIDATES]
    if rerank:
        ranked = _rerank(query, ranked)
    return ranked[:n]


def _with_replacements(groups: list[list[str]]) -> list[list[str]]:
    """'dicabut/menggantikan' questions: add the other docs of the same regulation series."""
    out = list(groups)
    known = {d for g in groups for d in g}
    for g in groups:
        series = {d.rsplit("_", 2)[0] for d in g if not REPORT_RE.match(d)}
        for s in series:
            rest = [d for d in doc_ids() if d.startswith(s + "_") and d not in known]
            if rest and rest not in out:
                out.append(rest)
    return out


def entity_groups(query: str) -> list[list[str]] | None:
    """Doc groups to read one at a time for a cross-document question, or None for the normal path.
    A bank named with two report years ('laporan 2024 ... laporan 2025') becomes two entities.
    'dicabut/menggantikan' questions keep the single-prompt path (replacement-series logic)."""
    if REPLACE_RE.search(query):
        return None
    groups = detect_groups(query)
    if len(groups) == 1 and len(groups[0]) == 2 and all(REPORT_RE.match(d) for d in groups[0]):
        if len(set(YEAR_RE.findall(query))) >= 2:
            groups = [[d] for d in groups[0]]
    return groups if len(groups) >= 2 else None


def retrieve_entity(query: str, doc_ids: list[str], n: int = ENTITY_PAGES) -> list[dict]:
    """Top pages of ONE entity's documents (same ranking as the single-group path)."""
    return _one_group(query, doc_ids, True, False, n, True, False, 0)


def retrieve(
    query: str,
    k: int = TOP_K,
    *,
    filter_docs: bool = True,
    hybrid: bool = True,
    rerank: bool = False,  # reranker gave no overall gain in the ablation
    summary: bool = True,
    per_entity: int = PER_ENTITY,
    colpali: bool = True,  # page-image ranking, used only for reports in data/colpali
    colpali_weight: int | None = None,  # times the ColPali ranking joins the RRF; None = auto
) -> list[dict]:
    if colpali_weight is None:  # auto: only chart/graph questions use the page-image ranking
        from telaah.vision import wants_image

        colpali_weight = COLPALI_CHART_WEIGHT if wants_image(query) else 0
    groups = detect_groups(query) if filter_docs else []
    if REPLACE_RE.search(query) and not REVOKER_RE.search(query):
        groups = _with_replacements(groups)
    if len(groups) <= 1:
        return _one_group(
            query, groups[0] if groups else None, hybrid, rerank, k, summary, colpali, colpali_weight
        )
    # fixed quota per entity, interleaved so every entity is represented
    per = [
        _one_group(query, g, hybrid, rerank, per_entity, summary, colpali, colpali_weight)
        for g in groups
    ]
    out, seen = [], set()
    for rank in range(per_entity):
        for r in per:
            if rank < len(r) and (r[rank]["doc_id"], r[rank]["page"]) not in seen:
                seen.add((r[rank]["doc_id"], r[rank]["page"]))
                out.append(r[rank])
    return out
