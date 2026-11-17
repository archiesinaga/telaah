"""Extra gold pages must stay on the question they were found for (2026-11-17: a dev rebuild shifted 307 ids)."""
import json

import pytest

from telaah.metrics import load_extra_gold, remap_extra_gold

QS = [{"id": "bd0001", "question": "Berapa NPL BRI 2024?"}, {"id": "bd0002", "question": "Berapa CAR BNI 2024?"}]


def write(tmp_path, data):
    p = tmp_path / "extra_gold_dev.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_missing_file_is_empty(tmp_path):
    assert load_extra_gold(tmp_path / "nope.json", QS) == {}


def test_matching_entries_load_as_tuples(tmp_path):
    p = write(tmp_path, {"bd0002": {"q": "Berapa CAR BNI 2024?", "pages": [["bni_2024", 12]]}})
    assert load_extra_gold(p, QS) == {"bd0002": [("bni_2024", 12)]}


def test_shifted_id_raises(tmp_path):
    # the entry was found for the NPL question, but after a rebuild that question is no longer bd0002
    p = write(tmp_path, {"bd0002": {"q": "Berapa NPL BRI 2024?", "pages": [["bri_2024", 5]]}})
    with pytest.raises(ValueError, match="--remap"):
        load_extra_gold(p, QS)


def test_old_id_only_format_raises(tmp_path):
    p = write(tmp_path, {"bd0001": [["bri_2024", 5]]})
    with pytest.raises(ValueError):
        load_extra_gold(p, QS)


def test_unknown_id_raises(tmp_path):
    p = write(tmp_path, {"bd0099": {"q": "Berapa NPL BRI 2024?", "pages": [["bri_2024", 5]]}})
    with pytest.raises(ValueError):
        load_extra_gold(p, QS)


def test_remap_rekeys_by_text_and_drops_gone_questions():
    raw = {"bd0002": {"q": "Berapa NPL BRI 2024?", "pages": [["bri_2024", 5]]},
           "bd0003": {"q": "Pertanyaan yang sudah dihapus", "pages": [["bca_2025", 1]]}}
    new, dropped = remap_extra_gold(raw, QS)
    assert new == {"bd0001": raw["bd0002"]} and dropped == ["bd0003"]
