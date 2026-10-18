from telaah import router
from telaah.filters import detect_groups


def test_single_fact_goes_to_rag(monkeypatch):
    monkeypatch.setattr(router, "entity_groups", lambda q: [])
    monkeypatch.setattr(router.facts, "answer_step", lambda q: None)
    assert router.route("Berapa total aset BRI pada tahun 2025?") == "rag"
    assert router.route("Berapa jumlah minimum anggota Dewan Komisaris bank umum?") == "rag"
    # a chart question that only asks for a unit is still one fact
    assert router.route("Menurut grafik BRI 2025, berapa total ekuitas BRI tahun 2025 (dalam triliun Rupiah)?") == "rag"


def test_comparison_and_trend_go_to_agent(monkeypatch):
    monkeypatch.setattr(router, "entity_groups", lambda q: [])
    assert router.route("Berapa selisih NPL BRI dan BCA?") == "agent"
    monkeypatch.setattr(router, "entity_groups", lambda q: [["bri_2025"], ["bca_2025"]])
    assert router.route("Bank mana yang aset totalnya lebih besar?") == "agent"


def test_arithmetic_questions_go_to_agent(monkeypatch):
    monkeypatch.setattr(router, "entity_groups", lambda q: [])
    assert router.route("Hitung laba bersih 2025 dibagi total aset akhir 2025 untuk BRI dalam persen.") == "agent"
    assert router.route("Berapa total laba gabungan BRI dan Mandiri dalam triliun Rupiah?") == "agent"


def test_named_source_report_limits_the_years():
    # the question spans 2021-2025 but must read the 2025 report (prior years are restated there)
    q = "Sebutkan NPL gross BRI 2021 sampai 2025. Gunakan data dari Laporan Tahunan 2025 masing-masing bank."
    assert detect_groups(q) == [["bri_2025"]]
    assert detect_groups("Sebutkan NPL gross BRI 2021 sampai 2025.") == [["bri_2024", "bri_2025"]]


def test_single_bank_trend_and_regulation_go_to_rag(monkeypatch):
    monkeypatch.setattr(router, "entity_groups", lambda q: [])
    monkeypatch.setattr(router.facts, "sheet", lambda q: None)
    monkeypatch.setattr(router.regulation, "applies", lambda q: False)
    assert router.route("Bagaimana tren NPL BRI dari 2021-2025?") == "rag"
    # a regulation threshold next to a bank figure the table lacks stays on plain RAG (7B: 0.63 vs 0.13 via agent)
    monkeypatch.setattr(router, "entity_groups", lambda q: [["bri_2025"]])
    assert router.route("Berapa selisih CAR Tier 1 BRI 2025 terhadap batas modal inti POJK 11/POJK.03/2016?") == "rag"
    assert router.route("Berapa ambang NPL gross dalam PADG 23 Tahun 2025?") == "rag"


def test_questions_covered_by_the_facts_table_go_to_agent(monkeypatch):
    monkeypatch.setattr(router, "entity_groups", lambda q: [])
    monkeypatch.setattr(router.facts, "sheet", lambda q: {"hits": {}})
    assert router.route("Bagaimana tren NPL BRI dari 2021-2025?") == "agent"
    # regulation questions never take the sheet path
    monkeypatch.setattr(router.regulation, "applies", lambda q: False)
    assert router.route("Apakah KPMM BTN 2025 di atas batas POJK 11/POJK.03/2016?") == "rag"


def test_single_figure_in_the_table_goes_to_facts(monkeypatch):
    monkeypatch.setattr(router, "entity_groups", lambda q: [])
    monkeypatch.setattr(router.facts, "sheet", lambda q: None)
    monkeypatch.setattr(router.facts, "answer_step", lambda q: {"answer": "x"})
    assert router.route("Berapa laba bersih konsolidasian BRI tahun 2025?") == "facts"
    assert router.route("Berapa KPMM minimum menurut POJK 11/POJK.03/2016?") == "rag"


def test_regulation_threshold_with_a_bank_figure_goes_to_regulation(monkeypatch):
    monkeypatch.setattr(router.regulation, "applies", lambda q: True)
    assert router.route("Berapa selisih KPMM BRI 2025 terhadap batas POJK 11/POJK.03/2016?") == "regulation"
    monkeypatch.setattr(router.regulation, "applies", lambda q: False)
    assert router.route("Berapa KPMM minimum menurut POJK 11/POJK.03/2016?") == "rag"
