"""Bind arithmetic to exact source excerpts and independently review applicability."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any

from legal_api import llm
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.grounding.numbers import numbers_in
from legal_api.prompts import prompt
from legal_api.workspace.engine import InvalidPlan, Passage, Plan, Value

NUMBER = re.compile(r"(?<![\d.,])-?\d+(?:[.,]\d+)*(?![\d.,])")
DATES = re.compile(r"\b(?:\d{4}-\d\d-\d\d|\d{1,2}[./-]\d{1,2}[./-]\d{4})\b")
PERCENT_WORD = re.compile(r"\byüzde\s+(bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz)\w*")
PERCENT_UNITS = {name: n for n, name in enumerate(
    ("bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"), 1)}
STATEMENT_KEY = "current-statement"


def normal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _stated_amount(value: Decimal, quote: str) -> bool:
    amounts = set()
    for token in NUMBER.findall(DATES.sub(" ", quote)):
        if "," in token:
            token = token.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", token):
            token = token.replace(".", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            amounts.add(Decimal(token))
    if value in amounts or any(value == PERCENT_UNITS[word]
                               for word in PERCENT_WORD.findall(quote.lower())):
        return True
    # The common number-word parser is also used by existing citation verification.
    words = NUMBER.sub(" ", quote)
    return any(value == Decimal(str(number)) for number in numbers_in(words))


def _stated_date(value: date, quote: str) -> bool:
    for token in DATES.findall(quote):
        parts = re.split(r"[./-]", token)
        try:
            if len(parts[0]) == 4 and date(*(int(part) for part in parts)) == value:
                return True
            if len(parts[0]) < 4 and date(*(int(part) for part in reversed(parts))) == value:
                return True
        except ValueError:
            continue
    return False


def _passage(ledger: EvidenceLedger, passage: Passage) -> dict:
    source = ledger.get(passage.ref)
    quote = normal(passage.quote)
    if source is None or quote not in normal(source.text):
        raise InvalidPlan(f"{passage.ref}: kaynakta birebir geçen bir pasaj gerekiyor.")
    return {"ref": source.key, "kind": source.kind, "citation": source.citation,
            "url": source.url, "quote": quote, "fetched_at": source.fetched_at.isoformat()}


def ground(ledger: EvidenceLedger, plan: Plan, values: dict[str, Value]) -> dict:
    evidence = {}
    for item in plan.inputs:
        proof = _passage(ledger, item.passage)
        value = values[item.key].data
        if proof["kind"] == "calculation":
            raise InvalidPlan(f"{item.key}: ilk belge, beyan veya hukuk kaynağı gerekiyor.")
        stated = (_stated_date(value, proof["quote"]) if isinstance(value, date)
                  else _stated_amount(value, proof["quote"]))
        if not stated:
            raise InvalidPlan(f"{item.key}: girdi değeri alıntılanan yerde doğrulanamadı.")
        evidence[item.key] = proof
    applicable = {}
    case_dates = {v.dump() for k, v in values.items() if k in evidence and v.unit == "date"}
    for rule in plan.rules:
        proofs = [_passage(ledger, passage) for passage in rule.passages]
        if rule.kind == "arithmetic":
            if not any(p["kind"] == "statement" for p in proofs):
                raise InvalidPlan(f"{rule.key}: kullanıcının salt aritmetik talebi gerekiyor.")
        else:
            if not any(p["kind"] in ("article", "decision", "official", "case_file") for p in proofs):
                raise InvalidPlan(f"{rule.key}: mevzuat, karar veya sözleşme hükmü gerekiyor.")
            observed = date.fromisoformat(rule.applies_on)
            dated_passage = any(p["kind"] in ("case_file", "statement", "clock")
                                and _stated_date(observed, p["quote"]) for p in proofs)
            if rule.applies_on not in case_dates and not dated_passage:
                raise InvalidPlan(f"{rule.key}: uygulanma tarihi doğrulanmış girdi veya "
                                  "ilgili belge pasajı olmalı.")
        applicable[rule.key] = proofs
    return {"inputs": evidence, "rules": applicable}


def schema(properties: dict[str, dict]) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


async def structured(role, usage: llm.Usage, purpose: str, system: str, data: dict,
                     output: dict, max_tokens: int) -> dict[str, Any]:
    message = await llm.create(
        role, usage, purpose, system=system, max_tokens=max_tokens,
        messages=[{"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": output}},
    )
    text = next((block.text for block in message.content if block.type == "text" and block.text.strip()), "")
    if not text:
        raise ValueError("Model bu araç çağrısı için doğrulanabilir bir yanıt vermedi.")
    body = json.loads(text)
    if not isinstance(body, dict):
        raise TypeError("Beklenen araç yanıtı alınamadı.")
    return body


async def review(usage: llm.Usage, question: str, plan: Plan, grounding: dict,
                 notes: list[str], previous_title: str | None) -> None:
    data = {"request": question, "plan": plan.model_dump(), "passages": grounding,
            "comparison_context": notes, "previous_plan": previous_title}
    verdict = await structured("judge", usage, "workspace_verify", prompt("workspace_verify"),
                               data, schema({"approved": {"type": "boolean"},
                                             "reason": {"type": "string"}}), 3500)
    if verdict.get("approved") is not True:
        reason = verdict.get("reason")
        raise InvalidPlan((reason if isinstance(reason, str) else
                           "Hesap ve kaynak ilişkisi doğrulanamadı.")[:700])
