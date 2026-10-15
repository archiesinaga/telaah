from telaah.answer import parse_citations
from telaah.ingest.parse import page_chunks
from telaah.metrics import citation_accuracy, numeric_match, recall_at_k, refusal_correct


def test_parse_citations():
    t = "NPL 2,1% [bank_x_2024 p.12] dan CAR 20% [bank_x_2024 p.13]."
    assert parse_citations(t) == [("bank_x_2024", 12), ("bank_x_2024", 13)]


def test_page_chunks_skips_empty():
    assert page_chunks("d", {1: "a", 2: "  "}) == [{"doc_id": "d", "page": 1, "text": "a"}]


def test_recall_and_citation():
    gold = [("d", 3)]
    assert recall_at_k([("d", 1), ("d", 3)], gold) == 1.0
    assert recall_at_k([("d", 1)], gold) == 0.0
    assert citation_accuracy([("d", 3)], gold) == 1.0
    assert citation_accuracy([("d", 4)], gold) == 0.0
    assert citation_accuracy([], []) == 1.0


def test_numeric_match_id_format():
    assert numeric_match("Totalnya Rp 123.456 miliar", "123.456")
    assert not numeric_match("Totalnya 999", "123.456")


def test_parse_score():
    from telaah.judge import parse_score

    assert parse_score('{"score": 1}') == 1.0
    assert parse_score('Hasil: {"score":0}') == 0.0
    assert parse_score("tidak tahu") is None


def test_refusal():
    assert refusal_correct(True, False) == 1.0
    assert refusal_correct(True, True) == 0.0
