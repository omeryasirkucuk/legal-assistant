from legal_api.agent.write import clean


def test_bare_document_keys_become_markers():
    text = "The closest are E10 and E12 (case E. 2016/8646); [[E3]] stays; E99 is unknown."
    assert clean(text, {"E3", "E10", "E12"}) == (
        "The closest are [[E10]] and [[E12]] (case E. 2016/8646); [[E3]] stays; E99 is unknown.")


def test_invisible_characters_are_removed():
    assert clean("a\u200bb") == "ab"
