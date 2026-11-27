import json
from types import SimpleNamespace

import pytest

from telaah import pairread, stepcalc, tools

PAGE = """Catatan 12. Beban penyusutan
2024 2023
Beban penyusutan 2.529.060 2.416.792
Beban amortisasi 310.115 298.004"""
Q = "Berapakah selisih beban penyusutan PT Bank Negara Indonesia (Persero) Tbk antara tahun 2024 dan tahun 2023?"


def step(q, a, cites):
    return {"q": q, "answer": a, "citations": cites, "status": "ok", "context": "ctx"}


class FakeLLM:
    """Answers the pair-read prompt with a fixed JSON; counts calls."""
    def __init__(self, reply):
        self.reply, self.calls = reply, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.reply)))])


@pytest.fixture
def page(monkeypatch):
    pages = {("bni_2024", 1425): PAGE, ("bni_2024", 1516): "Pendapatan lain 40.669.669"}

    def fake(doc, p):
        if (doc, p) not in pages:
            raise KeyError(doc)
        return pages[(doc, p)]
    monkeypatch.setattr(tools, "read_page_text", fake)


def same_column():
    return [step("Berapa beban penyusutan BNI pada tahun 2023?", "Beban penyusutan BNI tahun 2023 adalah 2,416,792 juta Rupiah [bni_2024 p.1425].", [("bni_2024", 1425)]),
            step("Berapa beban penyusutan BNI pada tahun 2024?", "Beban penyusutan BNI tahun 2024 adalah 2,416,792 juta Rupiah [bni_2024 p.1425].", [("bni_2024", 1425)])]


def test_candidates():
    assert pairread.candidates(Q, same_column()) == [("bni_2024", 1425)]  # one column read twice
    fine = same_column()
    fine[1] = {**fine[1], "answer": "Beban penyusutan BNI tahun 2024 adalah 2.529.060 juta Rupiah [bni_2024 p.1425]."}
    assert pairread.candidates(Q, fine) is None  # one page, two different figures: the steps look right
    split = same_column()
    split[0] = {**split[0], "citations": [("bni_2024", 1516)]}
    assert pairread.candidates(Q, split) == [("bni_2024", 1425), ("bni_2024", 1516)]  # newer-year page first
    nocite = same_column()
    nocite[0] = {**nocite[0], "citations": []}
    assert pairread.candidates(Q, nocite) == [("bni_2024", 1425)]
    assert pairread.candidates("Berapa rasio beban BNI 2023 dan 2024?", same_column()) is None  # not growth/difference


def test_fix_reads_both_years_from_one_page(page):
    llm = FakeLLM({"2023": "2.416.792", "2024": "2.529.060"})
    fixed = pairread.fix(llm, Q, same_column())
    assert llm.calls == 1 and all(s["citations"] == [("bni_2024", 1425)] for s in fixed)
    line = stepcalc.answer(Q, fixed)[0]
    assert "112.268 juta Rupiah" in line and "naik" in line  # dev bd0227 gold 112.268


def test_fix_refuses_untrusted_reads(page):
    assert pairread.fix(FakeLLM({"2023": "2.416.792", "2024": "9.999.999"}), Q, same_column()) is None  # not on the page
    assert pairread.fix(FakeLLM({"2023": "310.115", "2024": "298.004"}), Q, same_column()) is None  # other row: no step match
    assert pairread.fix(FakeLLM({"2023": "2.416.792", "2024": None}), Q, same_column()) is None
    llm = FakeLLM({"2023": "2.416.792", "2024": "2.529.060"})
    fine = same_column()
    fine[1] = {**fine[1], "answer": "Beban penyusutan BNI tahun 2024 adalah 2.529.060 juta Rupiah [bni_2024 p.1425]."}
    assert pairread.fix(llm, Q, fine) is None and llm.calls == 0  # nothing suspicious: no LLM call
