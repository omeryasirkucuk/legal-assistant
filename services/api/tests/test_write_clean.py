from legal_api.agent.write import clean


def test_raw_document_keys_cannot_create_citations():
    text = "The closest are E10 and E12 (case E. 2016/8646) [[E3]]."
    assert clean(text) == "The closest are E10 and E12 (case E. 2016/8646)."


def test_invisible_characters_are_removed():
    assert clean("a\u200bb") == "ab"
