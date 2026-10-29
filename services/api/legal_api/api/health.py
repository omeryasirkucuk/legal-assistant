"""Liveness and dependency checks."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.config import get_settings
from legal_api.db.session import get_session

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
