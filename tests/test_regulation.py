from telaah import regulation


def test_bank_fact_ignores_years_of_the_regulation_reference():
    b = regulation.bank_fact("Berapa KPMM Insentif menurut PADG 23 Tahun 2025, dan selisih KPMM Bank Mandiri 2025?")
    assert b[:3] == ("mandiri", "car", 2025)
    b = regulation.bank_fact("POJK 11/POJK.03/2016 mewajibkan modal inti 6%. Berapa selisih CAR Tier 1 BCA 2025?")
    assert b[:3] == ("bca", "tier1", 2025)
    assert regulation.bank_fact("Berapa KPMM minimum menurut POJK 11/POJK.03/2016?") is None


def test_threshold_must_be_on_the_cited_regulation_page(monkeypatch):
    monkeypatch.setattr(regulation, "states_pct", lambda d, p, n: (d, p, n) == ("reg", 7, "14"))
    assert regulation.find_threshold("Batas atas adalah 14% dari ATMR [reg p.7].", ["reg"]) == ("14", "reg", 7)
    # a percentage cited to a page that does not hold it, or to another document, is not a threshold
    assert regulation.find_threshold("Batas atas adalah 14% [reg p.8].", ["reg"]) is None
    assert regulation.find_threshold("CAR BCA 29,8% [bca_2025 p.15].", ["reg"]) is None


def test_threshold_from_a_sentence_naming_the_regulation_on_a_retrieved_page(monkeypatch):
    monkeypatch.setattr(regulation, "states_pct", lambda d, p, n: (d, p, n) == ("reg", 7, "14"))
    ans = "KPMM BTN 19,02%, sedangkan batas atas menurut POJK 11 adalah 14% dari ATMR."
    assert regulation.find_threshold(ans, ["reg"], [("reg", 8), ("reg", 7)], 19.02) == ("14", "reg", 7)


def test_states_pct_needs_the_percent_form():
    assert regulation.states_pct("ojk_pojk_11_2016", 7, "14")
    assert regulation.states_pct("ojk_pojk_11_2016", 14, "6")
    assert not regulation.states_pct("ojk_pojk_11_2016", 43, "14")
