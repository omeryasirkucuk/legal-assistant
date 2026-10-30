import json
from datetime import UTC, datetime
from pathlib import Path

from legal_api.agent.follow import _plan
from legal_api.retrieval.references import find_references, name_match
from legal_api.retrieval.statutes import StatuteHit

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "tr" / "references.json")
                     .read_text(encoding="utf-8"))
ART_269 = FIXTURE["art_269"]   # enforcement law art. 269, abridged, plus added reference forms
LAWS = FIXTURE["laws"]
NAMES = FIXTURE["names"]


def _hit() -> StatuteHit:
    return StatuteHit(1, "2004", LAWS["2004"], "s", "269", "h", ART_269, "u", datetime.now(UTC))


def test_reference_forms():
    refs = find_references(ART_269)
    assert [(r.labels, r.law_number, r.law_name) for r in refs] == [
        (("260", "288"), None, NAMES["old_code"]),
        (("62",), None, None),
        (("315",), "6098", None),
        (("269/a",), None, None),
    ]
    assert refs[0].sentence.startswith(FIXTURE["first_sentence_start"])


def test_name_match():
    assert name_match(NAMES["old_code"], LAWS["6098"]) == "partial"
    assert name_match(NAMES["current_code"], LAWS["6098"]) == "exact"
    assert name_match(NAMES["enforcement"], LAWS["2004"]) == "exact"
    assert name_match(NAMES["civil"], LAWS["6098"]) is None


def test_plan_resolves_by_label_or_content():
    plans = [_plan(_hit(), r, LAWS) for r in find_references(ART_269)]
    old_code, same_law, numbered, this_law = plans
    assert (old_code.exact_law, old_code.content_laws) == (None, ["6098"])
    assert same_law.exact_law == "2004"
    assert numbered.exact_law == "6098"
    assert this_law.exact_law == "2004"
