"""Registration setup for integration tests outside the invitation flow."""

import secrets
import uuid
from hashlib import sha256

from httpx import AsyncClient
from sqlalchemy import delete, select

from legal_api.db.app_models import RegistrationInvite, User
from legal_api.db.session import get_sessionmaker


async def register_invited(client: AsyncClient, email: str, name: str, password: str = "secret-pass"):
    code = secrets.token_urlsafe(32)
    digest = sha256(code.encode()).hexdigest()
    bootstrap_admin = None
    async with get_sessionmaker()() as db:
        if await db.scalar(select(User.id).limit(1)) is None:
            bootstrap_admin = uuid.uuid4()
            db.add(User(id=bootstrap_admin, email=f"{bootstrap_admin}@example.com",
                        name="Test bootstrap administrator", password_hash="", is_admin=True))
        db.add(RegistrationInvite(code_hash=digest, email=email.lower()))
        await db.commit()
    try:
        response = await client.post("/auth/register", json={
            "email": email, "name": name, "password": password, "invite_code": code,
        })
        assert response.status_code == 201, response.text
        return response
    finally:
        async with get_sessionmaker()() as db:
            await db.execute(delete(RegistrationInvite).where(RegistrationInvite.code_hash == digest))
            if bootstrap_admin is not None:
                await db.execute(delete(User).where(User.id == bootstrap_admin))
            await db.commit()
