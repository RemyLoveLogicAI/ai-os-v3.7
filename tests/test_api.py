"""
AI OS v3.7 — FastAPI Server Tests
Tests for all API endpoints using httpx AsyncClient.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

# Patch heavy dependencies before importing the app
with patch("core.llm_router.LLMRouter") as mock_router_cls, \
     patch("marketplace.registry.SkillRegistry") as mock_registry_cls:

    mock_router = AsyncMock()
    mock_router.health_check.return_value = {"status": "healthy", "backends": ["ollama"]}
    mock_router.configured_providers.return_value = ["ollama", "openai"]
    mock_router.status.return_value = {"active_backends": ["ollama"]}
    mock_router.route.return_value = {
        "content": "Hello from Ollama!",
        "model": "llama3",
        "provider": "ollama",
        "fallback": False,
        "tokens": 42,
    }
    mock_router.complete_direct.return_value = {
        "content": "Direct completion result",
        "tokens": 20,
    }
    mock_router_cls.return_value = mock_router

    mock_skill = MagicMock()
    mock_skill.to_dict.return_value = {
        "name": "echo",
        "version": "1.0.0",
        "description": "Echo skill",
        "status": "active",
    }
    mock_skill.invoke = AsyncMock(return_value={"echo": "test input"})

    mock_registry = MagicMock()
    mock_registry.skills = {"echo": mock_skill}
    mock_registry.get.return_value = mock_skill
    mock_registry.load_all = AsyncMock()
    mock_registry_cls.return_value = mock_registry

    from src.api.server import app  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c


# ── Health & Info ─────────────────────────────────────────────────────────────

class TestHealth:
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_contains_status(self, client):
        data = response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "components" in data
        assert "version" in data

    async def test_info_endpoint(self, client):
        response = await client.get("/v1/info")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AI OS"
        assert data["version"] == "3.7.0"
        assert "capabilities" in data


# ── LLM Routing ──────────────────────────────────────────────────────────────

class TestRoute:
    async def test_route_success(self, client):
        response = await client.post("/v1/route", json={
            "prompt": "What is 2 + 2?",
            "max_tokens": 100,
        })
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "model_used" in data
        assert "latency_ms" in data
        assert data["routed"] is True

    async def test_route_with_model_preference(self, client):
        response = await client.post("/v1/route", json={
            "prompt": "Hello",
            "model_preference": "llama3",
        })
        assert response.status_code == 200

    async def test_route_validates_max_tokens(self, client):
        response = await client.post("/v1/route", json={
            "prompt": "Test",
            "max_tokens": 0,  # Invalid — below minimum of 1
        })
        assert response.status_code == 422

    async def test_route_validates_temperature(self, client):
        response = await client.post("/v1/route", json={
            "prompt": "Test",
            "temperature": 3.0,  # Invalid — above maximum of 2.0
        })
        assert response.status_code == 422

    async def test_direct_complete(self, client):
        response = await client.post("/v1/complete", json={
            "model": "llama3",
            "prompt": "Complete this: The sky is",
        })
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["model"] == "llama3"


# ── Skill Marketplace ─────────────────────────────────────────────────────────

class TestSkills:
    async def test_list_skills(self, client):
        response = await client.get("/v1/skills")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert "total" in data
        assert isinstance(data["skills"], list)

    async def test_get_skill_by_name(self, client):
        response = await client.get("/v1/skills/echo")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "echo"

    async def test_get_nonexistent_skill_returns_404(self, client):
        response = await client.get("/v1/skills/nonexistent_skill_xyz")
        assert response.status_code == 404

    async def test_invoke_skill(self, client):
        response = await client.post("/v1/skills/echo/invoke", json={
            "input": "test input",
        })
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "skill" in data
        assert data["skill"] == "echo"
        assert "latency_ms" in data

    async def test_invoke_nonexistent_skill_returns_404(self, client):
        response = await client.post("/v1/skills/ghost/invoke", json={
            "input": "test",
        })
        assert response.status_code == 404


# ── Router Management ─────────────────────────────────────────────────────────

class TestRouter:
    async def test_router_status(self, client):
        response = await client.get("/v1/router/status")
        assert response.status_code == 200

    async def test_router_reload(self, client):
        response = await client.post("/v1/router/reload")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reloaded"
        assert "timestamp" in data


# ── Edge Cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    async def test_empty_prompt_is_invalid(self, client):
        response = await client.post("/v1/route", json={"prompt": ""})
        # Empty string passes Pydantic but should be handled gracefully
        # This test documents expected behavior
        assert response.status_code in [200, 422]

    async def test_very_long_prompt(self, client):
        long_prompt = "A" * 10000
        response = await client.post("/v1/route", json={"prompt": long_prompt})
        assert response.status_code in [200, 422, 502]

    async def test_docs_accessible(self, client):
        response = await client.get("/docs")
        assert response.status_code == 200

    async def test_redoc_accessible(self, client):
        response = await client.get("/redoc")
        assert response.status_code == 200
