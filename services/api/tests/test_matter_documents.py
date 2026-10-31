import uuid

from legal_api.matters import documents
from legal_api.matters.documents import Document, material

WORDS = ["fault", "alimony", "custody", "rent", "witness"]


def _vec(text):
    v = [float(text.lower().count(w)) for w in WORDS]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def _stub(monkeypatch):
    monkeypatch.setattr(documents, "embed_query", _vec)
    monkeypatch.setattr(documents, "embed_passages", lambda ts: [_vec(t) for t in ts])


def test_short_documents_go_whole(monkeypatch):
    _stub(monkeypatch)
    out = material("what about alimony", [Document(uuid.uuid4(), "rapor.pdf", "A short report.")])
    assert len(out) == 1 and out[0].text == "A short report." and "rapor.pdf" in out[0].name


def test_long_documents_give_the_parts_nearest_the_question(monkeypatch):
    _stub(monkeypatch)
    filler = "\n\n".join(f"General explanation paragraph {i}. " * 40 for i in range(30))
    report = filler + "\n\nThe defendant's fault share is set at seventy percent.\n\n" + filler
    other = filler + "\n\nThe monthly rent is ten thousand.\n\n" + filler
    out = material("what is the fault share", [Document(uuid.uuid4(), "bilirkisi.pdf", report),
                                      Document(uuid.uuid4(), "kira.pdf", other)])
    text = "\n".join(a.text for a in out)
    assert "fault share is set at seventy percent" in text
    assert sum(len(a.text) for a in out) <= documents.PASSAGE_CHARS + 100
    assert out[0].name.startswith("bilirkisi.pdf")
