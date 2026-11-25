"""The chat's bounded action loop for a sourced calculation and its presentation."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, ValidationError

from legal_api import llm
from legal_api.agent.sources import Source, SourceFinder
from legal_api.db.file_models import StoredFile
from legal_api.grounding.evidence import Evidence, EvidenceLedger
from legal_api.grounding.normalize import tr_fold
from legal_api.prompts import prompt
from legal_api.sources.gateway import SourceError
from legal_api.workspace.documents import EditSet, excerpt, word_copy
from legal_api.workspace.engine import VERSION, InvalidPlan, Plan, Record, Value, evaluate
from legal_api.workspace.ground import STATEMENT_KEY, ground, review, schema, structured
from legal_api.workspace.public import PublicResearch, public_query

ACTIONS = ("search_files", "read_file", "search_law", "read_law", "search_cases", "search_web", "read_web",
           "calculate", "finish", "blocked")
ACTION_SCHEMA = schema({"action": {"type": "string", "enum": list(ACTIONS)},
                        "payload": {"type": "string"}})
MAX_TURNS = 16
MAX_FOLLOWUP_SOURCES = 110
Format = Literal["short", "table", "xlsx"]


class Query(Record):
    query: str = Field(min_length=2, max_length=250)


class Law(Record):
    law: str = Field(pattern=r"^[0-9]{1,5}$")
    article: str = Field(pattern=r"^(?:(?:ek|geçici) )?[0-9]{1,4}(?:/[a-zA-Z])?$")


class ReadWeb(Record):
    id: str = Field(pattern=r"^[WEU][1-9][0-9]{0,2}$")
    offset: int = Field(ge=0, le=999999)
    find: str = Field(default="", max_length=120)


class ReadFile(Record):
    file: str = Field(pattern=r"^F[1-9][0-9]{0,2}$")
    start: int = Field(ge=1, le=5000)
    sheet: str = Field(max_length=31)


class Finish(Record):
    format: Format
    reuse: bool
    edits: list[EditSet] = Field(max_length=5)


Gap = Literal["input", "conflict", "rule", "date", "operation", "document"]
GAP_TEXT = {
    "input": "Gerekli dosya bilgisi doğrulanamadı.",
    "conflict": "Belgelerde sonucu değiştirecek bir çelişki var.",
    "rule": "Uygulanacak kural resmî kaynakla doğrulanamadı.",
    "date": "Kuralın dosyadaki tarihe uygulanabilirliği doğrulanamadı.",
    "operation": "Bu adım mevcut hesap işlemleriyle güvenle çalıştırılamadı.",
    "document": "Gerekli belge ya da konum okunamadı.",
}


class Blocked(Record):
    reason: Gap
    item: str = Field(max_length=160)
    format: Format

    def message(self) -> str:
        label = re.sub(r"\b(?:\d+\s+sayılı\s+)?m\.?\s*\d+\b", "", self.item.strip()).strip()
        valid_label = bool(label) and all(c.isalpha() or c in " /-" for c in label)
        return GAP_TEXT[self.reason] + (f" Açık kalem — {label}." if valid_label else "")


@dataclass
class Context:
    files: list[StoredFile] = field(default_factory=list)
    previous: dict | None = None
    previous_evidence: list = field(default_factory=list)


@dataclass
class Outcome:
    text: str
    snapshot: dict | None
    sources: list[Evidence]
    files: list[bytes] = field(default_factory=list)


def plain(text: str) -> str:
    cleaned = " ".join(text.split()).replace("<", "‹").replace(">", "›")
    return re.sub(r"([\\`*_\[\]{}()!#|~])", r"\\\1", cleaned)


def display(value: Value) -> str:
    if value.unit == "date":
        return value.data.strftime("%d.%m.%Y")
    if value.unit in ("number", "day"):
        number = value.dump()
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return number.replace(".", ",") + (" gün" if value.unit == "day" else "")
    places = max(2, -value.data.normalize().as_tuple().exponent)
    amount = f"{value.data:,.{places}f}".translate(str.maketrans(",.", ".,"))
    unit = "TL" if value.unit == "TRY" else value.unit
    return f"{amount} {unit}"


def records(sources: list[Source]) -> list[dict]:
    return [{"ref": s.evidence.key, "citation": s.evidence.citation, "text": s.document[:6500]}
            for s in sources]


def _remap(plan: Plan, refs: dict[str, str]) -> Plan:
    data = plan.model_dump()
    for item in data["inputs"]:
        item["passage"]["ref"] = refs[item["passage"]["ref"]]
    for rule in data["rules"]:
        for passage in rule["passages"]:
            passage["ref"] = refs[passage["ref"]]
    return Plan.model_validate(data)


class Workspace:
    def __init__(self, context: Context, finder: SourceFinder, web: PublicResearch,
                 ledger: EvidenceLedger, usage: llm.Usage):
        self.context, self.finder, self.web = context, finder, web
        self.ledger, self.usage = ledger, usage
        self.files = {f"F{i}": file for i, file in enumerate(context.files[:75], 1)}
        self.opened_public: dict[str, tuple[str, str, str, str]] = {}
        self.comparison: list[str] = []
        self.inspected: set[str] = set()
        self.origins: dict[str, dict] = {}
        self.previous: Plan | None = None
        self.current: Plan | None = None

    def _restore(self) -> None:
        if not self.context.previous or self.context.previous.get("engine") != VERSION:
            return
        original = Plan.model_validate(self.context.previous["plan"])
        if len(self.context.previous_evidence) <= MAX_FOLLOWUP_SOURCES:
            refs = {source.key: self.ledger.retain(source).key
                    for source in self.context.previous_evidence if source.kind != "calculation"}
            self.previous = _remap(original, refs)
            self.origins.update({refs[key]: value
                                 for key, value in self.context.previous.get("origins", {}).items()
                                 if key in refs})

    def _sources(self, sources: list[Source]) -> list[dict]:
        self.inspected.update(source.evidence.key for source in sources)
        return records(sources)

    async def lookup(self, action: str, data: dict) -> list | dict:
        if action == "search_files":
            query = Query.model_validate(data).query
            terms = set(re.findall(r"[^\W_]{3,}", tr_fold(query)))
            matches = []
            for key, file in self.files.items():
                title = tr_fold(file.name)
                lines = file.text.splitlines()
                best = max(lines, key=lambda line: sum(t in tr_fold(line) for t in terms),
                           default="")
                rank = sum(2 * (t in title) + (t in tr_fold(best)) for t in terms)
                if rank:
                    matches.append((rank, {"file": key, "name": file.name, "hint": best[:500]}))
            return [item for _, item in sorted(matches, key=lambda entry: -entry[0])[:8]]
        if action == "read_file":
            req = ReadFile.model_validate(data)
            if req.file not in self.files:
                raise ValueError("Dosya bu sohbette bulunamadı.")
            file = self.files[req.file]
            found = await asyncio.to_thread(excerpt, file, req.start, req.sheet)
            if not found.text.strip():
                raise ValueError("Bu konumda okunabilir metin bulunamadı.")
            src = self.ledger.add_record(
                source_id=f"file:{file.id}:{file.sha256}:{found.location}", kind="case_file",
                citation=f"{file.name} · {found.location}", text=found.text,
                url=f"/files/{file.id}")
            self.inspected.add(src.key)
            self.origins[src.key] = {"file_id": str(file.id), "sha256": file.sha256,
                                     "location": found.location}
            self.comparison.append(f"{src.key} {src.citation}\n{src.text[:3500]}")
            return self._sources([Source(src, found.text)])
        if action == "read_law":
            req = Law.model_validate(data)
            source = await self.finder.article(req.law, req.article)
            return self._sources([source] if source else [])
        if action == "search_law":
            query = Query.model_validate(data).query
            return self._sources(await self.finder.articles_for(query, limit=4))
        if action == "search_cases":
            query = Query.model_validate(data).query
            safe = public_query(query)
            return self._sources(await self.finder.decisions_for(safe, safe, self.usage, keep=3)
                                 if safe else [])
        if action == "search_web":
            if not self.web.enabled:
                return {"available": False, "next": "Yerel dizini veya mevcut E kaynağının "
                        "resmî belgesini read_web ile aç."}
            return await self.web.search(Query.model_validate(data).query)
        req = ReadWeb.model_validate(data)
        if req.id not in self.opened_public:
            if req.id.startswith("E"):
                source = self.ledger.get(req.id)
                if source is None or source.kind not in ("article", "decision", "official"):
                    raise ValueError("Kamu belgesi için önce bir hukuk kaynağı bulunmalı.")
                self.web.register_reference(req.id, source.url, source.citation)
            self.opened_public[req.id] = await self.web.read(req.id)
        url, title, body, digest = self.opened_public[req.id]
        if req.find:
            match = re.search(re.escape(req.find), body[req.offset:], re.IGNORECASE)
            if not match:
                return {"length": len(body), "matches": 0}
            offset = req.offset + match.start()
        else:
            offset = req.offset
        if offset >= len(body):
            raise ValueError("Kamu belgesi bu konuma kadar uzanmıyor.")
        begin = max(offset - 500, 0)
        end = min(offset + 6000, len(body))
        src = self.ledger.add_record(source_id=f"public:{url}:{digest}:{begin}:{end}",
                                     kind="official", citation=f"{title} ({begin}–{end})",
                                     url=url, text=body[begin:end])
        self.origins[src.key] = {"sha256": digest, "text_start": begin, "text_end": end}
        self.comparison.append(f"{src.key} {src.citation}\n{src.text[:3500]}")
        return {"length": len(body), "range": [begin, end], "source": self._sources([Source(src, src.text)])}

    async def _edits(self, items: list[EditSet], plan: Plan,
                     values: dict[str, Value]) -> tuple[list[dict], list[bytes]]:
        edits, copies = [], []
        for edit in items:
            if edit.file not in self.files or not self.files[edit.file].name.lower().endswith(".docx"):
                raise InvalidPlan("Düzenleme için bu sohbetteki bir Word belgesi gerekiyor.")
            file = self.files[edit.file]
            changes = []
            for change in edit.changes:
                if change.result not in plan.outputs or values[change.result].unit in (
                        "date", "number", "day"):
                    raise InvalidPlan("Word değişikliği doğrulanmış bir para sonucuna bağlanmalı.")
                amount = display(values[change.result])
                # Preserve the original's currency spelling and placement unless the edit
                # replaced a whole money figure.
                if change.before.endswith(" TRY") and amount.endswith(" TL"):
                    amount = amount.removesuffix(" TL") + " TRY"
                elif re.fullmatch(r"[-+\d., ]+", change.before):
                    amount = amount.split(" ", 1)[0]
                if not re.fullmatch(r"[-+\d., ]+(?:[A-Z]{2,3})?", change.before):
                    raise InvalidPlan("Word düzenlemesi mevcut tutar metniyle sınırlı.")
                changes.append({**change.model_dump(), "after": amount})
            copies.append(await asyncio.to_thread(word_copy, file, changes))
            edits.append({"source_file_id": str(file.id), "source_sha256": file.sha256,
                          "name": file.name, "changes": changes})
        return edits, copies

    def _outcome(self, plan: Plan | None, fmt: Format = "short", reason: str = "",
                 edits: list[dict] | None = None) -> Outcome:
        if plan is None:
            inspected = [source for source in self.ledger if source.key in self.inspected]
            text = f"**Doğrulama bekliyor.** {plain(reason)}"
            if inspected:
                audit = self.ledger.add_calculation(
                    source_id="workspace-checked", citation="İncelenen kaynaklar",
                    text="\n".join(source.citation for source in inspected))
                text += f" [[{audit.key}]]"
                inspected.append(audit)
            return Outcome(text, None, inspected)
        values = evaluate(plan)
        lines = ground(self.ledger, plan, values)
        cited = {p["ref"] for p in lines["inputs"].values()} | {
            p["ref"] for proofs in lines["rules"].values() for p in proofs}
        cited_sources = [source for source in self.ledger if source.key in cited]
        saved = plan.model_dump()
        prior = (self.context.previous or {}) if plan is self.previous or plan.updates_previous else {}
        number = int(prior.get("revision", 0)) + (plan is not self.previous)
        outputs = {step.key: step.label for step in plan.steps if step.key in plan.outputs}
        labels = {**outputs, **{item.key: item.label for item in plan.inputs}}
        previous_values = prior.get("values", {})
        changed = []
        for key, label in labels.items():
            old = previous_values.get(key)
            new = values[key]
            if old and old != {"value": new.dump(), "unit": new.unit}:
                changed.append({"label": label, "before": old["value"], "old_unit": old["unit"],
                                "after": new.dump(), "unit": new.unit})
        audit = [f"Hesap sürümü {number} · Motor {VERSION}"]
        audit.extend(f"{item.label} = {display(values[item.key])}\n"
                     f"{lines['inputs'][item.key]['citation']} · {lines['inputs'][item.key]['quote']}"
                     for item in plan.inputs)
        rules = {rule.key: rule for rule in plan.rules}
        for step in plan.steps:
            rule = rules[step.rule]
            audit.append(f"{step.label} = {step.operation}({', '.join(step.args)})"
                         f" → {display(values[step.key])}\n"
                         + (f"{rule.applies_on} · " if rule.applies_on else "")
                         + f"{rule.reasoning}\n"
                         + "\n".join(f"{p['citation']} · {p['quote']}"
                                     for p in lines["rules"][step.rule]))
        source = self.ledger.add_calculation(
            source_id="workspace-computation", citation="Hesap girdileri, işlemler ve dayanaklar",
            text="\n\n".join(audit))
        rows = [(plain(outputs[key]), display(values[key])) for key in plan.outputs]
        markers = " ".join(f"[[{item.key}]]" for item in [
            source, *[s for s in cited_sources if s.kind in ("article", "decision", "official")]])
        if fmt == "table":
            text = "| Kalem | Sonuç |\n| --- | ---: |\n" + "\n".join(
                f"| {label} | {value} |" for label, value in rows) + f"\n\n{markers}"
        else:
            text = " · ".join(f"{label}: **{value}**" for label, value in rows) + f" {markers}"
        if reason:
            text = f"**Doğrulama bekleyen kalem:** {plain(reason)}\n\n{text}"
        snapshot = {
            "engine": VERSION, "revision": number, "series": prior.get("series") or str(uuid.uuid4()),
            "plan": saved, "grounding": lines,
            "origins": {key: value for key, value in self.origins.items() if key in cited},
            "values": {key: {"value": value.dump(), "unit": value.unit}
                       for key, value in values.items()},
            "format": fmt, "changes": changed, "edits": edits or [], "pending": reason,
        }
        return Outcome(text, snapshot, [*cited_sources, source])

    async def run(self, question: str, history: list[dict]) -> Outcome:
        self._restore()
        statement = self.ledger.add_record(source_id=STATEMENT_KEY, kind="statement",
                                           citation="Bu sohbetteki kullanıcı beyanı", text=question)
        date_label = f"Türkiye saatiyle bugün: {datetime.now(ZoneInfo('Europe/Istanbul')).date()}"
        today = self.ledger.add_record(source_id="workspace-today", kind="clock",
                                       citation="Hesabın çalıştırıldığı tarih", text=date_label)
        actions = []
        context = {
            "message": question, "statement": statement.key,
            "today": {"ref": today.key, "text": today.text}, "history": history[-4:],
            "public_links": self.web.user_references(question),
            "files": [{"id": key, "name": f.name, "type": f.media_type}
                      for key, f in self.files.items()],
            "previous": self.previous.model_dump() if self.previous else None,
            "previous_pending": (self.context.previous or {}).get("pending", ""),
        }
        requests = set()
        for _ in range(MAX_TURNS):
            try:
                visible = []
                remaining = 125000
                for previous in reversed(actions):
                    remaining -= len(json.dumps(previous, ensure_ascii=False))
                    if remaining < 0:
                        break
                    visible.append(previous)
                choice = await structured("main", self.usage, "workspace_plan", prompt("workspace"),
                                          {**context, "actions": list(reversed(visible))},
                                          ACTION_SCHEMA, 10500)
                action = choice.get("action")
                if action not in ACTIONS:
                    raise ValueError("Geçersiz araç adı.")
                payload = json.loads(choice["payload"])
                if not isinstance(payload, dict):
                    raise TypeError("Araç girdisi nesne olmalı.")
                if action == "calculate":
                    candidate = Plan.model_validate(payload)
                    if candidate.updates_previous and self.previous is None:
                        raise InvalidPlan("Bu düzenlemeye bağlanabilecek bir önceki hesap yok.")
                    values = evaluate(candidate)
                    grounded = ground(self.ledger, candidate, values)
                    await review(self.usage, question, candidate, grounded, self.comparison[-6:],
                                 self.previous.title if self.previous else None)
                    self.current = candidate
                    result = {key: values[key].dump() for key in candidate.outputs}
                elif action == "finish":
                    finish = Finish.model_validate(payload)
                    plan = self.current or (self.previous if finish.reuse else None)
                    if plan is None:
                        raise InvalidPlan("Önce doğrulanmış bir hesap gerekiyor.")
                    if plan is self.previous:
                        accepted = await structured(
                            "judge", self.usage, "workspace_reuse", prompt("workspace_reuse"),
                            {"request": question, "previous": plan.title,
                             "previous_pending": (self.context.previous or {}).get("pending", "")},
                            schema({"approved": {"type": "boolean"}}), 2500)
                        if accepted.get("approved") is not True:
                            raise InvalidPlan("Bu istek için önceki hesap yeniden kullanılmadan önce "
                                              "yeni bilgi değerlendirilmeli.")
                    pending = ((self.context.previous or {}).get("pending", "")
                               if plan is self.previous else "")
                    if pending and finish.edits:
                        raise InvalidPlan("Tamamlanmamış hesapla Word belgesi güncellenemez.")
                    edits, copies = await self._edits(finish.edits, plan, evaluate(plan))
                    if edits:
                        accepted = await structured(
                            "judge", self.usage, "workspace_edit", prompt("workspace_edit"),
                            {"request": question, "previous_requests": [
                                msg["content"] for msg in history[-4:] if msg["role"] == "user"],
                             "changes": edits},
                            schema({"approved": {"type": "boolean"}}), 2500)
                        if accepted.get("approved") is not True:
                            raise InvalidPlan("İstenen Word düzenlemesinin kapsamı doğrulanamadı.")
                    outcome = self._outcome(plan, finish.format, pending, edits)
                    outcome.files = copies
                    return outcome
                elif action == "blocked":
                    blocked = Blocked.model_validate(payload)
                    return self._outcome(self.current, blocked.format, blocked.message())
                else:
                    signature = (action, json.dumps(payload, sort_keys=True, ensure_ascii=False))
                    if signature in requests:
                        raise ValueError("Bu araç aynı girdiyle denendi. Önceki sonucu kullan "
                                         "veya farklı bir kaynak ara.")
                    requests.add(signature)
                    result = await self.lookup(action, payload)
                actions.append({"action": action, "result": result})
            except (ValueError, TypeError, KeyError, OSError, SourceError, zipfile.BadZipFile) as exc:
                if isinstance(exc, ValidationError):
                    issue = "; ".join(".".join(map(str, item["loc"])) + " " + item["msg"]
                                      for item in exc.errors(include_input=False)[:4])
                elif isinstance(exc, (OSError, KeyError, TypeError)):
                    issue = "Araç girdisi veya kaynak okunamadı."
                else:
                    issue = str(exc)[:1000]
                actions.append({"error": issue})
        return self._outcome(self.current, reason="Hesap akışı işlem sınırına ulaştı.")
