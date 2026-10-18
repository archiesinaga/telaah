from telaah import facts


def test_number_styles():
    assert facts.number_style(["1.586.829", "2,95%", "(24.043)"]) == "id"
    assert facts.number_style(["1,362,055", "2.1", "(14.8)"]) == "en"
    assert facts.parse_num("(74.093.750)", "id") == -74093750
    assert facts.parse_num("3,12%", "id") == 3.12
    assert facts.parse_num("1,362,055", "en") == 1362055
    assert facts.parse_num("Rasio", "id") is None


def test_indicator_labels():
    assert facts.indicator_of("NPL Gross") == "npl_gross"
    assert facts.indicator_of("NPL Nett") == "npl_net"
    assert facts.indicator_of("LLR/NPL Bruto (Coverage Ratio)") is None
    assert facts.indicator_of("Rasio Kecukupan Modal Tier 1 (CAR Tier 1)") == "tier1"
    assert facts.indicator_of("Return on Equity (ROE) - Tier 1 Capital") == "roe"
    assert facts.indicator_of("Rasio Kewajiban Penyediaan Modal Minimum (KPMM)") == "car"
    assert facts.indicator_of("Total Kredit 1") is None
    assert facts.indicator_of("Total Aset Produktif") is None
    assert facts.indicator_of("TOTAL ASET") == "total_aset"


def test_header_years_skip_change_columns():
    cells = ["In billion Rupiah", "2025", "2024", "YoY 2024-2025 (%)", "2023", "2022", "2021"]
    assert facts._header_years(cells) == {1: 2025, 2: 2024, 4: 2023, 5: 2022, 6: 2021}
    assert facts._header_years(["Uraian", "2025", "2024 *"]) == {1: 2025, 2: 2024}
    assert facts._header_years(["Uraian", "Nilai"]) == {}


def test_parse_step():
    assert facts.parse_step("Berapa NPL gross BRI tahun 2023 menurut Laporan Tahunan 2025?") == ("bri", "npl_gross", 2023, 2025)
    assert facts.parse_step("Berapa NPL net BNI 2024?") == ("bni", "npl_net", 2024, None)
    assert facts.parse_step("Berapa CAR Tier 1 BCA 2025?") == ("bca", "tier1", 2025, None)
    assert facts.parse_step("Berapa total aset BCA menurut Laporan Tahunan 2025?") == ("bca", "total_aset", 2025, 2025)
    # more than one figure, a chart reading, or the attributable share: left to RAG
    assert facts.parse_step("Berapa selisih NPL BRI dan BCA 2025?") is None
    assert facts.parse_step("Berapa NPL BRI 2024 dan 2025?") is None
    assert facts.parse_step("Menurut grafik, berapa total aset BRI 2025?") is None
    assert facts.parse_step("Berapa laba yang diatribusikan kepada pemilik Bank Mandiri 2025?") is None


def test_shown_uses_indonesian_notation():
    assert facts.shown({"raw": "1,362,055", "unit": "mi"}) == "Rp1.362.055 miliar Rupiah"
    assert facts.shown({"raw": "2.1", "unit": "pct"}) == "2,1%"
    assert facts.shown({"raw": "3,12%", "unit": "pct"}) == "3,12%"
    assert facts.shown({"raw": "2.135.371.105", "unit": "jt"}) == "Rp2.135.371.105 juta Rupiah"
