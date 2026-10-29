from types import SimpleNamespace

from legal_api.agent.answer import plain_text
from legal_api.agent.atoms import AtomAnswer, _payment_order_answer, segments_from
from legal_api.agent.decompose import Atom, payment_order_branches
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
    assert "[[E1]]" in text
    assert len(text.splitlines()) == 1


def test_payment_order_deadlines_use_distinct_statute_atoms():
    branches = payment_order_branches("ödeme emrinde itiraz süresi kaç gündür?")
    assert branches is not None
    assert len(branches) == 3
    assert branches[0].atoms[0].statutes == (("2004", "62"),)
    assert branches[1].atoms[0].statutes == (("2004", "168"),)
    assert branches[2].atoms[0].statutes == (("2004", "269"),)
    assert branches[2].atoms[1].statutes == (("2004", "269"), ("6098", "315"))
    assert payment_order_branches("İki haklı ihtara dayalı tahliye şartları nelerdir?") is None


def test_payment_order_answers_are_bound_to_exact_statute_quotes():
    general = Atom("Genel haciz yoluyla ilamsız takipte ödeme emrine itiraz süresi kaç gündür?",
                   (("2004", "62"),), "")
    iik62 = SimpleNamespace(
        evidence=SimpleNamespace(article_number="62", key="E1"),
        document="İtirazını, ödeme emrinin tebliği tarihinden itibaren yedi gün içinde dilekçe ile "
                 "veya sözlü olarak icra dairesine bildirmeye mecburdur.",
    )
    result = _payment_order_answer(general, [iik62])
    assert result and result.found
    assert result.segments[0].keys == ("E1",)
    assert "[[E1]]" in result.text

    rent = Atom("Konut ve çatılı işyeri kira alacağı nedeniyle tahliye talepli takipte, "
                "İİK 269'daki kanuni ödeme süresi TBK 315 uyarınca kaç gündür?",
                (("2004", "269"), ("6098", "315")), "")
    iik269 = SimpleNamespace(
        evidence=SimpleNamespace(article_number="269", key="E2"),
        document="Ödeme emri kanuni müddet geçtikten sonra tahliye ihtarını içerir.",
    )
    tbk315 = SimpleNamespace(
        evidence=SimpleNamespace(article_number="315", key="E3"),
        document="Konut ve çatılı işyeri kiralarında ise en az otuz gündür.",
    )
    rent_result = _payment_order_answer(rent, [iik269, tbk315])
    assert rent_result and rent_result.found
    assert rent_result.segments[0].keys == ("E2", "E3")
    assert "30 gündür" in rent_result.text
