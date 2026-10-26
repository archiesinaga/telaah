from telaah import agent, answer, tools

PAGES = {("bca_2025", p): f"halaman {p}" for p in range(1, 21)}


def _setup(monkeypatch):
    monkeypatch.setattr(tools, "read_page_text", lambda d, p: PAGES[(d, p)])
    asked = []

    def fake_retrieve(q, k):
        asked.append((q, k))
        start = 1 if q == "step" else 4  # "step" ranks 1-5, the original question ranks 4-8: pages 4, 5 overlap
        return [{"doc_id": "bca_2025", "page": p, "text": PAGES[("bca_2025", p)]} for p in range(start, start + k)]

    monkeypatch.setattr(answer, "SECOND_LOOK", False)
    monkeypatch.setattr(answer, "entity_groups", lambda q: [])
    monkeypatch.setattr(answer, "retrieve", fake_retrieve)
    monkeypatch.setattr(answer, "add_page_images", lambda q, chunks: (chunks, []))
    monkeypatch.setattr(answer, "_chat", lambda llm, s, u: "Kurs 16.095 [bca_2025 p.7].")
    return asked


def test_pool_with_adds_sibling_pages_after_own(monkeypatch):
    asked = _setup(monkeypatch)
    r = answer.ask("step", pool_with="original")
    assert asked == [("step", 5), ("original", 5)]
    assert r["retrieved"] == [("bca_2025", p) for p in (1, 2, 3, 4, 5, 6, 7, 8)]  # own top 5 first, no duplicates


def test_pool_with_same_question_or_none_is_a_no_op(monkeypatch):
    asked = _setup(monkeypatch)
    assert len(answer.ask("step", pool_with="step")["retrieved"]) == 5
    assert len(answer.ask("step")["retrieved"]) == 5
    assert asked == [("step", 5), ("step", 5)]


def test_agent_passes_original_question_only_when_on(monkeypatch):
    seen = []
    monkeypatch.setattr(agent, "ask", lambda q, k=None, **kw: seen.append(kw) or
                        {"answer": "TIDAK DITEMUKAN", "citations": [], "retrieved": [], "context": "", "refused": True})
    monkeypatch.setattr(agent, "USE_FACTS", False)
    state = {"question": "orig", "steps": [{"q": "a", "status": "pending", "attempts": 0},
                                           {"q": "b", "status": "pending", "attempts": 0}], "trace": []}
    monkeypatch.setattr(agent, "STEP_POOL", False)
    agent.execute(state)
    monkeypatch.setattr(agent, "STEP_POOL", True)
    agent.execute(state)  # first try: own pages only
    retried = [{**s, "attempts": 1} for s in state["steps"]]
    agent.execute({**state, "steps": retried})  # retry: original question's pages added
    agent.execute({**state, "steps": retried[:1]})  # single step: nothing to share
    assert seen == [{}, {}, {}, {}, {"pool_with": "orig"}, {"pool_with": "orig"}, {}]


def test_answer_entity_adds_later_report_pages_after_own(monkeypatch):
    monkeypatch.setattr(answer, "retrieve_entity", lambda q, docs, n=5: [{"doc_id": d, "page": p, "text": "x"}
                                                                        for d in docs for p in (1, 2)])
    monkeypatch.setattr(answer, "add_page_images", lambda q, chunks: (chunks, []))
    monkeypatch.setattr(answer, "_chat", lambda llm, s, u: "ok")
    _, chunks, _, _ = answer.answer_entity(None, "giro 2024?", ["bri_2024"], later=["bri_2025"])
    assert [(c["doc_id"], c["page"]) for c in chunks] == [("bri_2024", 1), ("bri_2024", 2), ("bri_2025", 1), ("bri_2025", 2)]
    _, chunks, _, _ = answer.answer_entity(None, "giro 2024?", ["bri_2024"])
    assert len(chunks) == 2


def test_year_split():
    assert agent.year_split([["bri_2024"], ["bri_2025"]])
    assert not agent.year_split([["bri_2024"], ["bni_2024"]])
    assert not agent.year_split([["ojk_pojk_12_2024"], ["ojk_pojk_22_2023"]])
    assert not agent.year_split([["bri_2024", "bri_2025"], ["bni_2024"]])


def test_plan_sets_later_reports_only_when_on(monkeypatch):
    monkeypatch.setattr(agent, "USE_FACTS", False)
    monkeypatch.setattr(agent, "entity_groups", lambda q: [["bri_2024"], ["bri_2025"]])
    monkeypatch.setattr(agent, "split_question", lambda llm, q, groups: ["giro 2024?", "giro 2025?"])
    monkeypatch.setattr(agent, "_llm", lambda: None)
    state = {"question": "selisih giro BRI 2024 dan 2025?", "trace": []}
    monkeypatch.setattr(agent, "YEAR_UNION", False)
    assert all("later" not in s for s in agent.plan(state)["steps"])
    monkeypatch.setattr(agent, "YEAR_UNION", True)
    assert [s.get("later") for s in agent.plan(state)["steps"]] == [["bri_2025"], []]


def test_plan_entity_path_uses_calculator_for_growth(monkeypatch):
    monkeypatch.setattr(agent, "USE_FACTS", False)
    monkeypatch.setattr(agent, "entity_groups", lambda q: [["bri_2024"], ["bri_2025"]])
    monkeypatch.setattr(agent, "split_question", lambda llm, q, groups: ["giro 2024?", "giro 2025?"])
    monkeypatch.setattr(agent, "_llm", lambda: None)
    assert agent.plan({"question": "Berapa pertumbuhan giro BRI 2024 ke 2025?", "trace": []})["calc"]
    assert not agent.plan({"question": "Berapa giro BRI 2024 dan 2025?", "trace": []})["calc"]
