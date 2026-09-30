"""Health endpoint logic: per-component status, 503 when required infra is down."""

import pytest

from opentrading_mcp import health


def test_overall_healthy_when_all_components_ok():
    code, body = health.overall_status(
        [
            {"name": "redis", "ok": True, "detail": "pong 1ms"},
            {"name": "postgres", "ok": True, "detail": "select 1"},
        ]
    )
    assert code == 200
    assert body["ok"] is True
    assert body["components"][0]["name"] == "redis"


def test_overall_503_when_required_component_down():
    code, body = health.overall_status(
        [
            {"name": "redis", "ok": False, "detail": "connection refused", "required": True},
            {"name": "postgres", "ok": True, "detail": "select 1"},
        ]
    )
    assert code == 503
    assert body["ok"] is False


def test_overall_200_when_only_optional_component_down():
    code, body = health.overall_status(
        [
            {"name": "redis", "ok": True, "detail": "pong"},
            {"name": "worker", "ok": False, "detail": "no heartbeat", "required": False},
        ]
    )
    assert code == 200
    assert body["ok"] is True


async def test_health_report_structure(monkeypatch):
    async def fake_redis():
        return {"name": "redis", "ok": True, "detail": "pong", "required": True}

    async def fake_postgres():
        return {"name": "postgres", "ok": True, "detail": "select 1", "required": True}

    async def fake_worker():
        return {"name": "worker", "ok": True, "detail": "heartbeat 12s ago", "required": False}

    monkeypatch.setattr(health, "component_redis", fake_redis)
    monkeypatch.setattr(health, "component_postgres", fake_postgres)
    monkeypatch.setattr(health, "component_worker", fake_worker)
    code, body = await health.health_report(deep=False)
    assert code == 200
    assert body["server"] == "opentrading"
    assert len(body["components"]) == 3


async def test_health_report_503_without_redis(monkeypatch):
    async def fake_redis():
        return {"name": "redis", "ok": False, "detail": "unreachable", "required": True}

    async def fake_postgres():
        return {"name": "postgres", "ok": True, "detail": "select 1", "required": True}

    async def fake_worker():
        return {"name": "worker", "ok": False, "detail": "unknown", "required": False}

    monkeypatch.setattr(health, "component_redis", fake_redis)
    monkeypatch.setattr(health, "component_postgres", fake_postgres)
    monkeypatch.setattr(health, "component_worker", fake_worker)
    code, body = await health.health_report(deep=False)
    assert code == 503
    assert body["ok"] is False


def test_redis_component_skipped_when_unconfigured(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    import asyncio

    result = asyncio.run(health.component_redis())
    assert result["ok"] is True
    assert result["required"] is False


def test_postgres_component_skipped_when_unconfigured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import asyncio

    result = asyncio.run(health.component_postgres())
    assert result["ok"] is True
    assert result["required"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
