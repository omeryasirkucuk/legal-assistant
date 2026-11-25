"""Versioned, declarative arithmetic. Model output is data, never executable code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = 1
MAX_VALUE = Decimal(10000000000000)
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Label = Annotated[str, Field(min_length=1, max_length=180)]
Unit = Annotated[str, Field(pattern=r"^(number|date|day|[A-Z]{3})$")]
Operation = Literal[
    "sum", "subtract", "multiply", "divide", "minimum", "maximum",
    "days_between", "add_days", "round_money", "percent", "if_ge",
]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Passage(Record):
    ref: str = Field(pattern=r"^E[1-9][0-9]{0,2}$")
    quote: str = Field(min_length=3, max_length=2600)


class Input(Record):
    key: Key
    label: Label
    unit: Unit
    value: str = Field(min_length=1, max_length=40)
    passage: Passage
    meaning: str = Field(min_length=3, max_length=500)


class Rule(Record):
    key: Key
    passages: list[Passage] = Field(min_length=1, max_length=6)
    applies_on: str = Field(pattern=r"^(?:\d{4}-\d{2}-\d{2})?$")
    kind: Literal["legal", "arithmetic"] = "legal"
    reasoning: str = Field(min_length=8, max_length=1200)


class Step(Record):
    key: Key
    label: Label
    operation: Operation
    args: list[Key] = Field(min_length=1, max_length=50)
    rule: Key


class Plan(Record):
    updates_previous: bool = False
    title: Label
    inputs: list[Input] = Field(min_length=1, max_length=80)
    rules: list[Rule] = Field(min_length=1, max_length=15)
    steps: list[Step] = Field(min_length=1, max_length=120)
    outputs: list[Key] = Field(min_length=1, max_length=20)


class InvalidPlan(ValueError):
    pass


@dataclass(frozen=True)
class Value:
    data: Decimal | date
    unit: str

    def dump(self) -> str:
        if isinstance(self.data, date):
            return self.data.isoformat()
        return format(self.data, "f")


def parse_input(item: Input) -> Value:
    try:
        if item.unit == "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.value):
                raise ValueError
            return Value(date.fromisoformat(item.value), item.unit)
        if not re.fullmatch(r"-?\d{1,14}(?:\.\d{1,10})?", item.value):
            raise ValueError
        return _bound(Value(Decimal(item.value), item.unit))
    except (ValueError, DecimalException) as exc:
        raise InvalidPlan(f"{item.key}: geçersiz değer") from exc


def _bound(value: Value) -> Value:
    if isinstance(value.data, Decimal) and abs(value.data) > MAX_VALUE:
        raise InvalidPlan("Değer hesap motorunun desteklediği aralığın dışında.")
    return value


def _same(args: list[Value]) -> str:
    unit = args[0].unit
    if any(arg.unit != unit for arg in args[1:]):
        raise InvalidPlan("İşlemde birimler uyuşmuyor.")
    return unit


def _arity(op: str, args: list[Value], count: int) -> None:
    if len(args) != count:
        raise InvalidPlan(f"{op}: {count} girdi gerekiyor.")


def _calculate(op: Operation, args: list[Value]) -> Value:
    if op == "if_ge":
        _arity(op, args, 4)
        _same(args[:2])
        _same(args[2:])
        return args[2] if args[0].data >= args[1].data else args[3]
    if op in ("days_between", "add_days"):
        _arity(op, args, 2)
        first, second = (arg.data for arg in args)
        if not isinstance(first, date):
            raise InvalidPlan("İşlemin ilk girdisi tarih olmalı.")
        if op == "days_between" and isinstance(second, date):
            return Value(Decimal((second - first).days), "day")
        if op == "add_days" and args[1].unit == "day" and second == int(second):
            return Value(first + timedelta(days=int(second)), "date")
        raise InvalidPlan("Tarih işleminin ikinci girdisi geçersiz.")
    values = [arg.data for arg in args]
    if any(not isinstance(value, Decimal) for value in values):
        raise InvalidPlan("İşlem sayısal değer gerektiriyor.")
    if op == "sum":
        return Value(sum(values, Decimal(0)), _same(args))
    if op in ("minimum", "maximum"):
        return Value((min if op == "minimum" else max)(values), _same(args))
    if op == "round_money":
        _arity(op, args, 1)
        if args[0].unit in ("number", "day"):
            raise InvalidPlan("Para yuvarlama işlemi para birimi gerektiriyor.")
        return Value(values[0].quantize(Decimal("0.01"), ROUND_HALF_UP), args[0].unit)
    if op == "percent":
        _arity(op, args, 1)
        if args[0].unit != "number":
            raise InvalidPlan("Yüzde işlemi birimsiz sayı gerektiriyor.")
        return Value(values[0] / 100, "number")
    _arity(op, args, 2)
    left, right = values
    a, b = (arg.unit for arg in args)
    if op == "subtract":
        return Value(left - right, _same(args))
    if op == "multiply" and "number" in (a, b):
        return Value(left * right, b if a == "number" else a)
    if op == "divide" and (a == b or b == "number"):
        if not right:
            raise InvalidPlan("Sıfıra bölme.")
        return Value(left / right, "number" if a == b else a)
    raise InvalidPlan(f"{op}: birimler uyuşmuyor.")


def evaluate(plan: Plan) -> dict[str, Value]:
    values: dict[str, Value] = {}
    rules = {rule.key for rule in plan.rules}
    if len(rules) != len(plan.rules):
        raise InvalidPlan("Birden fazla kural aynı kimliği kullanıyor.")
    for rule in plan.rules:
        if rule.kind == "arithmetic" and not rule.applies_on:
            continue
        try:
            date.fromisoformat(rule.applies_on)
        except ValueError as exc:
            raise InvalidPlan(f"{rule.key}: uygulanma tarihi geçersiz.") from exc
    for item in plan.inputs:
        if item.key in values:
            raise InvalidPlan(f"{item.key}: girdi kimliği yinelenmiş.")
        values[item.key] = parse_input(item)
    with localcontext() as context:
        context.prec = 32
        for step in plan.steps:
            if step.rule not in rules or step.key in values or any(k not in values for k in step.args):
                raise InvalidPlan(f"{step.key}: adımın bağımlılığı, kuralı veya kimliği geçersiz.")
            try:
                values[step.key] = _bound(_calculate(step.operation, [values[k] for k in step.args]))
            except (DecimalException, OverflowError) as exc:
                raise InvalidPlan(f"{step.key}: sonuç desteklenen aralığın dışında.") from exc
    step_keys = {step.key for step in plan.steps}
    if len(set(plan.outputs)) != len(plan.outputs) or any(k not in step_keys for k in plan.outputs):
        raise InvalidPlan("Sonuçlar farklı hesap adımlarına bağlanmalı.")
    for key in plan.outputs:
        value = values[key]
        if value.unit not in ("number", "date", "day") and value.data != value.data.quantize(
                Decimal("0.01"), ROUND_HALF_UP):
            raise InvalidPlan(f"{key}: parasal sonuçta kullanılacak yuvarlama adımını belirt.")
    return values
