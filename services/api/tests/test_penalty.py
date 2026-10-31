import json
from fractions import Fraction
from pathlib import Path

from legal_api.agent.sources import Source
from legal_api.calc.penalty import apply, duration_text, paragraph, read_range, read_ratio
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
        return Source(self.ledger.add_calculation(source_id=f"a{label}", citation=f"TCK m. {label}",
                                                  text=text), text)


async def test_the_calculation_is_a_cited_source_with_its_phrases():
    ledger = EvidenceLedger()
    sources = await penalty_sources([
        {"label": "simple injury with a weapon", "law": "5237", "article": "86", "paragraph": "2",
         "modifiers": [{"law": "5237", "article": "86", "paragraph": "3", "item": "e"}]},
        {"label": "unknown", "law": "5237", "article": "999", "paragraph": "", "modifiers": []},
    ], _Finder(ledger), ledger)
    calc = [s for s in sources if s.evidence.citation.startswith(W["citation"].split("{")[0])]
    assert len(calc) == 2
    assert W["result"].format(low=dur(9, "month"), high=dur(2, "year", 3, "month")) in calc[0].document
    assert "TCK m. 86/3-e" in calc[0].document
    assert W["not_read"].split("{")[0] in calc[1].document


async def test_a_qualified_form_named_as_a_modifier_replaces_the_base():
    ledger = EvidenceLedger()
    sources = await penalty_sources([
        {"label": "threat with a weapon", "law": "5237", "article": "106", "paragraph": "1",
         "modifiers": [{"law": "5237", "article": "106", "paragraph": "2", "item": "a"}]},
    ], _Finder(ledger), ledger)
    assert W["result"].format(low=dur(2, "year"), high=dur(7, "year")) in sources[-1].document


async def test_a_ratio_paragraph_named_as_the_base_applies_to_each_earlier_range():
    ledger = EvidenceLedger()
    sources = await penalty_sources([
        {"label": "injury with a weapon", "law": "5237", "article": "86", "paragraph": "3",
         "modifiers": []},
    ], _Finder(ledger), ledger)
    text = sources[-1].document
    assert W["result"].format(low=dur(2, "year", 3, "month"), high=dur(4, "year", 6, "month")) in text
    assert W["result"].format(low=dur(9, "month"), high=dur(2, "year", 3, "month")) in text
