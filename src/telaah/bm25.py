import json
import math
import pickle
import re
from collections import Counter, defaultdict
from functools import lru_cache

from telaah.config import ROOT, PROCESSED_DIR

CACHE = ROOT / "data" / "bm25.pkl"
TOKEN_RE = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*")
K1, B = 1.5, 0.75


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class BM25:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lens = []
        for i, p in enumerate(pages):
            toks = tokenize(p["text"])
            self.lens.append(len(toks))
            for t, c in Counter(toks).items():
                self.postings[t].append((i, c))
        self.avg = sum(self.lens) / len(self.lens)
        self.by_doc: dict[str, set[int]] = defaultdict(set)
        for i, p in enumerate(pages):
            self.by_doc[p["doc_id"]].add(i)

    def search(
        self, query: str, k: int, doc_ids: list[str] | None = None, max_page: int | None = None
    ) -> list[tuple[int, float]]:
        allowed = None
        if doc_ids:
            allowed = set().union(*(self.by_doc.get(d, set()) for d in doc_ids))
        n = len(self.pages)
        scores: dict[int, float] = defaultdict(float)
        for t in set(tokenize(query)):
            post = self.postings.get(t)
            if not post:
                continue
            idf = math.log(1 + (n - len(post) + 0.5) / (len(post) + 0.5))
            for i, tf in post:
                if allowed is not None and i not in allowed:
                    continue
                if max_page is not None and self.pages[i]["page"] > max_page:
                    continue
                norm = tf + K1 * (1 - B + B * self.lens[i] / self.avg)
                scores[i] += idf * tf * (K1 + 1) / norm
        return sorted(scores.items(), key=lambda x: -x[1])[:k]


@lru_cache
def bm25() -> BM25:
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    pages = [
        json.loads(l)
        for f in sorted(PROCESSED_DIR.glob("*.jsonl"))
        for l in f.read_text(encoding="utf-8").splitlines()
        if l
    ]
    idx = BM25(pages)
    CACHE.write_bytes(pickle.dumps(idx))
    return idx
