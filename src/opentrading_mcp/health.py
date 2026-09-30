"""Liveness checks with per-component breakdown.

Default (shallow) checks only local infra reachability + worker freshness
read from Redis — no upstream network calls, safe to run every 10s.
``?deep=1`` additionally probes one cheap call per upstream family.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any


def overall_status(components: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    failed = [c["name"] for c in components if not c.get("ok", False) and c.get("required", True)]
    ok = not failed
    body: dict[str, Any] = {
        "ok": ok,
        "server": "opentrading",
        "components": components,
    }
    if failed:
        body["failed"] = failed
    return (200 if ok else 503), body


def _skipped(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "ok": True, "detail": f"skipped: {reason}", "required": False}


async def component_redis() -> dict[str, Any]:
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return _skipped("redis", "REDIS_URL unset")
    try:
        from opentrading_mcp.providers.store import _redis

        client = await asyncio.to_thread(_redis)
        if client is None:
            return {"name": "redis", "ok": False, "detail": "client init failed", "required": True}
        started = time.monotonic()
        await asyncio.to_thread(client.ping)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {"name": "redis", "ok": True, "detail": f"pong {elapsed_ms}ms", "required": True}
    except Exception as exc:
        return {"name": "redis", "ok": False, "detail": str(exc)[:200], "required": True}


async def component_postgres() -> dict[str, Any]:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return _skipped("postgres", "DATABASE_URL unset")
    try:
        import psycopg

        def _probe() -> None:
            conn = psycopg.connect(url, connect_timeout=5)
            try:
                conn.execute("SELECT 1").fetchall()
            finally:
                conn.close()

        await asyncio.to_thread(_probe)
        return {"name": "postgres", "ok": True, "detail": "select 1", "required": True}
    except Exception as exc:
        return {"name": "postgres", "ok": False, "detail": str(exc)[:200], "required": True}


async def component_worker() -> dict[str, Any]:
    try:
        from opentrading_mcp.providers.store import cache_get
    except Exception as exc:
        return {"name": "worker", "ok": False, "detail": str(exc)[:200], "required": False}
    try:
        raw = await asyncio.to_thread(cache_get, "mcp:health:worker")
    except Exception as exc:
        return {"name": "worker", "ok": False, "detail": str(exc)[:200], "required": False}
    if not raw:
        return {"name": "worker", "ok": False, "detail": "no heartbeat", "required": False}
    try:
        import json

        age = int(time.time() - float(json.loads(raw).get("ts", 0)))
    except (ValueError, TypeError, AttributeError):
        return {"name": "worker", "ok": False, "detail": "bad heartbeat payload", "required": False}
    if age > 120:
        return {
            "name": "worker",
            "ok": False,
            "detail": f"heartbeat {age}s ago",
            "required": False,
        }
    return {"name": "worker", "ok": True, "detail": f"heartbeat {age}s ago", "required": False}


async def deep_probes() -> list[dict[str, Any]]:
    """One cheap live call per upstream family; failures are non-fatal details."""

    def _probe_dnse() -> dict[str, Any]:
        from opentrading_mcp.providers import dnse as dnse_p

        rows = dnse_p.ohlc_history("VN30F1M", bar_type="derivative", resolution=15, page_size=2)
        return {"name": "dnse", "ok": bool(rows), "detail": f"{len(rows)} bars", "required": False}

    def _probe_vietstock() -> dict[str, Any]:
        from opentrading_mcp.providers import vietstock as vs_p

        status = vs_p.auth_status()
        ok = bool(status.get("authenticated"))
        return {
            "name": "vietstock",
            "ok": ok,
            "detail": "jwt ok" if ok else "not authenticated",
            "required": False,
        }

    def _probe_yfinance() -> dict[str, Any]:
        from opentrading_mcp.providers import yfinance as yf_p

        rows = yf_p.batch_last(["^GSPC"])
        return {
            "name": "yfinance",
            "ok": bool(rows),
            "detail": f"{len(rows)} rows",
            "required": False,
        }

    out: list[dict[str, Any]] = []
    for name, fn in (
        ("dnse", _probe_dnse),
        ("vietstock", _probe_vietstock),
        ("yfinance", _probe_yfinance),
    ):
        try:
            out.append(await asyncio.wait_for(asyncio.to_thread(fn), timeout=8))
        except Exception as exc:
            out.append({"name": name, "ok": False, "detail": str(exc)[:200], "required": False})
    return out


async def health_report(deep: bool = False) -> tuple[int, dict[str, Any]]:
    components = await asyncio.gather(
        component_redis(),
        component_postgres(),
        component_worker(),
    )
    parts: list[dict[str, Any]] = list(components)
    if deep:
        parts.extend(await deep_probes())
    return overall_status(parts)
