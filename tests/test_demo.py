from telaah import demo, tools


def _fake_page(monkeypatch, pages):
    monkeypatch.setattr(tools, "read_page_text", lambda d, p: pages[(d, p)] if (d, p) in pages else (_ for _ in ()).throw(KeyError("x")))


def test_doc_label():
    assert demo.doc_label("bri_2025") == "BRI LT 2025"
    assert demo.doc_label("mandiri_2024") == "Bank Mandiri LT 2024"
    assert demo.doc_label("ojk_pojk_22_2023") == "POJK Nomor 22 Tahun 2023"
    assert demo.doc_label("ojk_pojk_22_2023__faq") == "POJK Nomor 22 Tahun 2023 (FAQ)"
    assert demo.doc_label("ojk_pedoman_ai_perbankan_2025") == "OJK Pedoman AI Perbankan 2025"


def test_display_answer_citations_and_refusal():
    r = {"answer": "Total aset Rp2.135.371.105 juta [bri_2025 p.26].", "refused": False}
    assert demo.display_answer(r) == "Total aset Rp2.135.371.105 juta **[BRI LT 2025, hlm. 26]**."
    both = demo.display_answer({"answer": "NPL 3,29% dan 3,1% [bri_2025 p.3, btn_2025 p.9]", "refused": False})
    assert "[BRI LT 2025, hlm. 3]" in both and "[BTN LT 2025, hlm. 9]" in both
    ref = demo.display_answer({"answer": "TIDAK DITEMUKAN. Dokumen yang tersedia tidak memuat data Danamon.", "refused": True})
    assert ref.startswith("### Tidak ditemukan dalam dokumen") and "TIDAK DITEMUKAN" not in ref and "Danamon" in ref
    why = demo.display_answer({"answer": "TIDAK DITEMUKAN. Lihat tabel di [bri_2025 p.331].", "refused": True})
    assert "[BRI LT 2025, hlm. 331]" in why and "p.331" not in why


def test_trust_line(monkeypatch):
    _fake_page(monkeypatch, {("bri_2025", 26): "Total Aset 2.135.371.105"})
    assert demo.trust_line({"answer": "Rp2.135.371.105 juta [bri_2025 p.26]."}).startswith("✓")
    bad = demo.trust_line({"answer": "Rp9.999.999 juta [bri_2025 p.26]."})
    assert bad.startswith("⚠") and "9.999.999" in bad
    assert demo.trust_line({"answer": "Asetnya besar."}).startswith("⚠ Jawaban tanpa sitasi")
    assert demo.trust_line({"answer": "TIDAK DITEMUKAN", "refused": True}) == ""
    # agent: its verifier's verdict, which allows calculator results such as a difference
    agent = {"answer": "Selisih 548.542 miliar [bri_2025 p.26].", "route": "agent", "verified": True, "unsupported": [],
             "context": "Hasil hitung (kalkulator):\nselisih 548.542"}
    assert demo.trust_line(agent).startswith("✓") and "kalkulator" in demo.trust_line(agent)


def test_source_choices():
    r = {"answer": "x [bri_2025 p.26]. y [bri_2025 p.26] z [bri_2025 p.28]", "refused": False, "retrieved": [("a", 1)]}
    assert demo.source_choices(r) == [("BRI LT 2025, hlm. 26", "bri_2025|26"), ("BRI LT 2025, hlm. 28", "bri_2025|28")]
    refused = {"answer": "TIDAK DITEMUKAN", "refused": True, "retrieved": [("btn_2025", 5), ("btn_2025", 5), ("btn_2025", 7)]}
    assert [v for _, v in demo.source_choices(refused)] == ["btn_2025|5", "btn_2025|7"]


def test_bold_figures_only_answer_figures():
    page = "Tahun 2025 total aset 2.135.371.105 dan ekuitas 400.000; NPL 3,29%"
    out = demo.bold_figures(page, "Total aset Rp2.135.371.105 juta, NPL 3,29% [bri_2025 p.26] pada 2025.")
    assert "**2.135.371.105**" in out and "**3,29**" in out and "**2025**" not in out and "**400.000**" not in out


def test_page_view(monkeypatch):
    _fake_page(monkeypatch, {("bri_2025", 26): "aset 2.135.371.105"})
    view = demo.page_view("bri_2025|26", "aset Rp2.135.371.105 juta [bri_2025 p.26]")
    assert view.startswith("#### BRI LT 2025, hlm. 26") and "**2.135.371.105**" in view
    assert "tidak tersedia" in demo.page_view("bri_2025|99", "")
    assert demo.page_view(None, "") == ""


def test_how_md_agent_and_second_look():
    r = {"route": "agent", "steps": [{"q": "Berapa NPL BRI 2025?", "status": "ok", "answer": "3,29% [bri_2025 p.3]"}],
         "calc_result": {"expression": "3.29 - 3.1", "value": 0.19, "unit": "poin persentase"}}
    md = demo.how_md(r, 12.3)
    assert "agen" in md and "BRI LT 2025, hlm. 3" in md and "`3.29 - 3.1`" in md and "12.3 detik" in md
    assert "peringkat 6–10" in demo.how_md({"route": "rag", "look": 2, "retrieved": []}, 1.0)
    assert "grafik" in demo.how_md({"route": "rag"}, 1.0, chart_note=True)


def test_check_limit():
    assert demo.check_limit([], now=100) is None
    assert "Tunggu" in demo.check_limit([95.0], now=100)
    assert demo.check_limit([80.0], now=100) is None
    assert "Batas" in demo.check_limit([1.0] * demo.SESSION_MAX, now=1000)
