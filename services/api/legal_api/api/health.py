"""Liveness and dependency checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.config import get_settings
from legal_api.corpus.statutes import CORE_LAWS
from legal_api.db.session import get_session
from legal_api.db.statute_models import StatuteArticle

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    db_ok = True
    vector_ok = False
    try:
        await session.execute(text("SELECT 1"))
        result = await session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        vector_ok = result.scalar() is not None
    except (SQLAlchemyError, OSError):
        db_ok = False
    return {
        "app": get_settings().app_name,
        "status": "ok" if db_ok and vector_ok else "degraded",
        "database": db_ok,
        "pgvector": vector_ok,
    }


@router.get("/ready")
async def ready(response: Response, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    checks = await health(session)
    missing = list(CORE_LAWS)
    if checks["status"] == "ok":
        try:
            indexed = set(await session.scalars(select(StatuteArticle.law_number)
                                                .where(StatuteArticle.law_number.in_(CORE_LAWS))
                                                .distinct()))
            missing = [number for number in CORE_LAWS if number not in indexed]
        except (SQLAlchemyError, OSError):
            pass
    if missing:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {**checks, "status": "degraded" if missing else "ok", "missing_core_laws": missing}
