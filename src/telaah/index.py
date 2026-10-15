import json
import os
import uuid
from functools import lru_cache

from qdrant_client import QdrantClient, models

from telaah.config import COLLECTION, EMBED_MODEL, PROCESSED_DIR, QDRANT_PATH


@lru_cache
def embedder():
    from sentence_transformers import SentenceTransformer

    # CPU by default: keeps VRAM free for the LLM. Set TELAAH_DEVICE=cuda for indexing.
    return SentenceTransformer(EMBED_MODEL, device=os.environ.get("TELAAH_DEVICE", "cpu"))


@lru_cache
def client() -> QdrantClient:
    return QdrantClient(path=QDRANT_PATH)


def embed(texts: list[str]) -> list[list[float]]:
    return embedder().encode(texts, normalize_embeddings=True, batch_size=8).tolist()


def build_index() -> None:
    chunks = [
        json.loads(l)
        for f in sorted(PROCESSED_DIR.glob("*.jsonl"))
        for l in f.read_text(encoding="utf-8").splitlines()
        if l
    ]
    if not chunks:
        raise SystemExit("No chunks. Put PDFs in data/raw and run `telaah ingest`.")
    c = client()
    if c.collection_exists(COLLECTION):
        c.delete_collection(COLLECTION)
    c.create_collection(
        COLLECTION,
        vectors_config=models.VectorParams(
            size=len(embed(["x"])[0]), distance=models.Distance.COSINE
        ),
    )
    for i in range(0, len(chunks), 32):
        batch = chunks[i : i + 32]
        vecs = embed([b["text"][:4000] for b in batch])
        c.upsert(
            COLLECTION,
            points=[
                models.PointStruct(id=str(uuid.uuid4()), vector=v, payload=b)
                for v, b in zip(vecs, batch)
            ],
        )
    print(f"indexed {len(chunks)} pages")
