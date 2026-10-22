from telaah import twoyear


def test_detector(monkeypatch):
    monkeypatch.setattr(twoyear, "detect_groups", lambda q: [["bni_2024"]])
    monkeypatch.setattr(twoyear.facts, "sheet", lambda q, partial=False: None)
    g = twoyear.applies("Berapa pertumbuhan beban penyusutan BNI dari tahun 2023 ke 2024?")
    assert g == {"op": "growth_pct", "old": "2023", "new": "2024"}
    d = twoyear.applies("Berapa selisih beban penyusutan BNI antara tahun 2024 dan tahun 2023?")
    assert d == {"op": "difference", "old": "2023", "new": "2024"}
    assert twoyear.applies("Berapa pertumbuhan beban penyusutan BNI pada tahun 2024?") is None  # one year
    assert twoyear.applies("Berapa pertumbuhan dan selisih beban BNI 2023 ke 2024?") is None  # both words
    assert twoyear.applies("Menurut grafik BNI, berapa kenaikan laba dari 2023 ke 2024?") is None  # chart
    monkeypatch.setattr(twoyear.facts, "sheet", lambda q, partial=False: {"hits": {}})
    assert twoyear.applies("Berapa pertumbuhan total aset BNI dari 2023 ke 2024?") is None  # facts table handles it
    monkeypatch.setattr(twoyear.facts, "sheet", lambda q, partial=False: None)
    monkeypatch.setattr(twoyear, "detect_groups", lambda q: [["bni_2024"], ["bri_2024"]])
    assert twoyear.applies("Berapa pertumbuhan beban BNI dan BRI dari 2023 ke 2024?") is None  # two banks
    monkeypatch.setattr(twoyear, "detect_groups", lambda q: [["bni_2023"], ["bni_2024"]])
    assert twoyear.applies("Berapa pertumbuhan beban BNI dari 2023 ke 2024?") is not None  # one bank, two reports
    monkeypatch.setattr(twoyear, "detect_groups", lambda q: [["ojk_pojk_17_2023"]])
    assert twoyear.applies("Berapa pertumbuhan batas menurut POJK dari 2023 ke 2024?") is None  # not a bank report


def test_numbers_and_format():
    assert twoyear.to_float("2.304.524") == 2304524.0
    assert twoyear.to_float("2,304,524") == 2304524.0
    assert twoyear.to_float("4,87") == 4.87
    assert twoyear.to_float("abc") is None
    assert twoyear.compute("growth_pct", 2304524, 2416792) == "4,87%"
    assert twoyear.compute("difference", 2416792, 2304524) == "112.268"
    assert twoyear.compute("growth_pct", 0, 5) is None


def _setup(monkeypatch, reply, supported=True, retrieved=(("bni_2024", 1425),)):
    monkeypatch.setattr(twoyear, "applies", lambda q: {"op": "growth_pct", "old": "2023", "new": "2024"})
    monkeypatch.setattr(twoyear, "retrieve", lambda q: [{"doc_id": d, "page": p, "text": ""} for d, p in retrieved])
    monkeypatch.setattr(twoyear, "build_context", lambda c, q: "ctx")
    monkeypatch.setattr(twoyear, "OpenAI", lambda **k: None)
    monkeypatch.setattr(twoyear, "_chat", lambda llm, s, u: reply)
    monkeypatch.setattr(twoyear.tools, "check_citation", lambda d, p, c: {"supported": supported})


def test_answer_computes_in_python(monkeypatch):
    _setup(monkeypatch, '{"old": "2.304.524", "new": "2.416.792", "doc": "bni_2024", "page": 1425}')
    r = twoyear.answer("q")
    assert "4,87%" in r["answer"] and r["citations"] == [("bni_2024", 1425)] and not r["refused"]


def test_answer_falls_back_when_a_check_fails(monkeypatch):
    ok = '{"old": "2.304.524", "new": "2.416.792", "doc": "bni_2024", "page": 1425}'
    _setup(monkeypatch, '{"old": null, "new": "2.416.792", "doc": "bni_2024", "page": 1425}')
    assert twoyear.answer("q") is None  # a value missing
    _setup(monkeypatch, "tidak tahu")
    assert twoyear.answer("q") is None  # not JSON
    _setup(monkeypatch, ok, retrieved=(("bni_2024", 7),))
    assert twoyear.answer("q") is None  # cited page was not retrieved
    _setup(monkeypatch, ok, supported=False)
    assert twoyear.answer("q") is None  # numbers not on the cited page


def test_doc_label_with_page_is_accepted(monkeypatch):
    _setup(monkeypatch, '{"old": "2.304.524", "new": "2.416.792", "doc": "bni_2024 p.1425", "page": 1425}')
    assert twoyear.answer("q")["citations"] == [("bni_2024", 1425)]
