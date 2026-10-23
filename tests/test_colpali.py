import json

import torch

from telaah.colpali import PageIndex
from telaah.vision import wants_image


def _fake_index(tmp_path):
    """Two docs, two shards, pages with different vector counts and random unit vectors."""
    g = torch.Generator().manual_seed(0)
    truth = {}
    shards = []
    for doc, start, n_pages in [("doc_a", 1, 4), ("doc_b", 1, 3)]:
        pages = list(range(start, start + n_pages))
        lengths = [5 + (i % 3) for i in range(n_pages)]  # unequal lengths on purpose
        embs = [torch.nn.functional.normalize(torch.randn(n, 16, generator=g), dim=-1) for n in lengths]
        for p, e in zip(pages, embs):
            truth[(doc, p)] = e
        name = f"{doc}_{start:05d}.pt"
        torch.save(
            {"doc_id": doc, "pages": pages, "lengths": lengths, "emb": torch.cat(embs).half()},
            tmp_path / name,
        )
        shards.append(name)
    rows = [{"doc_id": d, "page": p, "shard": f"{d}_00001.pt"} for d, p in truth]
    (tmp_path / "manifest.json").write_text(json.dumps({"model": "fake", "pages": rows}))
    return PageIndex(tmp_path), truth


def test_page_ranks_first_for_its_own_vectors(tmp_path):
    idx, truth = _fake_index(tmp_path)
    for key in [("doc_a", 3), ("doc_b", 2), ("doc_a", 1)]:
        hits = idx.search_embeddings(truth[key][:4], n=3)
        assert (hits[0][0], hits[0][1]) == key


def test_doc_filter_and_coverage(tmp_path):
    idx, truth = _fake_index(tmp_path)
    hits = idx.search_embeddings(truth[("doc_a", 2)], n=10, doc_ids=["doc_b"])
    assert {h[0] for h in hits} == {"doc_b"} and len(hits) == 3
    assert idx.covers(["doc_a", "doc_b"]) and not idx.covers(["doc_a", "bni_2024"])
    assert not idx.covers([])
    assert idx.has_page("doc_a", 4) and not idx.has_page("doc_a", 5)


def test_maxsim_matches_bruteforce(tmp_path):
    idx, truth = _fake_index(tmp_path)
    q = torch.nn.functional.normalize(torch.randn(6, 16), dim=-1)
    got = {(d, p): s for d, p, s in idx.search_embeddings(q, n=99)}
    for key, e in truth.items():
        want = (q @ e.half().float().T).max(dim=1).values.sum().item()
        assert abs(got[key] - want) < 1e-3


def test_wants_image():
    assert wants_image("Menurut grafik pertumbuhan kredit, berapa LDR?")
    assert not wants_image("Berapa total aset BRI tahun 2025?")


def test_auto_weight_only_for_chart_questions(monkeypatch):
    import pytest

    R = pytest.importorskip("telaah.retrieve")
    from telaah import colpali as cp

    def pg(p):
        return {"doc_id": "bri_2025", "page": p, "text": "t", "score": 1.0}

    calls = []
    monkeypatch.setattr(R, "detect_groups", lambda q: [["bri_2025"]])
    monkeypatch.setattr(R, "_dense", lambda q, n, d, max_page=None, pages=None: [pg(i) for i in (10, 11, 12)])
    monkeypatch.setattr(R, "_sparse", lambda q, n, d, max_page=None, pages=None: [pg(i) for i in (11, 10, 15)])
    monkeypatch.setattr(R, "table_pages", lambda d: [])
    monkeypatch.setattr(cp, "covers", lambda ids: True)
    monkeypatch.setattr(cp, "search", lambda q, n, ids: calls.append(q) or [pg(328)])

    plain = [c["page"] for c in R.retrieve("Berapa total aset BRI 2025?")]
    assert calls == [] and 328 not in plain  # ordinary question: ColPali is never called
    chart = [c["page"] for c in R.retrieve("Menurut grafik, berapa laba operasional BRI?")]
    assert len(calls) == 1 and 328 in chart  # chart question: weight 2 lets the page in
    R.retrieve("Menurut grafik, berapa laba?", colpali_weight=0)
    assert len(calls) == 1  # explicit 0 disables it


def test_query_cache_and_cache_only(monkeypatch):
    from telaah import colpali as cp

    cached = torch.ones(3, 16)
    monkeypatch.setattr(cp, "_query_cache", lambda: {"grafik laba": cached})
    monkeypatch.setattr(cp, "_encoder", lambda: (_ for _ in ()).throw(AssertionError("model loaded")))
    monkeypatch.setattr(cp, "CACHE_ONLY", True)
    cp.encode_query.cache_clear()
    assert cp.encode_query("grafik laba") is cached  # hit: no model load
    import pytest

    with pytest.raises(cp.QueryNotCached):
        cp.encode_query("grafik aset")  # miss in cache-only mode: no model load either
    cp.encode_query.cache_clear()
