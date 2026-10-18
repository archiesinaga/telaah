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
    assert facts.parse_step("Berapa total aset BCA 2024 menurut Laporan Tahunan 2025?") == ("bca", "total_aset", 2024, 2025)
    # the report year alone does not say which year's figure is meant (q039 asked for a restated 2024 figure)
    assert facts.parse_step("Berapa laba bersih BRI setelah penyajian kembali di laporan tahunan 2025?") is None
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


def _hit(value, unit, raw):
    return {"value": value, "unit": unit, "raw": raw}


def test_derive_computes_only_what_is_asked():
    sh = {"indicator": "total_aset", "banks": ["bri", "bca"], "years": [2025],
          "hits": {("bri", 2025): _hit(2135371105, "jt", "2.135.371.105"), ("bca", 2025): _hit(1586829, "mi", "1.586.829")}}
    lines = facts.derive("Berapa total aset gabungan BRI dan BCA 2025 dalam triliun Rupiah?", sh)
    assert lines == ["Total gabungan 2025: 3.722,20 triliun Rupiah"]
    lines = facts.derive("Berapa selisih total aset BRI dan BCA 2025 (dalam miliar Rupiah)?", sh)
    assert lines == ["Selisih tertinggi (BRI) dan terendah (BCA) 2025: 548.542 miliar Rupiah"]


def test_derive_change_per_bank():
    sh = {"indicator": "npl_gross", "banks": ["bri", "btn"], "years": [2021, 2025],
          "hits": {("bri", 2021): _hit(3.08, "pct", "3,08%"), ("bri", 2025): _hit(3.29, "pct", "3,29%"),
                   ("btn", 2021): _hit(3.70, "pct", "3,70%"), ("btn", 2025): _hit(3.17, "pct", "3,17%")}}
    lines = facts.derive("Bandingkan NPL gross BRI dan BTN 2021 dan 2025, perubahan dan bank dengan perubahan terbesar", sh)
    assert "Perubahan BRI 2021 ke 2025: 0,21 poin persen" in lines
    assert "Perubahan BTN 2021 ke 2025: -0,53 poin persen" in lines
    assert "Perubahan terbesar (nilai absolut): BTN (-0,53 poin persen)" in lines


def test_question_years_and_skips():
    assert facts.parse_question("NPL BRI 2021 sampai 2025")[2] == [2021, 2022, 2023, 2024, 2025]
    assert facts.parse_question("NPL Mandiri 2025 dan NPL industri perbankan") is None


def test_scope_below_the_bank_is_not_answered_from_the_table():
    # an unanswerable district-level question must not get the bank-wide figure
    assert facts.parse_step("Berapa NPL gross BRI di Kecamatan Pulau Tiga per 2025?") is None
    assert facts.parse_question("Total aset BTN cabang Natuna 2025") is None


def test_step_year_must_be_asked_by_the_question():
    q = "Berapa laba bersih BRI tahun 2024 menurut laporan tahunan 2024, dan berapa angka 2024 setelah penyajian kembali di laporan tahunan 2025?"
    # the slipped step is corrected to the one asked year, read from the step's own report
    r = facts.answer_step("Berapa laba bersih BRI tahun 2025 setelah disajikan kembali?", q, ["bri_2025"])
    assert r["fact"]["year"] == 2024 and r["fact"]["doc"] == "bri_2025"
    assert facts.answer_step("Berapa laba bersih BRI tahun 2024?", q, ["bri_2024"])["fact"]["doc"] == "bri_2024"
    # several asked years: a step year outside them is left to RAG
    assert facts.answer_step("Berapa NPL BRI tahun 2023?", "NPL BRI 2021 dan 2025") is None


def test_unknown_banks():
    assert facts.unknown_banks("Berapa NPL gross Allo Bank tahun 2025 dan bandingkan dengan BRI.") == ["Allo Bank"]
    assert facts.unknown_banks("Berapa rasio NPL gross PT Bank Danamon Indonesia Tbk pada 2025?") == ["Bank Danamon Indonesia Tbk"]
    # known banks, the regulator and generic phrases are not unknown banks
    assert facts.unknown_banks("Berapa KPMM Bank Mandiri dan ROE Bank Mandiri 2025?") == []
    assert facts.unknown_banks("Menurut Peraturan Bank Indonesia, bank mana yang wajib ...") == []
    assert facts.parse_question("NPL Allo Bank dan BRI 2025") is None


def test_derive_mean_over_years():
    sh = {"indicator": "nim", "banks": ["bri"], "years": [2021, 2022],
          "hits": {("bri", 2021): _hit(6.89, "pct", "6,89%"), ("bri", 2022): _hit(6.75, "pct", "6,75%")}}
    assert facts.derive("Berapa rata-rata NIM BRI 2021-2022?", sh) == ["Rata-rata BRI 2021-2022: 6,82%"]
