from telaah import answer, tools
from telaah.filters import named_prefixes

PAGES = {("bri_2025", p): f"halaman {p}" for p in range(1, 16)}
PAGES[("bri_2025", 8)] = "Total aset Rp1.965.007 juta"
PAGES[("ojk_pojk_22_2023", 31)] = "denda paling banyak Rp15.000.000.000,00"


def _setup(monkeypatch, replies, on=True):
    monkeypatch.setattr(tools, "read_page_text", lambda d, p: PAGES[(d, p)] if (d, p) in PAGES else (_ for _ in ()).throw(KeyError("x")))
    pool = [{"doc_id": "bri_2025", "page": p, "text": PAGES[("bri_2025", p)]} for p in range(1, 16)]
    asked_k, calls = [], []
    monkeypatch.setattr(answer, "SECOND_LOOK", on)
    monkeypatch.setattr(answer, "entity_groups", lambda q: [])
    monkeypatch.setattr(answer, "retrieve", lambda q, k: asked_k.append(k) or pool[:k])
    monkeypatch.setattr(answer, "add_page_images", lambda q, chunks: (chunks, []))
    replies = iter(replies)
    monkeypatch.setattr(answer, "_chat", lambda llm, s, u: calls.append(u) or next(replies))
    return asked_k, calls


def test_named_prefixes():
    assert named_prefixes("Menurut POJK Nomor 12 Tahun 2024, berapa denda?") == ["ojk_pojk_12_2024"]
    assert named_prefixes("Berapa total aset BRI 2025?") == ["bri_"]
    assert named_prefixes("Apa yang dimaksud isi laporan nihil?") == []


def test_later_look_ok(monkeypatch):
    _setup(monkeypatch, [])
    q = "Berapa total aset BRI 2025?"
    assert answer.later_look_ok(q, "Total aset Rp1.965.007 juta [bri_2025 p.8].", [("bri_2025", 8)])[1]
    # wrong neighbouring page: moved to the look page that holds the number
    text, ok = answer.later_look_ok(q, "Total aset Rp1.965.007 juta [bri_2025 p.9].", [("bri_2025", 8)])
    assert ok and text.endswith("[bri_2025 p.8]")
    assert not answer.later_look_ok(q, "Total aset Rp9.999 juta [bri_2025 p.8].", [("bri_2025", 8)])[1]
    assert not answer.later_look_ok(q, "Total aset BRI besar.", [("bri_2025", 8)])[1]  # no citation
    # the 10-25 leak: figure is on the cited page, but the page belongs to another regulation
    leak = "Denda maksimum Rp15.000.000.000,00 [ojk_pojk_22_2023 p.31]."
    assert not answer.later_look_ok("Menurut POJK Nomor 12 Tahun 2024, berapa denda maksimum?", leak, [("ojk_pojk_22_2023", 31)])[1]


def test_off_asks_once(monkeypatch):
    asked_k, calls = _setup(monkeypatch, [answer.REFUSAL], on=False)
    r = answer.ask("Berapa total aset BRI 2025?")
    assert asked_k == [5] and len(calls) == 1 and r["refused"] and r["look"] == 1 and len(r["retrieved"]) == 5


def test_second_look_accepts_supported_answer(monkeypatch):
    asked_k, calls = _setup(monkeypatch, [answer.REFUSAL, "Total aset Rp1.965.007 juta [bri_2025 p.8]."])
    r = answer.ask("Berapa total aset BRI 2025?")
    assert asked_k == [15] and len(calls) == 2 and "[bri_2025 p.6]" in calls[1] and "[bri_2025 p.1]" not in calls[1]
    assert not r["refused"] and r["look"] == 2 and r["citations"] == [("bri_2025", 8)]
    assert r["retrieved"][:5] == [("bri_2025", p) for p in range(1, 6)] and len(r["retrieved"]) == 10
    assert "[bri_2025 p.8]" in r["context"]


def test_second_look_rejected_answer_keeps_refusal(monkeypatch):
    _, calls = _setup(monkeypatch, [answer.REFUSAL, "Total aset Rp9.999 juta [bri_2025 p.8].", "unused"])
    r = answer.ask("Berapa total aset BRI 2025?")
    assert len(calls) == 2 and r["refused"] and r["look"] == 1 and r["answer"] == answer.REFUSAL


def test_third_look_after_two_refusals(monkeypatch):
    _, calls = _setup(monkeypatch, [answer.REFUSAL, answer.REFUSAL, answer.REFUSAL])
    r = answer.ask("Berapa total aset BRI 2025?")
    assert len(calls) == 3 and r["refused"] and len(r["retrieved"]) == 15


def _cite_case(monkeypatch, flag, reply):
    monkeypatch.setitem(PAGES, ("bri_2025", 4), "Total aset Rp1.965.007 juta")  # inside the top 5
    _setup(monkeypatch, [reply], on=False)
    monkeypatch.setattr(answer, "CITE_REPAIR", flag)
    return answer.ask("Berapa total aset BRI 2025?")


def test_cite_repair_points_to_page_with_the_figure(monkeypatch):
    r = _cite_case(monkeypatch, True, "Total aset Rp1.965.007 juta [bri_2025 p.3].")  # p.3 lacks the figure
    assert r["citations"] == [("bri_2025", 4)] and r["answer"].endswith("[bri_2025 p.4]")
    assert r["retrieved"] == [("bri_2025", p) for p in range(1, 6)]  # retrieval untouched


def test_cite_repair_off_and_refusal_unchanged(monkeypatch):
    r = _cite_case(monkeypatch, False, "Total aset Rp1.965.007 juta [bri_2025 p.3].")
    assert r["citations"] == [("bri_2025", 3)]
    r = _cite_case(monkeypatch, True, answer.REFUSAL)
    assert r["refused"] and r["answer"] == answer.REFUSAL
    r = _cite_case(monkeypatch, True, "Total aset Rp9.999 juta [bri_2025 p.3].")  # figure on no page: left for the verifier
    assert r["citations"] == [("bri_2025", 3)]


def test_cite_repair_in_entity_answers(monkeypatch):
    monkeypatch.setitem(PAGES, ("bri_2025", 4), "Total aset Rp1.965.007 juta")
    _setup(monkeypatch, [], on=False)
    chunks = [{"doc_id": "bri_2025", "page": p, "text": PAGES[("bri_2025", p)]} for p in range(1, 6)]
    monkeypatch.setattr(answer, "split_question", lambda llm, q, g: ["a?", "b?"])
    monkeypatch.setattr(answer, "answer_entity", lambda llm, sub, g: ("jawaban", chunks, [], "ctx"))
    monkeypatch.setattr(answer, "_chat", lambda *a, **k: "Total aset Rp1.965.007 juta [bri_2025 p.3].")
    monkeypatch.setattr(answer, "CITE_REPAIR", True)
    assert answer.ask_entities("q", [["bri_2025"], ["bri_2025"]])["citations"] == [("bri_2025", 4)]
    monkeypatch.setattr(answer, "CITE_REPAIR", False)
    assert answer.ask_entities("q", [["bri_2025"], ["bri_2025"]])["citations"] == [("bri_2025", 3)]
