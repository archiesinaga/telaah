"""Chart-page transcriptions as extra page text (pilot; TELAAH_TRANSCRIPTS=1 turns it on, default OFF).

Chart values often exist only in the page image, so neither BM25 nor the dense index can find them and the
LLM cannot read them. Pages that look chart-heavy (>= MIN_IMAGES images, or < MAX_TEXT chars of text) are
transcribed once by the vision model (`vision.transcribe_page`, cached in data/page_transcripts). With the
switch on:
- BM25 indexes page text + transcription (`bm25_tx`, cached in data/bm25_tx.pkl);
- the dense score of a transcribed page is max(page vector, transcription vector) (`dense`);
- a retrieved transcribed page carries its transcription into the LLM context (`annotate`).
Reports without transcriptions rank exactly as before.

    telaah transcribe --docs bca_2025 mandiri_2025   # Gemini, resumable, stops on the daily quota
    telaah transcripts-index                         # embed the transcriptions (bge-m3)
"""
import hashlib
import os
import pickle
import time
from functools import lru_cache

import torch

from telaah.bm25 import BM25, bm25
from telaah.config import RAW_DIR, ROOT
from telaah.vision import NO_CHART, TRANSCRIPT_DIR

USE = os.environ.get("TELAAH_TRANSCRIPTS", "0") == "1"
MIN_IMAGES = 2  # dev chart gold pages: median 3 images; text/table gold pages: 90% have <= 1
MAX_TEXT = 1000  # infographic pages have little extractable text (median page: ~3200 chars)
EMB_FILE = TRANSCRIPT_DIR / "embeddings.pt"
BM25_FILE = ROOT / "data" / "bm25_tx.pkl"
INTERVAL = float(os.environ.get("TRANSCRIBE_MIN_INTERVAL", "4.5"))  # flash-lite free tier: 15 requests/min


def is_chart_heavy(n_images: int, text_len: int) -> bool:
    return n_images >= MIN_IMAGES or text_len < MAX_TEXT


def chart_heavy_pages(doc_id: str) -> list[int]:
    import pymupdf

    with pymupdf.open(RAW_DIR / f"{doc_id}.pdf") as doc:
        return [i for i, pg in enumerate(doc.pages(), 1) if is_chart_heavy(len(pg.get_image_info()), len(pg.get_text()))]


@lru_cache
def load() -> dict[tuple[str, int], str]:
    """(doc_id, page) -> transcription, pages without charts left out."""
    out = {}
    for f in sorted(TRANSCRIPT_DIR.glob("*_p*.txt")):
        doc_id, page = f.stem.rsplit("_p", 1)
        text = f.read_text(encoding="utf-8").strip()
        if text and not text.upper().startswith(NO_CHART):
            out[(doc_id, int(page))] = text
    return out


def _signature(tx: dict) -> str:
    return hashlib.sha1(repr(sorted((k, len(v)) for k, v in tx.items())).encode()).hexdigest()


@lru_cache
def bm25_tx() -> BM25:
    """BM25 over page text + transcription; returned pages keep their original text."""
    tx = load()
    sig = _signature(tx)
    if BM25_FILE.exists():
        cached = pickle.loads(BM25_FILE.read_bytes())
        if cached["sig"] == sig:
            return cached["idx"]
    base = bm25()
    aug = [{**p, "text": p["text"] + "\n" + tx[k]} if (k := (p["doc_id"], p["page"])) in tx else p for p in base.pages]
    idx = BM25(aug)
    idx.pages = base.pages
    BM25_FILE.write_bytes(pickle.dumps({"sig": sig, "idx": idx}))
    return idx


def build_embeddings() -> None:
    from telaah.index import embed

    tx = load()
    keys = sorted(tx)
    emb = torch.tensor(embed([tx[k][:4000] for k in keys])) if keys else torch.zeros(0, 1)
    torch.save({"sig": _signature(tx), "keys": keys, "emb": emb}, EMB_FILE)
    print(f"embedded {len(keys)} transcriptions -> {EMB_FILE}")


@lru_cache
def _embeddings() -> dict:
    if not EMB_FILE.exists():
        return {"keys": [], "emb": torch.zeros(0, 1)}
    data = torch.load(EMB_FILE)
    if data["sig"] != _signature(load()):
        print("[telaah] transcription embeddings are stale: run `telaah transcripts-index`")
    return data


def dense(qvec: list[float], n: int, doc_ids: list[str] | None, max_page: int | None = None,
          pages: list[int] | None = None) -> list[tuple[tuple[str, int], float]]:
    """Top transcriptions by cosine (vectors are normalized), same filters as retrieve._dense."""
    data = _embeddings()
    if not data["keys"]:
        return []
    scores = data["emb"] @ torch.tensor(qvec)
    hits = []
    for (d, p), s in zip(data["keys"], scores.tolist()):
        if (doc_ids and d not in doc_ids) or (max_page and p > max_page) or (pages and p not in pages):
            continue
        hits.append(((d, p), s))
    return sorted(hits, key=lambda x: -x[1])[:n]


def annotate(chunks: list[dict]) -> list[dict]:
    tx = load()
    return [{**c, "transcript": tx[k]} if (k := (c["doc_id"], c["page"])) in tx else c for c in chunks]


def transcribe(docs: list[str], limit: int = 0) -> None:
    from telaah import vision

    todo = [(d, p) for d in docs for p in chart_heavy_pages(d)
            if not (TRANSCRIPT_DIR / f"{d}_p{p}.txt").exists()]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} chart-heavy pages to transcribe in {docs}", flush=True)
    for n, (d, p) in enumerate(todo, 1):
        t0 = time.time()
        try:
            text = vision.transcribe_page(d, p)
        except vision.DailyQuota:
            print(f"daily quota reached after {n - 1} pages; rerun after the reset (midnight Pacific) to continue")
            return
        except RuntimeError as e:
            print(f"[{n}/{len(todo)}] {d} p.{p} failed: {e}", flush=True)
            continue
        kind = "no chart" if text.upper().startswith(NO_CHART) else f"{len(text)} chars"
        print(f"[{n}/{len(todo)}] {d} p.{p}: {kind}", flush=True)
        time.sleep(max(0.0, INTERVAL - (time.time() - t0)))
    print("done; next: telaah transcripts-index")
