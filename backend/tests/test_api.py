import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import os

# Point to a temp DB for tests
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("LLM_API_KEYS", "fake_key_1,fake_key_2")
os.environ.setdefault("ENABLE_FAILURE_SIMULATION", "true")

from app.main import app


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] == 2
    assert data["cache_enabled"] is True


@pytest.mark.anyio
async def test_chat_missing_session(client):
    r = await client.post("/chat", json={"message": "hello"})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_chat_empty_message(client):
    r = await client.post("/chat", json={"session_id": "test-s1", "message": "   "})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_session_not_found(client):
    r = await client.get("/sessions/nonexistent-999/messages")
    assert r.status_code == 404
    assert r.json()["detail"] == "session not found"


@pytest.mark.anyio
async def test_simulate_all_keys_fail(client):
    r = await client.post(
        "/chat",
        json={"session_id": "sim-test", "message": "hello"},
        headers={"X-Simulate-Failure": "*=429"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "all providers unavailable"
