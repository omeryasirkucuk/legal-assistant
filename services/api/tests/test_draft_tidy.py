import json
from pathlib import Path

from legal_api.drafting.tidy import tidy

TR = json.loads((Path(__file__).parent / "fixtures" / "tr" / "test_strings.json").read_text(encoding="utf-8"))

FIXTURE = Path(__file__).parent / "fixtures" / "tr" / "documents" / "untidy_petition.txt"


def test_long_bracket_notes_move_to_the_checklist_and_self_talk_is_dropped():
    text = FIXTURE.read_text(encoding="utf-8")
    out = tidy(text)
    petition, checklist = out.split("---")[1], out.split("---")[2]
    assert TR["draft_tidy_1"] in petition and TR["draft_tidy_2"] not in petition
    assert TR["draft_tidy_3"] in checklist
    assert TR["draft_tidy_4"] not in out and TR["draft_tidy_5"] in petition
    assert TR["draft_tidy_6"] in petition and "[[E2]]" in petition


def test_a_text_without_note_and_checklist_is_left_alone():
    assert tidy("Just an answer [with a long note in brackets here].") == \
        "Just an answer [with a long note in brackets here]."


def test_a_petition_asking_for_an_interim_measure_gets_the_header():
    text = (TR["draft_tidy_7"])
    out = tidy(text)
    assert out.split("---")[1].lstrip().startswith(TR["draft_tidy_8"])
    assert tidy(out).count(TR["draft_tidy_9"]) == 1
