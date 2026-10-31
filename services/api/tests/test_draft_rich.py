import io
import types

from docx import Document

from legal_api.drafting.export import render
from legal_api.drafting.locate import locate
from legal_api.drafting.rich import (
    apply_doc,
    carry_over,
    editor_doc,
    file_blocks,
    fingerprint,
    from_doc,
    text_of,
)

DRAFT = ("A note.\n---\nCENTRAL CIVIL COURT\n\nPlaintiff: **A**\n\n"
         "The rent was overdue [[E1]] and notice was served.\n---\nChecklist")


def _draft(text, meta=None):
    return types.SimpleNamespace(text=text, meta=meta or {})


def test_the_editor_gets_the_petition_with_citations_as_their_own_nodes():
    doc = editor_doc(_draft(DRAFT))
    first, _, third = doc["content"]
    assert first["attrs"]["textAlign"] == "center"
    assert {"type": "citation", "attrs": {"key": "E1"}} in third["content"]
    assert text_of(from_doc(doc)) == ("**CENTRAL CIVIL COURT**\n\nPlaintiff: **A**\n\n"
                                      "The rent was overdue [[E1]] and notice was served.")


def test_saving_the_document_keeps_the_note_and_checklist_and_the_formatting_reaches_word():
    doc = editor_doc(_draft(DRAFT))
    para = doc["content"][2]
    para["attrs"]["textAlign"] = "right"
    para["content"][0]["marks"] = [{"type": "italic"}, {"type": "textStyle", "attrs": {"fontSize": "14pt"}}]
    text = apply_doc(DRAFT, doc)
    assert text.startswith("A note.\n---\n") and text.endswith("\n---\nChecklist")
    saved = _draft(text, {"doc": doc, "doc_for": fingerprint(text)})
    word = Document(io.BytesIO(render(file_blocks(saved), "docx")))
    p = word.paragraphs[2]
    assert p.alignment == 2 and p.runs[0].italic and p.runs[0].font.size.pt == 14
    assert "[[E1]]" not in p.text and "E1" not in p.text


def test_a_text_change_makes_the_document_again():
    doc = editor_doc(_draft(DRAFT))
    doc["content"][0]["attrs"]["textAlign"] = "right"
    stale = _draft(DRAFT.replace("rent", "fee"), {"doc": doc, "doc_for": fingerprint(DRAFT)})
    assert editor_doc(stale)["content"][0]["attrs"]["textAlign"] == "center"


def test_lists_become_numbered_paragraphs():
    doc = {"type": "doc", "content": [{"type": "orderedList", "attrs": {"start": 1}, "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "one"}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "two"}]}]}]}]}
    assert [b.text for b in from_doc(doc)] == ["1. one", "2. two"]


def test_a_selection_is_found_without_bold_marks_and_with_other_line_breaks():
    text = "Intro.\n\nPLAINTIFF: **A**\nlives here.\n\nEnd."
    start, end = locate(text, "PLAINTIFF: A lives here.")
    assert text[start:end] == "PLAINTIFF: **A**\nlives here."
    assert locate(text, "not there") is None


def test_files_carry_the_petition_title():
    from docx import Document as Word
    pdf = render("Body.", "pdf", "Divorce petition")
    assert b"Divorce petition" in pdf and b"anonymous" not in pdf
    word = Word(io.BytesIO(render("Body.", "docx", "Divorce petition")))
    assert word.core_properties.title == "Divorce petition"


def test_a_rewrite_keeps_the_formatting_of_what_it_did_not_change():
    doc = editor_doc(_draft(DRAFT))
    doc["content"][1]["content"][0]["marks"] = [{"type": "italic"}]       # "Plaintiff: "
    doc["content"][2]["attrs"]["textAlign"] = "right"
    rewritten = DRAFT.replace("The rent was overdue", "Rent was late")
    new = carry_over(doc, rewritten)
    assert new["content"][1] is doc["content"][1]                          # untouched: kept whole
    assert new["content"][2]["attrs"]["textAlign"] == "right"              # rewritten: same place
    assert "Rent was late" in text_of(from_doc(new))
