"""FastAPI application factory."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from legal_api.api import (
    admin,
    auth,
    calendar,
    chats,
    deadline_calc,
    drafting,
    files,
    folders,
    health,
    matters,
    reports,
    search,
    settings,
)
from legal_api.config import get_settings
from legal_api.db.file_models import StoredFile
from legal_api.db.session import get_sessionmaker
from legal_api.embeddings import embed_query
from legal_api.privacy.file_crypto import FileProtectionError
from legal_api.privacy.policy import validate


@asynccontextmanager
async def lifespan(_: FastAPI):
    config = get_settings()
    if config.protected_data:
        async with get_sessionmaker()() as session:
            legacy = await session.scalar(select(StoredFile.id)
                                          .where(StoredFile.encrypted.is_(False)).limit(1))
        if legacy is not None:
            raise RuntimeError("run legal_api.files.encrypt before enabling protected mode")
        if any(path.is_file() for path in (config.storage_dir / "users").glob("*/*/*")):
            raise RuntimeError("reconcile remaining legacy files before enabling protected mode")
    # Load the embedding model in the background so the first question doesn't pay ~7 s.
    warmup = asyncio.create_task(asyncio.to_thread(embed_query, "warmup"))
    yield
    warmup.cancel()


def create_app() -> FastAPI:
    config = get_settings()
    validate(config)
    app = FastAPI(title=config.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.web_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, auth, admin, calendar, chats, deadline_calc, drafting, files,
                   folders, matters, reports, search, settings):
        app.include_router(module.router)

    @app.exception_handler(FileProtectionError)
    async def file_unavailable(_request: Request, _error: FileProtectionError):
        return JSONResponse({"detail": "file temporarily unavailable"}, status_code=503)

    if config.protected_data:
        @app.middleware("http")
        async def private_responses(request: Request, call_next):
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "same-origin"
            return response
    return app


app = create_app()
