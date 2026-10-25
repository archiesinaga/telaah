import json

from telaah import agent, tools


def _fake_page(monkeypatch, pages):
    monkeypatch.setattr(tools, "read_page_text", lambda d, p: pages[(d, p)] if (d, p) in pages else (_ for _ in ()).throw(KeyError("x")))


def test_check_text_flags_unsupported_number(monkeypatch):
    _fake_page(monkeypatch, {("a_2024", 3): "NPL gross 3,12% pada 2024"})
    assert agent.check_text("NPL 3,12% [a_2024 p.3]") == []
    bad = agent.check_text("NPL 9,99% [a_2024 p.3]")
    assert bad and bad[0]["missing"] == ["9,99"]
    missing_page = agent.check_text("NPL 2,0% [a_2024 p.99]")
    assert missing_page and missing_page[0]["reason"] == "'x'"  # page not found -> unsupported


def test_check_text_allows_calculator_result(monkeypatch):
    _fake_page(monkeypatch, {("a_2024", 3): "NPL 3,12%"})
    allowed = agent._allowed({"value": 1.12})
    assert agent.check_text("Selisih 1,12% [a_2024 p.3] vs 3,12%.", allowed) == []
    assert agent.check_text("Selisih 1,12% [a_2024 p.3]") != []


def test_repair_text_moves_citation_to_page_with_the_number(monkeypatch):
    _fake_page(monkeypatch, {("a_2025", 342): "lain", ("a_2025", 31): "NPL gross 3,29%"})
    fixed = agent.repair_text("NPL 3,29% [a_2025 p.342]", [("a_2025", 31)])
    assert fixed.endswith("[a_2025 p.31]") and "p.342" not in fixed
    assert agent.repair_text("NPL 8,8% [a_2025 p.342]", [("a_2025", 31)]).endswith("[a_2025 p.342]")


def test_split_cites_and_plain_numbers():
    assert agent.split_cites("x [a_1 p.3, b_2 p.4]") == "x [a_1 p.3] [b_2 p.4]"
    assert agent.split_cites("x [a_1 p.3] [b_2 p.4]") == "x [a_1 p.3] [b_2 p.4]"
    assert agent.plain_numbers("laba Rp61.346.133 juta, NPL 3,29% [a_1 p.3]") == "laba Rp61346133 juta, NPL 3.29% "
    assert agent.plain_numbers("CAR 29,8 dan 19.36") == "CAR 29.8 dan 19.36"


def test_check_text_number_may_come_from_any_cited_page(monkeypatch):
    _fake_page(monkeypatch, {("a_1", 1): "NPL 3,29%", ("b_1", 2): "NPL 3,17%"})
    assert agent.check_text("A 3,29% dan B 3,17% [a_1 p.1] [b_1 p.2]") == []
    assert agent.check_text("A 3,29% dan B 9,99% [a_1 p.1] [b_1 p.2]")[0]["missing"] == ["9,99"]


def _run(monkeypatch, answers, replies):
    """answers: step question -> list of ask() results per attempt; replies: LLM replies in order."""
    calls = {}

    def fake_ask(q, k=None):
        n = calls.get(q, 0)
        calls[q] = n + 1
        text = answers[q][min(n, len(answers[q]) - 1)]
        return {"answer": text, "citations": [], "retrieved": [], "context": "", "refused": "TIDAK DITEMUKAN" in text}

    replies = iter(replies)
    monkeypatch.setattr(agent, "ask", fake_ask)
    monkeypatch.setattr(agent, "_chat", lambda *a, **k: next(replies))
    monkeypatch.setattr(agent, "TRACE_DIR", agent.TRACE_DIR / "_test")
    return calls


def test_graph_retries_then_composes(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "TRACE_DIR", tmp_path)
    _fake_page(monkeypatch, {("a_2024", 3): "NPL 3,12%", ("b_2024", 4): "NPL 2,0%"})
    calls = _run(
        monkeypatch,
        {"qa": ["NPL 7,7% [a_2024 p.3]", "NPL 3,12% [a_2024 p.3]"], "qb": ["NPL 2,0% [b_2024 p.4]"]},
        [json.dumps({"steps": ["qa", "qb"], "calc": True}), json.dumps({"expression": "3.12 - 2.0", "unit": "%"}),
         "Selisih 1,12% [a_2024 p.3] [b_2024 p.4]"],
    )
    monkeypatch.setattr(agent, "TRACE_DIR", tmp_path)
    out = agent.run_agent("selisih?")
    assert calls == {"qa": 2, "qb": 1}  # failed step retried once, passing step not re-run
    assert out["verified"] and out["calc_result"]["value"] == 1.12


def test_graph_refuses_when_nothing_verified(monkeypatch, tmp_path):
    _fake_page(monkeypatch, {})
    _run(monkeypatch, {"q": ["TIDAK DITEMUKAN"]}, [json.dumps({"steps": ["q"], "calc": False})])
    monkeypatch.setattr(agent, "TRACE_DIR", tmp_path)
    out = agent.run_agent("q")
    assert out["refused"] and not out["verified"]


def test_claim_keeps_only_figures():
    claim = agent._claim("Per 31 Desember 2025, pasal 5 ayat 2: NPL 3,29%, laba Rp57.132.365 juta, 50 persen [a_1 p.3]", set())
    assert claim.split() == ["3,29", "57.132.365", "50"]
    assert agent._claim("selisih 1,12% dan NPL 3,29%", {"1.12"}) == "3,29"


def test_fmt_id():
    assert agent.fmt_id(1849958023.5) == "1.849.958.023,5"
    assert agent.fmt_id(10.44) == "10,44"
    assert agent.fmt_id(406151) == "406.151"


def test_repair_split_swaps_the_dead_citation(monkeypatch):
    pages = {("bank_2025", 9): "RIM 84,52%", ("reg_2025", 4): "ketentuan umum", ("reg_2025", 7): "batas bawah 84% dan batas atas 94%"}
    _fake_page(monkeypatch, pages)
    cand = [("bank_2025", 9), ("reg_2025", 4), ("reg_2025", 7)]
    text = "RIM 84,52%, di atas batas bawah 84% dan di bawah batas atas 94% [bank_2025 p.9] [reg_2025 p.4]."
    assert agent.repair_split(text, cand).endswith("[bank_2025 p.9] [reg_2025 p.7].")
    # every figure already covered, or no candidate page of that document holds the figures: unchanged
    assert agent.repair_split("RIM 84,52% [bank_2025 p.9] [reg_2025 p.4].", cand) == "RIM 84,52% [bank_2025 p.9] [reg_2025 p.4]."
    assert agent.repair_split(text, cand[:2]) == text
    assert agent.repair_split("RIM 84,52% [bank_2025 p.9].", cand) == "RIM 84,52% [bank_2025 p.9]."
