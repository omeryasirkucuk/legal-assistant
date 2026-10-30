import json
from pathlib import Path

from legal_api.chat.history_search import _terms, snippet

TEXT = json.loads((Path(__file__).parents[1] / "fixtures" / "tr" / "history_search.json")
                  .read_text(encoding="utf-8"))


def test_terms_are_folded_with_turkish_casing():
    assert _terms(TEXT["query_upper"]) == [TEXT["query_folded"]]


def test_snippet_marks_partial_words_and_drops_markup():
    out = snippet(TEXT["content"], _terms(TEXT["query_partial"]))
    assert out.startswith(TEXT["snippet_start"])
    assert "[[E1]]" not in out and "<short>" not in out
