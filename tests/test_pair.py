from telaah import facts


def _step(q, doc, page, label, year, value, raw, unit):
    return {"q": q, "status": "ok", "fact": {"doc": doc, "page": page, "label": label, "year": year, "value": value,
                                              "raw": raw, "unit": unit, "support": 1}}


NIM = [_step("BNI nim 2025", "bni_2025", 29, "Net Interest Margin (NIM)", 2025, 3.8, "3.8", "pct"),
       _step("BTN nim 2025", "btn_2025", 28, "Net Interest Margin (NIM)", 2025, 4.2, "4,20", "pct")]
Q = "Bandingkan NIM BNI dan BTN pada tahun 2025 menurut Laporan Tahunan 2025 masing-masing. Bank mana yang lebih tinggi, dan berapa selisihnya?"


def test_pair_comparison_lists_both_values_gap_and_winner():
    out = " ".join(facts.pair_comparison(Q, NIM))
    assert "BNI 3,8% [bni_2025 p.29]" in out and "BTN 4,20% [btn_2025 p.28]" in out
    assert "Selisih 0,40 poin persen (4,20 - 3,80); BTN lebih tinggi dibandingkan BNI" in out


def test_pair_comparison_money_uses_the_asked_unit():
    steps = [_step("BCA laba bersih 2022", "bca_2025", 15, "Laba", 2022, 40763.0, "40.763", "mi"),
             _step("Bank Mandiri laba bersih 2022", "mandiri_2025", 38, "Laba", 2022, 44952.0, "44.952", "mi")]
    out = " ".join(facts.pair_comparison("Berapa selisih laba bersih antara BCA dan Bank Mandiri pada tahun 2022, dan bank mana yang lebih tinggi?", steps))
    assert "BCA Rp40,76 triliun" in out and "Bank Mandiri Rp44,95 triliun" in out and "Selisih 4,19 triliun Rupiah (44,95 - 40,76)" in out


def test_pair_comparison_declines_other_questions():
    assert facts.pair_comparison("Berapa pertumbuhan NIM BNI dan BTN pada tahun 2025?", NIM) is None
    assert facts.pair_comparison("Berapa NIM BNI dan BTN pada tahun 2025?", NIM) is None  # no comparison asked
    assert facts.pair_comparison(Q, NIM[:1]) is None
    assert facts.pair_comparison(Q, [NIM[0], {**NIM[1], "status": "failed"}]) is None
    assert facts.pair_comparison(Q, [NIM[0], _step("BTN nim 2024", "btn_2025", 28, "NIM", 2024, 4.2, "4,20", "pct")]) is None
