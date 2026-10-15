from telaah import answer


def _page(row_at: int) -> str:
    head = "| Uraian | 2025 | 2024 | 2023 | 2022 | 2021 |\n"
    filler = "".join(f"| Baris {i} | 1 | 2 | 3 | 4 | 5 |\n" for i in range(row_at))
    return head + filler + "| Total Aset | 2.829.948.026 | 2.427.223.262 | 2.174.219.449 | 1.992.544.687 | 1.725.611.128 |\n" \
        + "".join(f"| Lain {i} | 9 | 9 | 9 | 9 | 9 |\n" for i in range(200))


def test_excerpt_keeps_head_when_row_is_inside_cap():
    text = _page(5)
    assert answer.excerpt(text, "Berapa total aset Bank Mandiri?", 3000) == text[:3000]


def test_excerpt_reaches_a_row_beyond_the_cap():
    text = _page(150)
    assert "2.829.948.026" not in text[:3000]
    out = answer.excerpt(text, "Berapa total aset Bank Mandiri?", 3000)
    assert "2.829.948.026" in out and len(out) <= 3100
    assert "| Uraian | 2025 | 2024 |" in out  # the year header stays with the window


def test_excerpt_without_question_is_plain_head():
    text = _page(150)
    assert answer.excerpt(text, "", 3000) == text[:3000]


def test_refine_step_adds_consolidated_and_source():
    out = answer.refine_step("Berapa total aset BRI pada akhir 2024?",
                             "Hitung pertumbuhan aset BRI. Gunakan data dari Laporan Tahunan 2025 masing-masing bank.")
    assert "konsolidasian" in out and "Laporan Tahunan 2025" in out
    # nothing to add: a step about a regulation, no source note in the question
    assert answer.refine_step("Berapa KPMM Insentif PADG 23 Tahun 2025?", "Berapa selisih?") == "Berapa KPMM Insentif PADG 23 Tahun 2025?"


def test_alias_expansion_only_for_abbreviations():
    from telaah import retrieve

    assert "non performing loan" in retrieve.expand_aliases("Berapa NPL gross BTN 2021?")
    assert retrieve.expand_aliases("Berapa total aset BRI?") == "Berapa total aset BRI?"


def test_throttle_spaces_llm_calls(monkeypatch):
    clock = {"t": 100.0, "slept": []}
    monkeypatch.setattr(answer, "LLM_MIN_INTERVAL", 4.5)
    monkeypatch.setattr(answer, "_last_call", 0.0)
    monkeypatch.setattr(answer.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(answer.time, "sleep", lambda s: (clock["slept"].append(s), clock.__setitem__("t", clock["t"] + s)))
    answer.throttle()  # first call: no wait
    clock["t"] += 1.0
    answer.throttle()  # 1 s later: waits the remaining 3.5 s
    assert clock["slept"] == [3.5]
