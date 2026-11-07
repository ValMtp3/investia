"""Test de la route GET /health."""

import httpx

from investia.main import create_app

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "LITELLM_BASE_URL": "http://localhost:4000",
    "LITELLM_MASTER_KEY": "sk-test",
    "APP_SECRET_KEY": "test-admin-secret-0123456789abcdef",
}


async def test_health_returns_200_ok(monkeypatch):
    for var, value in REQUIRED_ENV.items():
        monkeypatch.setenv(var, value)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
