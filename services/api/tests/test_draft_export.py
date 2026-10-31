import io

from docx import Document

from legal_api.drafting.adjust import markers
from legal_api.drafting.export import to_docx


def test_docx_has_no_markers_and_bold_headings():
    text = "ANKARA ASLİYE HUKUK MAHKEMESİNE\n\n**DAVACI:** [Ad]\nKira ödenmedi [[E1]] [[E2]].\n"
    doc = Document(io.BytesIO(to_docx(text)))
    lines = [p.text for p in doc.paragraphs]
    assert lines == ["ANKARA ASLİYE HUKUK MAHKEMESİNE", "DAVACI: [Ad]", "Kira ödenmedi."]
    assert doc.paragraphs[0].runs[0].bold


def test_markers_are_read():
    assert markers("a [[E1]] b [[E12]] [[E1]]") == {"[[E1]]", "[[E12]]"}


def test_a_request_line_above_the_court_is_set_right_and_the_court_centred():
    from legal_api.drafting.export import blocks
    text = ("Not.\n---\n**İHTİYATİ TEDBİR TALEPLİDİR**\n\n[İL] AİLE MAHKEMESİ SAYIN HÂKİMLİĞİNE\n\n"
            "DAVACI: A\n\nAÇIKLAMALAR\n\n1-) Olay.\n---\nListe")
    aligns = [(b.text, b.align) for b in blocks(text)]
    assert aligns[0] == ("İHTİYATİ TEDBİR TALEPLİDİR", "right")
    assert aligns[1][1] == "centre" and aligns[-2] == ("AÇIKLAMALAR", "justify")
