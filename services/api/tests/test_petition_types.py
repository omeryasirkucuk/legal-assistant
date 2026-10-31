import json
from pathlib import Path

from legal_api.drafting.types import petition_types

TR = json.loads((Path(__file__).parent / "fixtures" / "tr" / "test_strings.json").read_text(encoding="utf-8"))


def test_petition_types_load_with_their_articles():
    types = petition_types()
    assert {"dava", "cevap", "istinaf", "icra-itiraz", "ihtarname"} <= set(types)
    assert ("6100", "119") in types["dava"].articles
    assert ("6325", "18/b") in types["dava"].articles
    assert TR["petition_types_1"] not in types["dava"].name and types["dava"].outline


def test_practice_notes_are_loaded_and_not_types():
    types = petition_types()
    assert not any(t.endswith(".practice") for t in types)
    assert types["dava"].practice
