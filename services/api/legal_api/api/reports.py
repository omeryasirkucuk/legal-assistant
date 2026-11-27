"""Submit feedback and review only the conversation shared with each report."""

import asyncio
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select

from legal_api.auth import DB, CurrentUser, require_admin
from legal_api.db.app_models import Chat, Message, ProblemReport, User
from legal_api.db.file_models import StoredFile
from legal_api.files import store

router = APIRouter(tags=["reports"])


class ReportInput(BaseModel):
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    chat_id: uuid.UUID | None = None


@router.post("/reports", status_code=201)
async def submit(body: ReportInput, user: CurrentUser, db: DB):
    context = {"chat_id": None, "title": "", "messages": [], "files": []}
    if body.chat_id is not None:
        chat = await db.scalar(select(Chat).where(Chat.id == body.chat_id, Chat.user_id == user.id))
        if chat is None:
            raise HTTPException(404, "chat not found")
        messages = await db.execute(select(Message.role, Message.content).where(
            Message.chat_id == chat.id).order_by(Message.created_at, Message.id))
        files = await db.execute(select(StoredFile.id, StoredFile.name, StoredFile.text).where(
            StoredFile.chat_id == chat.id, StoredFile.user_id == user.id).order_by(StoredFile.created_at))
        context = {
            "chat_id": str(chat.id), "title": chat.title,
            "messages": [dict(row) for row in messages.mappings()],
            "files": [{"id": str(f.id), "name": f.name, "text": f.text} for f in files],
        }
    report = ProblemReport(user_id=user.id, description=body.description, context=context)
    db.add(report)
    await db.commit()
    return {"id": report.id}


@router.get("/admin/reports")
async def reports(user: CurrentUser, db: DB, response: Response):
    require_admin(user)
    response.headers["Cache-Control"] = "no-store"
    rows = await db.execute(select(ProblemReport.id, ProblemReport.created_at, User.email,
                                   ProblemReport.description).join(User)
                            .order_by(ProblemReport.created_at.desc(), ProblemReport.id))
    return rows.mappings().all()


@router.get("/admin/reports/{report_id}")
async def detail(report_id: uuid.UUID, user: CurrentUser, db: DB, response: Response):
    require_admin(user)
    response.headers["Cache-Control"] = "no-store"
    report = await db.get(ProblemReport, report_id)
    if report is None:
        raise HTTPException(404, "report not found")
    return report.context


@router.get("/admin/reports/{report_id}/files/{file_id}")
async def download(report_id: uuid.UUID, file_id: uuid.UUID, user: CurrentUser, db: DB):
    require_admin(user)
    report = await db.get(ProblemReport, report_id)
    if report is None or not any(f["id"] == str(file_id) for f in report.context["files"]):
        raise HTTPException(404, "file not found")
    file = await db.get(StoredFile, file_id)
    if file is None or file.user_id != report.user_id:
        raise HTTPException(404, "file not found")
    return Response(await asyncio.to_thread(store.read, file), media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.name, safe='')}"})
