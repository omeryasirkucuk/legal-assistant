from pathlib import Path

from legal_api.corpus.statutes import split_articles

FIXTURES = Path(__file__).parent / "fixtures" / "tr"
LINES = (FIXTURES / "statute_footnotes.txt").read_text(encoding="utf-8").splitlines()


def test_a_closing_sentence_with_footnote_marks_stays_in_its_article():
    # The closing line of art. 86/3 (the increase for a weapon) ends with a footnote mark;
    # it was taken for art. 87's marginal title and cut from art. 86.
    articles = {a.label: a for a in split_articles(
        (FIXTURES / "statute_footnotes.txt").read_text(encoding="utf-8"))}
    assert articles["86"].text.endswith(LINES[7])            # the closing line, with [41]
    assert articles["87"].heading == LINES[8]
    assert articles["87"].text.endswith(LINES[11])           # ends with [44][45]
    assert articles["88"].heading == LINES[12]
    assert articles["86"].heading.endswith(LINES[1])


def test_a_bare_footnote_number_after_a_sentence_ends_it_too():
    articles = {a.label: a for a in split_articles(
        (FIXTURES / "statute_footnotes.txt").read_text(encoding="utf-8"))}
    assert articles["88"].text.endswith(LINES[14])          # ends with a bare 13
    assert articles["89"].heading == LINES[15]
