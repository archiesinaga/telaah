"""Encode the ColPali queries of a question set ahead of an eval, on the GPU, into data/colpali/query_cache.pt.

ColQwen2 on the CPU needs ~4.4 GB of RAM on top of the eval and the 7B server, which the 15.7 GB laptop does not
have. Run this with Ollama idle (GPU free), then run the eval with TELAAH_COLPALI_CACHE_ONLY=1.

    TELAAH_COLPALI_DEVICE=cuda .venv/Scripts/python eval/bench/colpali_cache.py dev.jsonl --ids _new_ids_chart.txt

Only questions that trip `wants_image` are encoded: the others never use the ColPali ranking. Agent sub-questions
are written by the LLM at run time and cannot be cached here; they miss and skip ColPali.
"""
import argparse

import torch

from common import HERE, read_jsonl
from telaah import colpali
from telaah.vision import wants_image

ap = argparse.ArgumentParser()
ap.add_argument("questions", help="question file in eval/bench (dev only)")
ap.add_argument("--ids", help="file with the question ids to encode (default: all)")
a = ap.parse_args()

ids = set((HERE / a.ids).read_text().split()) if a.ids else None
queries = [q["question"] for q in read_jsonl(HERE / a.questions)
           if (ids is None or q["id"] in ids) and wants_image(q["question"])]
cache = torch.load(colpali.QUERY_CACHE) if colpali.QUERY_CACHE.exists() else {}
todo = [q for q in queries if q not in cache]
for n, q in enumerate(todo, 1):
    cache[q] = colpali.encode_query(q)
    print(f"[{n}/{len(todo)}] {q[:70]}", flush=True)
torch.save(cache, colpali.QUERY_CACHE)
print(f"{len(queries)} image questions, {len(todo)} encoded, cache now {len(cache)} queries -> {colpali.QUERY_CACHE}")
