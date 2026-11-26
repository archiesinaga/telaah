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


def test_recall_at_k_groups_scores_each_step():
    from telaah.metrics import recall_at_k_groups

    step1 = [("a", p) for p in range(1, 6)]
    step2 = [("b", 1), ("b", 9)]
    assert recall_at_k_groups([step1, step2], [("b", 9)]) == 1.0  # gold in step 2's top 5
    assert recall_at_k([*step1, *step2], [("b", 9)]) == 0.0  # combined list: only step 1 was seen
    assert recall_at_k_groups([step1], [("a", 6)]) == 0.0
    assert recall_at_k_groups([], [("a", 1)]) == 0.0
    assert recall_at_k_groups([], []) == 1.0


def test_numeric_match_id_format():
    assert numeric_match("Totalnya Rp 123.456 miliar", "123.456")
    assert not numeric_match("Totalnya 999", "123.456")


def test_numeric_match_formats_are_read_per_number():
    # a comma decimal next to a dot-thousands figure in the same answer was read as 1476 (the "14,76" bug)
    assert numeric_match("Pertumbuhan 14,76% (nilai 6.139.468 dan 7.045.749)", "14,76%")
    assert numeric_match("naik 4.87%", "4,87%")  # English decimal vs Indonesian decimal
    assert numeric_match("Rp2,416,792 juta", "2.416.792")  # English thousands vs Indonesian thousands
    assert numeric_match("laba 1.234,56 miliar", "1.234,56")
    assert not numeric_match("pertumbuhan 14,76%", "1.476")  # decimal is not thousands


def test_numeric_match_ignores_trailing_decimal_zeros():
    assert numeric_match("NIM BNI 3,8% vs BTN 4,20%", "NIM BNI 3,80% vs BTN 4,2%")
    assert numeric_match("selisih 8,00 poin persen", "selisih 8 poin")
    assert numeric_match("BOPO 86%", "86,00%")
    assert not numeric_match("3,08%", "3,8%")  # an inner zero is a digit
    assert not numeric_match("Rp1.000 miliar", "1")  # thousands separator, not a decimal


def test_numeric_match_unit_conversion():
    # another unit word: convert, then round or truncate to gold's last printed digit
    assert numeric_match("adalah Rp328.309.681 juta [mandiri_2025 p.296]", "Rp328,30 triliun")  # truncated
    assert numeric_match("Rp154.987.000 juta", "Rp155 triliun")  # rounded
    assert numeric_match("Rp14.782.500 juta", "Rp14.783 miliar")
    assert not numeric_match("Rp154.200.000 juta", "Rp155 triliun")  # neither rounds nor truncates to 155
    assert not numeric_match("Rp970.233.234 juta", "Rp992,9 triliun")
    # same unit word or no unit word: still exact
    assert not numeric_match("Rp328,31 triliun", "Rp328,30 triliun")
    assert not numeric_match("Rp328.309.681", "Rp328,30 triliun")
    assert not numeric_match("16,63%", "16,6%")


def test_parse_score():
    from telaah.judge import parse_score

    assert parse_score('{"score": 1}') == 1.0
    assert parse_score('Hasil: {"score":0}') == 0.0
    assert parse_score("tidak tahu") is None


def test_refusal():
    assert refusal_correct(True, False) == 1.0
    assert refusal_correct(True, True) == 0.0
