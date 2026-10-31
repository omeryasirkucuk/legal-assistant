import io

import pytest
from docx import Document

from legal_api.files.extract import UnsupportedFile, text_of


def test_docx_and_text_are_read():
    doc = Document()
    doc.add_paragraph("DAVACI : X")
    doc.add_paragraph("SONUÇ VE İSTEM : kabulü")
    buf = io.BytesIO()
    doc.save(buf)
    assert text_of("a.DOCX", buf.getvalue()) == "DAVACI : X\nSONUÇ VE İSTEM : kabulü"
    assert text_of("a.txt", b"metin") == "metin"


def test_other_types_are_rejected():
    with pytest.raises(UnsupportedFile):
        text_of("a.exe", b"x")
