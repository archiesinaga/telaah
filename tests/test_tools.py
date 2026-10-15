import pytest

from telaah import tools


def test_calculate():
    assert tools.calculate("(120.5 - 98.2) / 98.2 * 100") == pytest.approx(22.708, abs=1e-3)
    assert tools.calculate("-2 ** 2") == -4


@pytest.mark.parametrize("expr", ["__import__('os')", "1 + a", "2 ** 1000", "(1).real", "True + 1"])
def test_calculate_rejects(expr):
    with pytest.raises((ValueError, SyntaxError)):
        tools.calculate(expr)


def test_number_variants():
    assert "1234.5" in tools.number_variants("1.234,5")
    assert "1234.5" in tools.number_variants("1,234.5")
    assert "5.8" in tools.number_variants("5,80")


def test_check_citation_and_pages():
    doc = tools.list_documents()[0]
    page = next(iter(tools._pages(doc)))
    nums = sorted(tools.numbers_in(tools.read_page_text(doc, page)))
    assert tools.check_citation(doc, page, f"nilainya {nums[0]}")["supported"] if nums else True
    bad = tools.check_citation(doc, page, "angka 987654321,123")
    assert not bad["supported"] and bad["missing_numbers"] == ["987654321,123"]
    assert not tools.check_citation(doc, 99999, "x")["page_found"]
    assert not tools.check_citation("nope", 1, "x")["page_found"]
    with pytest.raises(KeyError):
        tools.read_page_text("nope", 1)
