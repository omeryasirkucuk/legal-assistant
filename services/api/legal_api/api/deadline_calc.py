"""The last day of a period from a notice, for the lawyer adding a deadline to a file."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from legal_api.auth import CurrentUser
from legal_api.calc.deadlines import Unit
from legal_api.calc.notice import Branch, Service, from_notice

router = APIRouter(tags=["deadlines"])


class NoticeIn(BaseModel):
    received: date
    service: Service
    amount: int = Field(ge=1, le=3650)
    unit: Unit
    branch: Branch


class Step(BaseModel):
    code: str
    values: dict


class NoticeOut(BaseModel):
    received: date
    served: date
    due: date
    law: str
    steps: list[Step]
    warnings: list[Step]
    notes: list[str]


@router.post("/deadlines/calculate")
async def calculate(body: NoticeIn, user: CurrentUser) -> NoticeOut:
    r = from_notice(body.received, body.service, body.amount, body.unit, body.branch)
    step = lambda pairs: [Step(code=c, values={k: str(v) for k, v in vals.items()}) for c, vals in pairs]
    return NoticeOut(received=r.received, served=r.served, due=r.deadline.end, law=r.law,
                     steps=step(r.deadline.steps), warnings=step(r.deadline.warnings), notes=r.notes)
