"""FastAPI application factory."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from legal_api.api import auth, chats, health, search
from legal_api.config import get_settings
from legal_api.embeddings import embed_query


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the embedding model in the background so the first question doesn't pay ~7 s.
    warmup = asyncio.create_task(asyncio.to_thread(embed_query, "warmup"))
    yield
    warmup.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, auth, chats, search):
        app.include_router(module.router)
    return app


app = create_app()
