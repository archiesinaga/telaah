"""ColPali / ColQwen2 page-image retrieval over the index built on Kaggle (data/colpali).

Pages are indexed as multi-vector embeddings (about 747 vectors x 128 dims per page, fp16).
A query is scored against a page with MaxSim: for each query vector take its best match among the
page's vectors, then sum over the query vectors.

Only a few reports are indexed (see data/colpali/manifest.json). `covers()` tells the caller
whether a set of doc_ids can be searched, so a partial index never biases the ranking.

The query encoder (ColQwen2, ~2B params) runs on CPU in bf16 by default so the 7B LLM keeps the
GPU. Set TELAAH_COLPALI_DEVICE=cuda to use the GPU instead.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import torch

from telaah.config import COLPALI_DIR, COLPALI_MODEL

QUERY_CACHE = Path(COLPALI_DIR) / "query_cache.pt"  # query embeddings encoded ahead on the GPU, see eval/bench/colpali_cache.py
# 1 = never load ColQwen2: a query missing from QUERY_CACHE raises QueryNotCached and the caller skips ColPali
CACHE_ONLY = os.environ.get("TELAAH_COLPALI_CACHE_ONLY", "0") == "1"


class QueryNotCached(Exception):
    pass


class PageIndex:
    """All page embeddings in RAM (fp16), searched shard by shard."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        manifest = json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))
        self.model_name = manifest.get("model")
        names = sorted({r["shard"] for r in manifest["pages"]})
        self.shards = []  # one entry per shard file
        self.docs: set[str] = set()
        self.page_set: set[tuple[str, int]] = set()
        for name in names:
            s = torch.load(self.dir / name, map_location="cpu")
            lengths = torch.tensor(s["lengths"], dtype=torch.long)
            # page number (0..P-1 inside the shard) of every vector row
            owner = torch.repeat_interleave(torch.arange(len(lengths)), lengths)
            self.shards.append(
                {"doc_id": s["doc_id"], "pages": list(s["pages"]), "emb": s["emb"], "owner": owner}
            )
            self.docs.add(s["doc_id"])
            self.page_set.update((s["doc_id"], p) for p in s["pages"])

    def covers(self, doc_ids: list[str]) -> bool:
        return bool(doc_ids) and all(d in self.docs for d in doc_ids)

    def has_page(self, doc_id: str, page: int) -> bool:
        return (doc_id, page) in self.page_set

    def search_embeddings(
        self, q: torch.Tensor, n: int, doc_ids: list[str] | None = None
    ) -> list[tuple[str, int, float]]:
        """q: (num_query_vectors, dim). Returns the top-n (doc_id, page, score), best first."""
        q = q.to(torch.float32)
        scored: list[tuple[str, int, float]] = []
        for sh in self.shards:
            if doc_ids and sh["doc_id"] not in doc_ids:
                continue
            sim = q @ sh["emb"].to(torch.float32).T  # (nq, vectors in shard)
            n_pages = len(sh["pages"])
            best = torch.full((q.shape[0], n_pages), float("-inf"))
            best.scatter_reduce_(
                1, sh["owner"].unsqueeze(0).expand(q.shape[0], -1), sim, reduce="amax"
            )
            page_scores = best.sum(0)  # MaxSim: sum over query vectors of the best page match
            scored += [(sh["doc_id"], p, float(s)) for p, s in zip(sh["pages"], page_scores)]
        scored.sort(key=lambda x: -x[2])
        return scored[:n]


def available() -> bool:
    return (Path(COLPALI_DIR) / "manifest.json").exists()


@lru_cache
def index() -> PageIndex:
    return PageIndex(COLPALI_DIR)


@lru_cache
def _encoder():
    from colpali_engine.models import ColQwen2, ColQwen2Processor

    device = os.environ.get("TELAAH_COLPALI_DEVICE", "cpu")
    dtype = torch.bfloat16 if device == "cpu" else torch.float16
    model = ColQwen2.from_pretrained(COLPALI_MODEL, torch_dtype=dtype, device_map=device).eval()
    return model, ColQwen2Processor.from_pretrained(COLPALI_MODEL)


@lru_cache
def _query_cache() -> dict[str, torch.Tensor]:
    return torch.load(QUERY_CACHE) if QUERY_CACHE.exists() else {}


@lru_cache(maxsize=1024)
def encode_query(query: str) -> torch.Tensor:
    if (hit := _query_cache().get(query)) is not None:
        return hit
    if CACHE_ONLY:
        raise QueryNotCached(query)
    model, processor = _encoder()
    with torch.inference_mode():
        batch = processor.process_queries([query]).to(model.device)
        return model(**batch)[0].to(torch.float32).cpu()  # (num_query_vectors, 128)


def covers(doc_ids: list[str]) -> bool:
    return available() and index().covers(doc_ids)


def has_page(doc_id: str, page: int) -> bool:
    return available() and index().has_page(doc_id, page)


@lru_cache
def _page_text() -> dict[tuple[str, int], str]:
    from telaah.bm25 import bm25

    return {(p["doc_id"], p["page"]): p["text"] for p in bm25().pages}


NO_TEXT = "(halaman ini hanya berisi gambar/grafik; tidak ada teks hasil ekstraksi)"


def search(query: str, n: int, doc_ids: list[str] | None = None) -> list[dict]:
    """Same shape as retrieve._dense: dicts with doc_id, page, text, score."""
    texts = _page_text()
    hits = index().search_embeddings(encode_query(query), n, doc_ids)
    return [
        {"doc_id": d, "page": p, "text": texts.get((d, p)) or NO_TEXT, "score": s, "colpali": True}
        for d, p, s in hits
    ]
