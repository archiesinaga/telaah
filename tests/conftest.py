"""Tests marked `requires_corpus` read the locally built corpus (data/processed, data/facts.sqlite).
Both are git-ignored; a fresh clone skips these tests until the corpus is built (see corpus/README.md)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _corpus_built() -> bool:
    processed = ROOT / "data" / "processed"
    return (ROOT / "data" / "facts.sqlite").exists() and processed.is_dir() and any(processed.iterdir())


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_corpus: needs the locally built corpus (data/processed, data/facts.sqlite)")


def pytest_collection_modifyitems(config, items):
    if _corpus_built():
        return
    skip = pytest.mark.skip(reason="corpus not built (see corpus/README.md)")
    for item in items:
        if "requires_corpus" in item.keywords:
            item.add_marker(skip)
