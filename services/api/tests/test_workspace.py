import io
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from docx import Document
from openpyxl import load_workbook

from legal_api import llm
from legal_api.agent import pipeline
from legal_api.agent.understand import Understanding
from legal_api.api import chats
from legal_api.config import get_settings
from legal_api.main import create_app
from legal_api.sources.gateway import Gateway
from legal_api.workspace.engine import InvalidPlan, Plan, evaluate
from legal_api.workspace.ground import ground
from legal_api.workspace.public import PublicResearch, public_query
from tests.accounts import register_invited

OFFICIAL = (
    "https://cdn.tbmm.gov.tr/KKBSPublicFile/D24/Y3/T1/KanunMetni/"
    "dfb267a1-b63c-4df2-a388-b844f84334f9.html"
)
RATE = "kalan vadesi otuz altı ayı aşmayan kredilerde yüzde birini"
FIXED = "Faiz oranının sabit olarak belirlenmesi hâlinde, sözleşmede yer verilmek suretiyle"
DATE = "Erken ödeme tarihi 2025-06-18"
FILE = (
    f"{DATE}\n"
    "Faiz indirimi sonrası erken ödenen tutar: 120.000,00 TL\n"
    "Kalan vade: 24 ay\n"
    "Kredi sabit faizlidir. Erken ödeme tazminatı sözleşmede kararlaştırılmıştır."
)
CORRECTION = (
    "İlk dosyadaki erken ödeme tutarı yerine yeni dekonttaki 150.000,00 TL geçerli. "
    "Yeniden hesapla ve talep.docx dosyasındaki üst sınırı güncelle."
)


def record(ref, quote):
    return {"ref": ref, "quote": quote}


def proposal(document, law):
    amount = record(document, "Faiz indirimi sonrası erken ödenen tutar: 120.000,00 TL")
    return {
        "title": "Erken ödeme tazminatı üst sınırı",
        "inputs": [
            {"key": "erken", "label": "Erken ödenen ana tutar", "unit": "TRY",
             "value": "120000", "passage": amount,
             "meaning": "Faiz indirimi sonrası ödeme"},
            {"key": "tarih", "label": "Erken ödeme tarihi", "unit": "date",
             "value": "2025-06-18", "passage": record(document, DATE),
             "meaning": "Tavan rejiminin değerlendirildiği tarih"},
            {"key": "vade", "label": "Kalan vade (ay)", "unit": "number", "value": "24",
             "passage": record(document, "Kalan vade: 24 ay"),
             "meaning": "İlgili oran diliminin seçimi"},
            {"key": "oran", "label": "Yasal oran (yüzde puanı)", "unit": "number", "value": "1",
             "passage": record(law, RATE), "meaning": "Kalan vade 36 ayı aşmıyor"},
        ],
        "rules": [{"key": "tavan", "applies_on": "2025-06-18", "reasoning":
                   "Sabit faiz ve sözleşme hükmü mevcut. 24 ay kalan vadede yüzde 1 uygulanır.",
                   "passages": [record(law, RATE), record(law, FIXED), record(document,
                                "Kredi sabit faizlidir. Erken ödeme tazminatı sözleşmede kararlaştırılmıştır.")]}],
        "steps": [
            {"key": "carpan", "label": "Oran çarpanı", "operation": "percent",
             "args": ["oran"], "rule": "tavan"},
            {"key": "sonuc", "label": "Erken ödeme tazminatı üst sınırı", "operation": "multiply",
             "args": ["erken", "carpan"], "rule": "tavan"},
        ],
        "outputs": ["sonuc"],
    }


def test_source_bound_engine_handles_exact_amounts_and_rejects_false_references():
    from legal_api.grounding.evidence import EvidenceLedger

    ledger = EvidenceLedger()
    document = ledger.add_record(source_id="contract", kind="case_file", citation="Belge", text=FILE)
    law = ledger.add_record(source_id="official", kind="official", citation="6502 m. 37",
                            url=OFFICIAL, text=f"{FIXED}\n{RATE}")
    plan = Plan.model_validate(proposal(document.key, law.key))
    values = evaluate(plan)
    assert values["sonuc"].dump() == "1200.00"
    assert ground(ledger, plan, values)["rules"]["tavan"][0]["url"] == OFFICIAL
    plan.inputs[0].value = "12000"
    with pytest.raises(InvalidPlan, match="girdi değeri"):
        ground(ledger, plan, evaluate(plan))
    plan.inputs[0].value = "120000"
    plan.rules[0].passages[0].quote += " (sonradan eklenen ifade)"
    with pytest.raises(InvalidPlan, match="birebir"):
        ground(ledger, plan, evaluate(plan))


