import base64
import json

import httpx

from legal_api.sources.bedesten_decisions import BedestenDecisions
from legal_api.sources.bedesten_statutes import BedestenStatutes
from legal_api.sources.gateway import Gateway
from legal_api.sources.types import Court

OK = {"FMTY": "SUCCESS"}


def _b64(html: str) -> str:
    return base64.b64encode(html.encode()).decode()


def _gateway(routes: dict) -> tuple[Gateway, list]:
    sent = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        sent.append((request.url.path, body))
        return httpx.Response(200, json={"data": routes[request.url.path](body), "metadata": OK})

    return Gateway(transport=httpx.MockTransport(handler), min_interval=0, shared=False), sent


async def test_decision_search_maps_structured_citation_fields():
    gw, sent = _gateway({"/emsal-karar/searchDocuments": lambda b: {
        "total": 1,
        "emsalKararList": [{
            "documentId": "638970600", "itemType": {"name": "YARGITAYKARARI"},
            "birimAdi": "6. Hukuk Dairesi", "esasNo": "2009/11739", "kararNo": "2010/4923",
            "kararTarihiStr": "26.04.2010",
        }],
    }})
    total, refs = await BedestenDecisions(gw).search("kira tahliye", [Court.YARGITAY])
    assert total == 1
    ref = refs[0]
    assert ref.source_id == "bedesten:638970600"
    assert ref.chamber.endswith("6. Hukuk Dairesi") and ref.chamber.startswith("Yarg")
    assert (ref.case_no, ref.decision_no, ref.decision_date) == (
        "2009/11739", "2010/4923", "2010-04-26")
    assert ref.url == "https://mevzuat.adalet.gov.tr/ictihat/638970600"
    _, body = sent[0]
    assert body["data"]["phrase"] == "+kira +tahliye"
    assert body["data"]["itemTypeList"] == ["YARGITAYKARARI"]


async def test_decision_fetch_decodes_html_text():
    gw, _ = _gateway({
        "/emsal-karar/searchDocuments": lambda b: {"total": 1, "emsalKararList": [
            {"documentId": "1", "itemType": {"name": "ISTINAFHUKUK"}, "birimAdi": "X"}]},
        "/emsal-karar/getDocumentContent": lambda b: {
            "content": _b64("<p>First</p><p>Second&nbsp;para</p>"), "mimeType": "text/html"},
    })
    client = BedestenDecisions(gw)
    _, refs = await client.search("x", [Court.ISTINAF])
    decision = await client.fetch(refs[0])
    assert decision.text == "First\nSecond para"
    assert decision.ref.court is Court.ISTINAF


async def test_statute_article_lookup_walks_nested_tree():
    gw, sent = _gateway({
        "/mevzuat/searchDocuments": lambda b: {"total": 1, "mevzuatList": [{
            "mevzuatId": "103273", "mevzuatNo": 6098, "mevzuatAdi": "BORCLAR KANUNU",
            "mevzuatTur": {"name": "KANUN"}, "resmiGazeteSayisi": "27836",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6098"}]},
        "/mevzuat/mevzuatMaddeTree": lambda b: {"children": [
            {"maddeNo": None, "children": [{"maddeNo": 315, "maddeId": "777", "children": []}]},
        ]},
        "/mevzuat/getDocumentContent": lambda b: {"content": _b64("<p>MADDE 315- Text</p>")},
    })
    client = BedestenStatutes(gw)
    _, refs = await client.search(title="Borclar")
    article = await client.article(refs[0], 315)
    assert article.text == "MADDE 315- Text"
    assert sent[-1][1]["data"] == {"documentType": "MADDE", "id": "777"}
    assert await client.article(refs[0], 9999) is None


def test_article_labels_parse_lettered_additional_and_temporary_forms():
    from legal_api.sources.bedesten_statutes import parse_article_label

    assert parse_article_label("315") == ("main", 315, "315")
    assert parse_article_label("269/a") == ("main", 269, "269/a")
    assert parse_article_label("m. 269 / b") == ("main", 269, "269/b")
    assert parse_article_label("Ek 1")[:2] == ("additional", 1)
    assert parse_article_label("ge\u00e7ici madde 3")[:2] == ("temporary", 3)
    assert parse_article_label("nonsense") is None
