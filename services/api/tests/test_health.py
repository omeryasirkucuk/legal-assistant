from httpx import ASGITransport, AsyncClient

from legal_api.main import create_app


async def test_health_reports_database_and_pgvector():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        response = await c.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert body["pgvector"] is True
    assert body["status"] == "ok"
