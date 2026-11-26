"""Tests marked `requires_corpus` read the corpus (data/processed, data/facts.sqlite), both git-ignored.

When the real corpus is absent (a fresh clone) they run against `tests/fixtures/corpus/`: the facts table (104 KB)
and one public regulation (POJK 11/2016). Set TELAAH_TEST_FIXTURES=1 to use the fixtures even when the corpus exists."""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "corpus"


def _corpus_built() -> bool:
    processed = ROOT / "data" / "processed"
    return (ROOT / "data" / "facts.sqlite").exists() and processed.is_dir() and any(processed.iterdir())


def _use_fixtures() -> bool:
    return bool(os.getenv("TELAAH_TEST_FIXTURES")) or not _corpus_built()


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_corpus: reads the corpus; runs on tests/fixtures/corpus when it is not built")
    config.addinivalue_line("markers", "requires_full_corpus: needs the bank-report text, skipped on the fixtures")


def pytest_collection_modifyitems(config, items):
    if not _use_fixtures():
        return
    skip = pytest.mark.skip(reason="needs the full corpus (python scripts/fetch_data.py)")
    for item in items:
        if "requires_full_corpus" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _corpus_fixtures(request, monkeypatch):
    if "requires_corpus" not in request.keywords or not _use_fixtures():
        yield
        return
    from telaah import facts, filters, tools

    monkeypatch.setattr(facts, "DB_PATH", FIXTURES / "facts.sqlite")
    monkeypatch.setattr(facts, "PROCESSED_DIR", FIXTURES / "processed")
    monkeypatch.setattr(tools, "PROCESSED_DIR", FIXTURES / "processed")
    monkeypatch.setattr(filters, "PROCESSED_DIR", FIXTURES / "processed")
    filters.doc_ids.cache_clear()
    tools._pages.cache_clear()
    yield
    monkeypatch.undo()
    filters.doc_ids.cache_clear()
    tools._pages.cache_clear()
