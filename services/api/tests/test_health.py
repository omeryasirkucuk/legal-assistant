import pytest
from httpx import ASGITransport, AsyncClient

from legal_api.api.health import CORE_LAWS
from legal_api.db.session import get_session
from legal_api.main import create_app


async def test_health_reports_database_and_pgvector():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        response = await c.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert body["pgvector"] is True
    assert body["status"] == "ok"


@pytest.mark.parametrize("indexed", [[], CORE_LAWS])
async def test_research_readiness_reports_missing_core_laws(indexed):
    class Database:
        async def execute(self, _statement):
            return self

        def scalar(self):
            return 1

        async def scalars(self, _statement):
            return indexed

    app = create_app()
    app.dependency_overrides[get_session] = Database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/ready")
    assert response.status_code == (200 if indexed else 503)
    assert response.json()["missing_core_laws"] == [law for law in CORE_LAWS if law not in indexed]
