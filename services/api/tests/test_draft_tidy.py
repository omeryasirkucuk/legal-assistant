from pathlib import Path

from legal_api.drafting.tidy import tidy

FIXTURE = Path(__file__).parent / "fixtures" / "tr" / "documents" / "untidy_petition.txt"


def test_long_bracket_notes_move_to_the_checklist_and_self_talk_is_dropped():
    text = FIXTURE.read_text(encoding="utf-8")
    out = tidy(text)
    petition, checklist = out.split("---")[1], out.split("---")[2]
    assert "[Dava değeri]" in petition and "ayrıca değerlendirilecektir" not in petition
    assert "ayrıca değerlendirilecektir" in checklist
    assert "hangi vakıanın" not in out and "Mesajların ekran görüntüleri sunulmuştur" in petition
    assert "[Davalının adresi]" in petition and "[[E2]]" in petition


def test_a_text_without_note_and_checklist_is_left_alone():
    assert tidy("Just an answer [with a long note in brackets here].") == \
        "Just an answer [with a long note in brackets here]."


def test_a_petition_asking_for_an_interim_measure_gets_the_header():
    text = ("Not.\n---\nAİLE MAHKEMESİ SAYIN HÂKİMLİĞİNE\n\nSONUÇ VE İSTEM: 1. Araca ihtiyati tedbir "
            "şerhi konulmasına,\n---\nListe")
    out = tidy(text)
    assert out.split("---")[1].lstrip().startswith("**İHTİYATİ TEDBİR TALEPLİDİR**")
    assert tidy(out).count("İHTİYATİ TEDBİR TALEPLİDİR") == 1
