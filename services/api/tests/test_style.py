from pathlib import Path

from legal_api.drafting.style import measure

FIXTURES = Path(__file__).parent / "fixtures" / "tr"


def test_formal_petition_is_measured():
    s = measure((FIXTURES / "petition_formal.txt").read_text(encoding="utf-8"))
    assert s.words > 100
    assert s.formal_per_1000 > 40           # işbu, mezkûr, binaenaleyh, hasebiyle ...
    assert s.numbered_paragraphs == 2
    assert s.closing == "arz ve talep ederiz"
    assert {"DAVACI", "KONU", "AÇIKLAMALAR", "SONUÇ VE İSTEM"} <= set(s.headings)


def test_plain_text_has_a_low_register_score():
    s = measure("Davalı kirayı ödemedi. Ona iki kez yazdık. Tahliye istiyoruz.")
    assert s.formal_per_1000 == 0
    assert s.words_per_sentence < 5


def test_empty_text():
    assert measure("").words == 0


def test_a_draft_is_measured_on_its_petition_part():
    from legal_api.drafting.style import petition_part
    draft = ("Not.\n---\n**DAVACI :** X\n**SONUÇ VE İSTEM :** Kabulüne karar verilmesini "
             "saygılarımızla arz ve talep ederiz.\n---\n**Eksikler**\n- adres")
    body = petition_part(draft)
    assert body.startswith("\n**DAVACI") and "Eksikler" not in body
    s = measure(body)
    assert s.headings == ["DAVACI", "SONUÇ VE İSTEM"] and s.closing == "arz ve talep ederiz"


def test_petition_span_finds_the_petition_between_note_and_checklist():
    from legal_api.drafting.style import petition_span
    text = "Note.\n---\nThe petition body is the longest part.\n---\nChecklist"
    start, end = petition_span(text)
    assert text[start:end].strip() == "The petition body is the longest part."
    assert petition_span("no dashes") == (0, 9)
