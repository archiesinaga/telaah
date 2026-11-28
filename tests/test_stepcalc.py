from telaah import stepcalc


def step(q, a, cite):
    return {"q": q, "answer": a, "citations": [cite], "status": "ok"}


def test_figure_reads_the_stated_value_and_unit():
    f = stepcalc.figure("Total pendapatan segmen Singapura BRI pada tahun 2024 adalah 585.615 juta Rupiah [bri_2024 p.1184].")
    assert (f["value"], f["exp"], f["cur"]) == (585615.0, 6, True)
    assert stepcalc.figure("Nilai Giro BI Mandiri tahun 2023 adalah Rp108,61 triliun [mandiri_2024 p.403].")["exp"] == 12
    assert stepcalc.figure("Pendapatan Bunga BNI pada tahun 2023 adalah 40,669,669 Rupiah [bni_2024 p.1516].")["value"] == 40669669
    assert stepcalc.figure("NPL gross BRI per 31 Desember 2024 adalah 2,78% [bri_2024 p.31].")["pct"]
    assert stepcalc.figure("TIDAK DITEMUKAN") is None
    assert stepcalc.figure("Laba tahun 2024 adalah 1.000 juta dan 2023 adalah 900 juta.") is not None  # after the last 'adalah'
    assert stepcalc.figure("Nilainya adalah 1.000 juta atau 1 miliar.") is None  # two figures: ambiguous


def test_periods_ignore_the_named_report():
    assert stepcalc.periods("Berapa nilai X tahun 2023 (menurut Laporan Tahunan 2024)?") == ["2023"]
    assert stepcalc.periods("Selisih X antara 2024 dan 2023 dalam Laporan Tahunan PT Bank Mandiri (Persero) Tbk 2024?") == ["2023", "2024"]


def test_mixed_units_are_converted_before_the_difference():
    q = "Berapa besar selisih nilai Giro pada Bank Indonesia Bank Mandiri pada tahun 2024 dibandingkan dengan tahun 2023?"
    steps = [step("Berapa nilai Giro BI Mandiri pada tahun 2023?", "Pada tahun 2023 nilainya adalah Rp108,61 triliun [mandiri_2024 p.403].", ("mandiri_2024", 403)),
             step("Berapa nilai Giro BI Mandiri pada tahun 2024?", "Nilainya pada tahun 2024 adalah Rp105.146.044 juta [mandiri_2024 p.30].", ("mandiri_2024", 30))]
    line = stepcalc.answer(q, steps)[0]
    assert "3.463.956 juta Rupiah" in line and "turun" in line and "[mandiri_2024 p.403] [mandiri_2024 p.30]" in line


def test_unit_word_missing_on_one_side_and_growth():
    q = "Berapa pertumbuhan laba BTN dari 2024 ke 2025?"
    steps = [step("Berapa laba BTN tahun 2025?", "Laba BTN tahun 2025 adalah 52.899 juta Rupiah [btn_2025 p.1294].", ("btn_2025", 1294)),
             step("Berapa laba BTN tahun 2024?", "Laba BTN tahun 2024 adalah 61.521 [btn_2025 p.1294].", ("btn_2025", 1294))]
    line = stepcalc.answer(q, steps)[0]
    assert "-14,01%" in line and line.count("[btn_2025 p.1294]") == 1


def test_falls_back_when_unsure():
    q = "Berapa selisih pendapatan Singapura BRI antara 31 Desember 2024 dan 31 Desember 2023?"
    same = [step("Berapa pendapatan Singapura BRI 31 Desember 2024?", "Nilainya adalah 585.615 juta [bri_2024 p.1184].", ("bri_2024", 1184)),
            step("Berapa pendapatan Singapura BRI 31 Desember 2023?", "Nilainya adalah 585.615 juta [bri_2024 p.1184].", ("bri_2024", 1184))]
    assert stepcalc.answer(q, same) is None  # one column read twice
    two_banks = [step("Berapa laba BRI 2024?", "adalah 10 juta", ("bri_2024", 1)), step("Berapa laba BNI 2024?", "adalah 9 juta", ("bni_2024", 1))]
    assert stepcalc.answer("Berapa selisih laba BRI dan BNI tahun 2024?", two_banks) is None
    pts = [step("Berapa NPL BRI 2023?", "adalah 3,12% [bri_2024 p.31]", ("bri_2024", 31)), step("Berapa NPL BRI 2024?", "adalah 2,78% [bri_2024 p.31]", ("bri_2024", 31))]
    assert stepcalc.answer("Berapa selisih NPL BRI antara 2023 dan 2024?", pts) is None  # points: calculator prompt
    assert stepcalc.answer("Berapa rasio laba BRI 2023 dan 2024?", pts) is None  # neither growth nor difference


