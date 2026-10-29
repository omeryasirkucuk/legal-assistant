from types import SimpleNamespace

from legal_api.agent.answer import plain_text
from legal_api.agent.atoms import AtomAnswer, segments_from
from legal_api.agent.decompose import Atom
from legal_api.agent.sources import Source
from legal_api.grounding.evidence import EvidenceLedger


def _sources() -> list[Source]:
    ledger = EvidenceLedger()
    a = ledger.add_decision(source_id="a", chamber="C", case_no="1", decision_no="2",
                            decision_date="2025-01-01", url="u", text="Metin bir.")
    b = ledger.add_decision(source_id="b", chamber="C", case_no="3", decision_no="4",
                            decision_date="2025-01-02", url="u", text="Metin iki.")
    return [Source(a, a.text), Source(b, b.text)]


def _block(text, *doc_indexes):
    cites = [SimpleNamespace(document_index=i, cited_text=f"q{i}") for i in doc_indexes]
    return SimpleNamespace(type="text", text=text, citations=cites or None)


def test_citations_map_document_indexes_to_evidence_keys():
    content = [SimpleNamespace(type="thinking"), _block("Sure "), _block("7 gundur", 1, 0, 1)]
    segments = segments_from(content, _sources())
    assert [(s.text, s.keys) for s in segments] == [("Sure ", ()), ("7 gundur", ("E2", "E1"))]


def test_found_answer_without_any_citation_is_not_grounded():
    atom = Atom("soru", (), "")
    assert not AtomAnswer(atom, True, segments_from([_block("iddia")], _sources())).grounded
    assert AtomAnswer(atom, False).grounded


def test_plain_text_marks_missing_sub_answers():
    structure = {"branches": [{"label": "Genel haciz", "atoms": [
        {"ask": "x", "found": True, "segments": [{"text": "7 gun", "keys": ["E1"]}]},
        {"ask": "y", "found": False, "segments": []}]}]}
    text = plain_text(structure)
    assert text.startswith("- Genel haciz: 7 gun ")
    assert len(text.splitlines()) == 1
