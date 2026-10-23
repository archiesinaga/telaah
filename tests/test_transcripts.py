import torch

from telaah import transcripts
from telaah.bm25 import BM25


def test_chart_heavy_rule():
    assert transcripts.is_chart_heavy(3, 4000)  # several images
    assert transcripts.is_chart_heavy(0, 400)  # infographic page, little text
    assert not transcripts.is_chart_heavy(1, 3200)  # ordinary text/table page


def test_load_skips_pages_without_charts(tmp_path, monkeypatch):
    (tmp_path / "bca_2025_p12.txt").write_text("Intensitas Emisi 2025: 1,37", encoding="utf-8")
    (tmp_path / "bca_2025_p13.txt").write_text("TIDAK ADA GRAFIK", encoding="utf-8")
    (tmp_path / "mandiri_2025_p35.txt").write_text("", encoding="utf-8")
    monkeypatch.setattr(transcripts, "TRANSCRIPT_DIR", tmp_path)
    transcripts.load.cache_clear()
    assert transcripts.load() == {("bca_2025", 12): "Intensitas Emisi 2025: 1,37"}
    transcripts.load.cache_clear()


def _pages():
    return [
        {"doc_id": "bca_2025", "page": 12, "text": "Kinerja keberlanjutan"},
        {"doc_id": "bca_2025", "page": 40, "text": "Emisi karbon dikelola sesuai kebijakan"},
    ]


def test_bm25_tx_finds_transcribed_value_and_keeps_page_text(tmp_path, monkeypatch):
    monkeypatch.setattr(transcripts, "load", lambda: {("bca_2025", 12): "Intensitas Emisi 2025: 1,37 ton"})
    monkeypatch.setattr(transcripts, "bm25", lambda: BM25(_pages()))
    monkeypatch.setattr(transcripts, "BM25_FILE", tmp_path / "bm25_tx.pkl")
    transcripts.bm25_tx.cache_clear()
    idx = transcripts.bm25_tx()
    top = idx.search("intensitas emisi 1,37", 1)[0][0]
    assert idx.pages[top] == _pages()[0]  # found through the transcription, original text returned
    assert BM25(_pages()).search("intensitas 1,37", 1) == []  # without it the value is not searchable
    transcripts.bm25_tx.cache_clear()


def test_dense_filters_and_ranks(monkeypatch):
    keys = [("bca_2025", 12), ("mandiri_2025", 35), ("bca_2025", 80)]
    emb = torch.tensor([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
    monkeypatch.setattr(transcripts, "_embeddings", lambda: {"keys": keys, "emb": emb})
    hits = transcripts.dense([1.0, 0.0], 5, ["bca_2025"])
    assert [k for k, _ in hits] == [("bca_2025", 12), ("bca_2025", 80)]
    assert transcripts.dense([1.0, 0.0], 5, None, max_page=40)[0][0] == ("bca_2025", 12)


def test_dense_merge_in_retrieve(monkeypatch):
    import pytest

    R = pytest.importorskip("telaah.retrieve")

    class Hit:
        def __init__(self, p, s):
            self.payload, self.score = {"doc_id": "bca_2025", "page": p, "text": "t"}, s

    class Client:
        def query_points(self, *a, **k):
            return type("R", (), {"points": [Hit(40, 0.6), Hit(12, 0.3)]})()

    monkeypatch.setattr(R, "client", lambda: Client())
    monkeypatch.setattr(R, "embed", lambda qs: [[1.0, 0.0]])
    monkeypatch.setattr(R.transcripts, "USE", True)
    monkeypatch.setattr(R.transcripts, "dense", lambda *a: [(("bca_2025", 12), 0.8), (("bca_2025", 13), 0.5)])
    monkeypatch.setattr(R, "_page_lookup", lambda: {("bca_2025", 13): {"doc_id": "bca_2025", "page": 13, "text": "x"}})
    got = R._dense("intensitas emisi", 3, ["bca_2025"])
    assert [(c["page"], c["score"]) for c in got] == [(12, 0.8), (40, 0.6), (13, 0.5)]
    monkeypatch.setattr(R.transcripts, "USE", False)
    assert [c["page"] for c in R._dense("intensitas emisi", 3, ["bca_2025"])] == [40, 12]  # switch off: unchanged


def test_context_includes_transcript():
    from telaah.answer import build_context

    ctx = build_context([{"doc_id": "bca_2025", "page": 12, "text": "Kinerja keberlanjutan", "transcript": "Emisi: 1,37"}])
    assert "Emisi: 1,37" in ctx and "Kinerja keberlanjutan" in ctx and ctx.startswith("[bca_2025 p.12]")