def test_falls_back_on_implausible_ratio():
    q = "Berapa pertumbuhan beban BTN dari 2024 ke 2025?"
    unit_dropped = [step("Berapa beban BTN tahun 2024?", "Beban BTN tahun 2024 adalah 6,14 juta [btn_2025 p.309].", ("btn_2025", 309)),
                    step("Berapa beban BTN tahun 2025?", "Beban BTN tahun 2025 adalah 7.045.749 [btn_2025 p.309].", ("btn_2025", 309))]
    assert stepcalc.answer(q, unit_dropped) is None  # dev bd0225: 114.751.512% growth before the guard
    wrong_row = [step("Berapa X Mandiri tahun 2023?", "adalah 137.677 juta [mandiri_2024 p.1448]", ("mandiri_2024", 1448)),
                 step("Berapa X Mandiri tahun 2024?", "adalah 82.065.670 juta [mandiri_2024 p.1448]", ("mandiri_2024", 1448))]
    assert stepcalc.answer("Berapa selisih X Mandiri antara 2023 dan 2024?", wrong_row) is None  # same unit, 596x apart
    big_but_real = [step("Berapa laba Mandiri tahun 2024?", "adalah Rp1.705 juta [mandiri_2024 p.433]", ("mandiri_2024", 433)),
                    step("Berapa laba Mandiri tahun 2025?", "adalah Rp6.115 juta [mandiri_2025 p.358]", ("mandiri_2025", 358))]
    assert "258,65%" in stepcalc.answer("Berapa pertumbuhan laba Mandiri dari 2024 ke 2025?", big_but_real)[0]  # dev bd0221 stays


def bank_step(doc, a, page):
    return {"q": "x", "answer": a, "citations": [(doc, page)], "status": "ok", "docs": [doc]}


def test_pair_answer_writes_gap_and_winner_for_two_banks():
    q = "Mana yang lebih tinggi, total tabungan BRI atau Bank Mandiri per 31 Desember 2025? Sebutkan selisihnya."
    steps = [bank_step("bri_2025", "Total tabungan adalah 587.585.862 juta Rupiah [bri_2025 p.322].", 322),
             bank_step("mandiri_2025", "Total tabungan adalah Rp616.814.451 juta [mandiri_2025 p.5].", 5)]
    lines = stepcalc.pair_answer(q, steps)
    assert "Selisih 29.228.589 juta Rupiah; Bank Mandiri lebih tinggi dibandingkan BRI." in lines[1]
    assert "[bri_2025 p.322] [mandiri_2025 p.5]" in lines[0]


def test_pair_answer_declines_when_unsure():
    q = "Berapa selisih CKPN antara BRI dan Bank Mandiri per 31 Desember 2025?"
    ok = [bank_step("bri_2025", "CKPN adalah 10 juta [bri_2025 p.1].", 1), bank_step("mandiri_2025", "CKPN adalah 12 juta [mandiri_2025 p.2].", 2)]
    assert stepcalc.pair_answer(q, ok) is not None
    assert stepcalc.pair_answer(q, [ok[0], {**ok[1], "status": "failed"}]) is None  # a failed step
    assert stepcalc.pair_answer(q, [ok[0], bank_step("bri_2025", "CKPN adalah 12 juta [bri_2025 p.2].", 2)]) is None  # same bank
    assert stepcalc.pair_answer(q, [bank_step("bri_2025", "CKPN adalah 10.", 1), bank_step("mandiri_2025", "CKPN adalah 12.", 2)]) is None  # no unit word: scale unknown
    assert stepcalc.pair_answer("Berapa pertumbuhan CKPN BRI dan Bank Mandiri?", ok) is None  # not a comparison
