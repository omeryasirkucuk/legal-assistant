from pathlib import Path

from legal_api.drafting.feedback import apply_action, learn_from_edit
from legal_api.drafting.profile import Preferences, sample_of, style_instruction, targets

FORMAL = (Path(__file__).parent / "fixtures" / "tr" / "petition_formal.txt").read_text(
    encoding="utf-8")


def test_without_samples_the_house_defaults_apply():
    t = targets([], Preferences(), "dava")
    assert t.learnt_from == 0 and t.words == 900 and t.register == "balanced"


def test_targets_follow_the_samples_of_the_same_type():
    samples = [sample_of("dava", FORMAL), sample_of("ihtarname", "Kısa bir metin. Bitti.")]
    t = targets(samples, Preferences(), "dava")
    assert t.learnt_from == 1
    assert t.register == "formal"
    assert t.closing == "arz ve talep ederiz"
    assert "SONUÇ VE İSTEM" in t.headings


def test_buttons_move_length_and_register():
    p = apply_action(apply_action(Preferences(), "shorter"), "plainer")
    t = targets([sample_of("dava", FORMAL)], p, "dava")
    base = targets([sample_of("dava", FORMAL)], Preferences(), "dava")
    assert t.words < base.words and t.register == "balanced"


def test_a_shortened_edit_lowers_the_length_preference():
    p = learn_from_edit(Preferences(), FORMAL, FORMAL[: len(FORMAL) // 2])
    assert p.length_factor < 0.8


def test_instruction_names_the_targets():
    text = style_instruction(targets([], Preferences(), "dava"), ["Kararları tam künyeyle yaz."])
    assert "900" in text and "Kararları tam künyeyle yaz." in text and "{" not in text


def test_a_chosen_length_and_register_replace_the_samples():
    p = Preferences(length="short", register="plain")
    t = targets([sample_of("dava", FORMAL)], p, "dava")
    assert t.words == 450 and t.register == "plain"
    assert targets([], apply_action(p, "longer"), "dava").words > 450


def test_the_sample_to_imitate_is_of_the_case_area_first():
    from legal_api.drafting.profile import Sample, closest_sample
    divorce = Sample("dava", {}, "x" * 50, closeness=0.86, area="family")
    labour = Sample("dava", {}, "x" * 10, closeness=0.85, area="labour")
    assert closest_sample([divorce, labour], "dava", "labour") == (labour, True)
    # Without a sample of the case's area, another one is given, marked as such.
    assert closest_sample([divorce], "dava", "labour") == (divorce, False)
    # An area not told from the request: closeness in meaning decides.
    assert closest_sample([divorce, labour], "dava") == (divorce, True)


def test_a_sample_of_the_same_kind_of_case_comes_before_one_of_the_same_area():
    from legal_api.drafting.profile import Sample, closest_sample
    agreed = Sample("dava", {}, "x" * 90, closeness=0.9, area="family", matter="anlaşmalı boşanma")
    contested = Sample("dava", {}, "x" * 10, closeness=0.8, area="family", case_kind="bosanma")
    assert closest_sample([agreed, contested], "dava", "family", "bosanma") == (contested, True)
    assert closest_sample([agreed], "dava", "family", "bosanma") == (agreed, False)
