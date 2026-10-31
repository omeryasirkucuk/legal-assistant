from pathlib import Path

import pytest

from legal_api.files.labels import file_format, labels

FIXTURES = Path(__file__).parent / "fixtures" / "tr" / "documents"


@pytest.mark.parametrize(("fixture", "expected"), [
    ("labour_petition.txt", ("petition", "labour")),
    ("tenancy_notice.txt", ("notice", "tenancy")),
    ("family_decision.txt", ("decision", "family")),
    ("enforcement_order.txt", ("enforcement", "enforcement")),
])
def test_kind_and_area_come_from_the_text(fixture, expected):
    text = (FIXTURES / fixture).read_text(encoding="utf-8")
    assert labels("document.docx", text) == expected


def test_a_drafted_file_keeps_the_kind_it_was_made_as():
    text = (FIXTURES / "labour_petition.txt").read_text(encoding="utf-8")
    assert labels("x.pdf", text, petition_type="ihtarname")[0] == "notice"
    assert labels("x.pdf", text, petition_type="dava")[0] == "petition"


def test_unclear_files_are_other():
    assert labels("IMG_2031.jpg", "") == ("other", "other")
    assert labels("notes.txt", "lorem ipsum dolor sit amet") == ("other", "other")


@pytest.mark.parametrize(("name", "fmt"), [
    ("a.DOCX", "word"), ("a.pdf", "pdf"), ("a.udf", "udf"), ("scan.jpeg", "image"),
    ("t.xlsx", "spreadsheet"), ("m.eml", "email"), ("n.txt", "text"), ("z.bin", "other"),
])
def test_format_comes_from_the_name(name, fmt):
    assert file_format(name) == fmt
