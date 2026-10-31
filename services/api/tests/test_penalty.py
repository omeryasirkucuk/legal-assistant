import json
from fractions import Fraction
from pathlib import Path

from legal_api.agent.sources import TITLE_PREFIX, Source
from legal_api.calc.penalty import (
    apply,
    duration_text,
    paragraph,
    read_range,
    read_ratio,
)
from legal_api.calc.penalty_sources import penalty_sources
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import penalty_terms

TCK = json.loads((Path(__file__).parent / "fixtures" / "tr" / "penal_articles.json")
                 .read_text(encoding="utf-8"))
W = penalty_terms()["words"]


def dur(*parts) -> str:
    """A duration as the calculator writes it: dur(2, "year", 3, "month")."""
    return " ".join(f"{n} {W[u]}" for n, u in zip(parts[::2], parts[1::2], strict=True))


def _span(r):
    return duration_text(r.low), duration_text(r.high)


def test_ranges_are_read_from_the_paragraph_named():
    assert _span(read_range(paragraph(TCK["86"], 1))) == (dur(1, "year", 6, "month"), dur(3, "year"))
    simple = read_range(paragraph(TCK["86"], 2))
    assert _span(simple) == (dur(6, "month"), dur(1, "year", 6, "month")) and simple.fine
    assert _span(read_range(paragraph(TCK["106"], 2))) == (dur(2, "year"), dur(7, "year"))


def test_an_item_with_its_own_ratio_gets_that_one():
    weapon = read_ratio(paragraph(TCK["86"], 3), "e")
    cruelty = read_ratio(paragraph(TCK["86"], 3), "f")
    assert (weapon.kind, weapon.low, weapon.high) == ("increase", Fraction(1, 2), Fraction(1, 2))
    assert (cruelty.low, cruelty.high) == (Fraction(1), Fraction(1))


def test_decreases_up_to_and_between():
    discretion = read_ratio(paragraph(TCK["62"], 1))
    assert (discretion.kind, discretion.shape, discretion.high) == ("decrease", "up_to", Fraction(1, 6))
    unjust = read_ratio(paragraph(TCK["29"], 1))
    assert (unjust.shape, unjust.low, unjust.high) == ("range", Fraction(1, 4), Fraction(3, 4))


def test_a_weapon_raises_both_bounds_by_half():
    weapon = read_ratio(paragraph(TCK["86"], 3), "e")
    assert [duration_text(d) for d in apply(read_range(paragraph(TCK["86"], 2)), [weapon])] == [dur(9, "month"), dur(2, "year", 3, "month")]
    assert [duration_text(d) for d in apply(read_range(paragraph(TCK["86"], 1)), [weapon])] == [dur(2, "year", 3, "month"), dur(4, "year", 6, "month")]


class _Finder:
    def __init__(self, ledger):
        self.ledger = ledger

    async def article(self, law, label):
        text = TCK.get(label)
        if text is None:
            return None
        document = f"{TITLE_PREFIX}{TCK['_titles'][label]}\n{text}"
        return Source(self.ledger.add_calculation(source_id=f"a{label}", citation=f"TCK m. {label}",
                                                  text=text), document)


LABELS = TCK["_labels"]


async def _calc(*specs):
    ledger = EvidenceLedger()
    sources = await penalty_sources(list(specs), _Finder(ledger), ledger)
    return [s.document for s in sources if s.evidence.citation.startswith(W["citation"].split("{")[0])]


def _spec(label, article, paragraph, *mods):
    return {"label": LABELS[label], "law": "5237", "article": article, "paragraph": paragraph,
            "modifiers": [{"law": "5237", "article": a, "paragraph": p, "item": i} for a, p, i in mods]}


def _result(low, high):
    return W["result"].format(low=low, high=high)


async def test_the_calculation_is_a_cited_source_and_unknown_articles_warn():
    (simple,) = await _calc(_spec("weapon_simple_injury", "86", "2", ("86", "3", "e")))
    assert _result(dur(9, "month"), dur(2, "year", 3, "month")) in simple
    assert "TCK m. 86/3-e" in simple
    (unknown,) = await _calc(_spec("weapon_injury", "999", ""))
    assert W["not_read"].split("{")[0] in unknown


async def test_the_label_finds_the_weapon_increase_the_model_left_out():
    (injury,) = await _calc(_spec("weapon_injury", "86", "1"))
    assert _result(dur(2, "year", 3, "month"), dur(4, "year", 6, "month")) in injury
    (both,) = await _calc(_spec("weapon_simple_injury", "86", "1"))
    assert _result(dur(9, "month"), dur(2, "year", 3, "month")) in both
    assert _result(dur(2, "year", 3, "month"), dur(4, "year", 6, "month")) in both


async def test_the_same_increase_named_twice_is_applied_once():
    (text,) = await _calc(_spec("weapon_simple_injury", "86", "3", ("86", "3", "e")))
    assert _result(dur(9, "month"), dur(2, "year", 3, "month")) in text


async def test_an_unrelated_provision_is_left_out():
    (text,) = await _calc(_spec("weapon_injury", "86", "1", ("87", "", ""), ("86", "3", "b")))
    assert _result(dur(2, "year", 3, "month"), dur(4, "year", 6, "month")) in text
    assert text.count(W["ignored"].split("{")[0]) == 2


async def test_the_armed_threat_paragraph_replaces_the_plain_one():
    (text,) = await _calc(_spec("weapon_threat", "106", "1"))
    assert _result(dur(2, "year"), dur(7, "year")) in text
    (named,) = await _calc(_spec("weapon_threat", "106", "1", ("106", "2", "a")))
    assert _result(dur(2, "year"), dur(7, "year")) in named


async def test_a_ratio_paragraph_named_as_the_base_applies_to_each_earlier_range():
    (text,) = await _calc(_spec("weapon_injury", "86", "3"))
    assert _result(dur(2, "year", 3, "month"), dur(4, "year", 6, "month")) in text
    assert _result(dur(9, "month"), dur(2, "year", 3, "month")) in text