async def test_web_scope_and_protected_mode(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "brave_search_api_key", "test-key")
    monkeypatch.setattr(settings, "data_mode", "development")
    requested = []

    def dispatch(request):
        requested.append(request)
        assert request.url.host == "api.search.brave.com"
        assert "Narlidere" not in request.url.params["q"]
        assert "92011" not in request.url.params["q"]
        return httpx.Response(200, json={"web": {"results": [
            {"title": "Official", "url": OFFICIAL},
            {"title": "Foreign", "url": "https://mevzuat.gov.tr.example.org/1.pdf"},
            {"title": "Foreign", "url": "https://resmigazete.gov.tr:81/1.pdf"},
        ]}})

    gateway = Gateway(httpx.MockTransport(dispatch), min_interval=0)
    try:
        research = PublicResearch(gateway)
        assert public_query("erken Narlidere ödeme 92011") == "erken ödeme"
        assert len(await research.search("erken Narlidere ödeme 92011")) == 1
        monkeypatch.setattr(settings, "data_mode", "protected")
        assert await research.search("erken ödeme") == []
        with pytest.raises(ValueError):
            await research.read("W1")
        assert len(requested) == 1
    finally:
        await gateway.aclose()


async def test_chat_unknown_case_reformat_update_edit_and_account_isolation(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "brave_search_api_key", "test-key")
    monkeypatch.setattr(settings, "data_mode", "development")

    async def understand(*_args):
        return Understanding(task="workspace")

    async def title(*_args):
        return None

    def official_response(request):
        if request.url.host == "api.search.brave.com":
            assert request.url.params["q"].startswith("erken ödeme tazminatı")
            return httpx.Response(200, json={"web": {"results": [
                {"title": "TBMM · 6502 sayılı Kanun", "url": OFFICIAL}]}})
        assert str(request.url) == OFFICIAL
        return httpx.Response(200, headers={"Content-Type": "text/html"},
                              content=(f'<meta charset="Windows-1254"><p>MADDE\n37</p>'
                                       f'<p>{FIXED}</p><p>{RATE}</p>').encode("cp1254"))

    def gateway():
        return Gateway(httpx.MockTransport(official_response), min_interval=0)

    def action(name, **payload):
        return {"action": name, "payload": json.dumps(payload, ensure_ascii=False)}

    async def create(_role, _usage, purpose, **params):
        context = json.loads(params["messages"][0]["content"])
        if purpose in ("workspace_verify", "workspace_revision", "workspace_reuse", "workspace_edit"):
            result = {"approved": True, **({"reason": ""} if purpose == "workspace_verify" else {})}
        else:
            assert purpose == "workspace_plan"
            msg, history = context["message"], context["actions"]
            assert not history or "error" not in history[-1], history[-1] if history else ""
            n = len(history)
            if msg == "Excel olarak indir":
                result = action("finish", format="xlsx", reuse=True, edits=[])
            elif msg == "Yanıt içinde tablo göster":
                result = action("finish", format="table", reuse=True, edits=[])
            elif msg == "Çelişkili dekontlarla kesin sonucu yaz":
                if n == 0:
                    result = action("read_file", file=context["files"][0]["id"], start=1, sheet="")
                else:
                    result = action("blocked", reason="conflict", item="Erken ödeme tutarı",
                                    format="short")
            elif msg == CORRECTION:
                if n == 0:
                    result = action("revise_inputs", changes=[{
                        "key": "erken", "value": "150000",
                        "passage": record(context["statement"], "yeni dekonttaki 150.000,00 TL")}])
                else:
                    file = next(f["id"] for f in context["files"] if f["name"] == "talep.docx")
                    result = action("finish", format="short", reuse=False, edits=[{
                        "file": file, "changes": [{"paragraph": 1, "before": "1.200,00 TL",
                                                  "result": "sonuc"}]}])
            else:
                match n:
                    case 0:
                        result = action("read_file", file="F1", start=1, sheet="")
                    case 1:
                        result = action("search_web", query="erken ödeme tazminatı")
                    case 2:
                        result = action("read_web", id="W1", offset=0, find="MADDE 37")
                    case 3:
                        result = action("calculate", **proposal(
                            history[0]["result"][0]["ref"],
                            history[2]["result"]["source"][0]["ref"]))
                    case _:
                        result = action("finish", format="short", reuse=False, edits=[])
        return SimpleNamespace(content=[llm.TextBlock("text", json.dumps(result))])

    monkeypatch.setattr(pipeline, "understand", understand)
    monkeypatch.setattr(pipeline, "Gateway", gateway)
    monkeypatch.setattr(chats, "generate_title", title)
    monkeypatch.setattr(llm, "create", create)

    app = create_app()

    async def register(client):
        await register_invited(client, f"workspace-{uuid.uuid4()}@example.com",
                               "Workspace test", "test-pass-123")

    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as other,
    ):
        await register(client)
        await register(other)
        chat_id = (await client.post("/chats", json={"content": "Dosya hesabı"})).json()["id"]
        path = f"/chats/{chat_id}/messages"
        uploaded = await client.post("/files", files={
            "file": ("kredi.txt", FILE.encode(), "text/plain")})
        assert uploaded.is_success, uploaded.text

        async def ask(message, files=()):
            sent = await client.post(path, json={"content": message, "file_ids": list(files)})
            assert "event: saved" in sent.text, sent.text
            return (await client.get(path)).json()[-1]

        short = await ask("Dosyaya göre bankanın isteyebileceği üst sınırı kısaca hesapla",
                          [uploaded.json()["id"]])
        assert "1.200,00 TL" in short["content"]
        assert short["meta"]["workspace"]["format"] == "short"
        prefix = f"{path}/{short['id']}"
        key = next(e["key"] for e in short["evidence"] if e["kind"] == "calculation")
        source = (await client.get(f"{prefix}/evidence/{key}")).json()
        assert RATE in source["text"] and "kredi.txt" in source["text"]
        assert (await client.get(f"{prefix}/output/xlsx")).status_code == 404
        assert (await other.get(f"{prefix}/evidence/{key}")).status_code == 404

        table = await ask("Yanıt içinde tablo göster")
        assert "| Kalem | Sonuç |" in table["content"]
        assert table["meta"]["workspace"]["revision"] == 1

        excel = await ask("Excel olarak indir")
        excel_path = f"{path}/{excel['id']}/output/xlsx"
        downloaded = await client.get(excel_path)
        assert downloaded.status_code == 200, downloaded.text[:100] if not downloaded.is_success else ""
        book = load_workbook(io.BytesIO(downloaded.content))
        assert book["Hesap"]["B5"].data_type == "f"
        assert book["Girdiler ve işlemler"]["B2"].value == 120000
        assert book["Girdiler ve işlemler"]["B7"].value == "=B2*B6"
        assert (await other.get(excel_path)).status_code == 404

        doc = Document()
        doc.add_paragraph("Paragraf: 1.200,00 TL üst sınırdır.")
        doc.add_paragraph("İkinci paragraf.")
        original = io.BytesIO()
        doc.save(original)
        word = await client.post("/files", files={"file": (
            "talep.docx", original.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert word.is_success, word.text
        revision = await ask(CORRECTION, [word.json()["id"]])
        assert "1.500,00 TL" in revision["content"]
        summary = revision["meta"]["workspace"]
        assert summary["revision"] == 2
        assert summary["changes"][0]["before"] == "1200.00"
        edited = await client.get(f"{path}/{revision['id']}/output/0")
        assert edited.status_code == 200, edited.text[:100] if not edited.is_success else ""
        assert [p.text for p in Document(io.BytesIO(edited.content)).paragraphs] == [
            "Paragraf: 1.500,00 TL üst sınırdır.", "İkinci paragraf."]

        source_file = f"/files/{word.json()['id']}"
        assert (await client.get(source_file)).content == original.getvalue()
        assert (await client.delete(source_file)).status_code == 204
        assert (await client.get(f"{path}/{revision['id']}/output/0")).content == edited.content
        assert load_workbook(io.BytesIO((await client.get(excel_path)).content))[
            "Girdiler ve işlemler"]["B2"].value == 120000
        blocked = await ask("Çelişkili dekontlarla kesin sonucu yaz")
        assert "Belgelerde sonucu değiştirecek bir çelişki var" in blocked["content"]
        assert "1.500" not in blocked["content"] and "workspace" not in blocked["meta"]
        assert any(s["citation"] == "İncelenen kaynaklar" for s in blocked["evidence"])
        assert (await client.delete(f"/chats/{chat_id}")).status_code == 204
