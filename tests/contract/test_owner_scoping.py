"""Contract: watchlists and alert rules belong to their caller; cycle rebuilds are team-only.

DB tests need a throwaway Postgres in TEST_DATABASE_URL (CI starts one; locally e.g.
`docker run -d -p 55432:5432 -e POSTGRES_PASSWORD=pw postgres:16` and
TEST_DATABASE_URL=postgresql://postgres:pw@localhost:55432/postgres). They are skipped without it.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import Any

import pytest

from opentrading_mcp import dbinit
from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.tools import cycle_db
from opentrading_mcp.tools.shared import TEAM_PRINCIPAL, AnyContext, caller_id

TEST_DB = os.environ.get("TEST_DATABASE_URL", "").strip()
needs_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


class Ctx:
    """The slice of the SDK Context the tools touch: log() and the HTTP request's state."""

    def __init__(self, user_id: str | None) -> None:
        state = SimpleNamespace(user_id=user_id) if user_id else SimpleNamespace()
        self.request_context = SimpleNamespace(request=SimpleNamespace(state=state))

    async def log(self, *_args: Any, **_kwargs: Any) -> None:
        return None


TEAM, ALICE = Ctx("team"), Ctx("alice")


@pytest.fixture(scope="module")
def tools() -> Any:
    server = create_server()
    register_all(server)

    def call(tool_name: str, /, **kwargs: Any) -> dict[str, Any]:
        tool = server._tool_manager.get_tool(tool_name)
        assert tool is not None, tool_name
        return asyncio.run(tool.fn(**kwargs))

    return call


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.delenv("MCP_DB_URL", raising=False)
    monkeypatch.setattr(dbinit, "_ensured", False)
    assert dbinit.ensure_tables()
    conn = cycle_db.connect()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM watchlists")
        cur.execute("DELETE FROM alert_rules")
    yield conn
    conn.close()


def test_caller_id_falls_back_to_team_without_a_request() -> None:
    assert caller_id(None) == TEAM_PRINCIPAL
    assert caller_id(SimpleNamespace()) == TEAM_PRINCIPAL
    assert caller_id(Ctx(None)) == TEAM_PRINCIPAL
    assert caller_id(ALICE) == "alice"


@needs_db
def test_one_callers_watchlist_is_invisible_and_untouchable_to_another(db: Any, tools: Any) -> None:
    created = tools("watchlist_create", name="core", ctx=TEAM)["data"]
    list_id = created["id"]
    tools("watchlist_add", list_id=list_id, symbols=["VCB", "FPT"], ctx=TEAM)

    assert tools("watchlist_list", ctx=ALICE)["data"]["watchlists"] == []
    assert tools("watchlist_get", list_id=list_id, ctx=ALICE)["availability"] == "empty"
    added = tools("watchlist_add", list_id=list_id, symbols=["HPG"], ctx=ALICE)
    assert "no watchlist" in added["warnings"][0]
    assert (
        tools("watchlist_remove", list_id=list_id, symbols=["VCB"], ctx=ALICE)["data"]["symbols"]
        == []
    )
    assert (
        tools("watchlist_update", list_id=list_id, name="mine", ctx=ALICE)["availability"]
        == "empty"
    )
    assert tools("watchlist_delete", list_id=list_id, ctx=ALICE)["availability"] == "empty"

    mine = tools("watchlist_get", list_id=list_id, ctx=TEAM)["data"]
    assert mine["name"] == "core" and mine["symbols"] == ["FPT", "VCB"]
    # Names are unique per owner, not globally.
    assert tools("watchlist_create", name="core", ctx=ALICE)["data"]["name"] == "core"
    assert len(tools("watchlist_list", ctx=TEAM)["data"]["watchlists"]) == 1


@needs_db
def test_one_callers_alert_rules_are_invisible_and_untouchable_to_another(
    db: Any, tools: Any
) -> None:
    rule = tools("alert_create", symbol="vcb", op=">", threshold=100.0, ctx=TEAM)["data"]
    assert tools("alert_list", ctx=ALICE)["data"]["rules"] == []
    assert tools("alert_pause", rule_id=rule["id"], ctx=ALICE)["availability"] == "empty"
    assert tools("alert_delete", rule_id=rule["id"], ctx=ALICE)["availability"] == "empty"
    rules = tools("alert_list", ctx=TEAM)["data"]["rules"]
    assert [(r["id"], r["active"]) for r in rules] == [(rule["id"], True)]


@needs_db
def test_rows_made_before_owners_existed_are_backfilled_to_the_team(
    monkeypatch: Any, tools: Any
) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.delenv("MCP_DB_URL", raising=False)
    conn = cycle_db.connect()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS watchlist_items, watchlists, alert_rules CASCADE")
        cur.execute("CREATE TABLE watchlists (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
        cur.execute(
            "CREATE TABLE alert_rules (id SERIAL PRIMARY KEY, symbol TEXT NOT NULL,"
            " op TEXT NOT NULL, threshold DOUBLE PRECISION NOT NULL,"
            " metric TEXT NOT NULL DEFAULT 'price', active BOOLEAN NOT NULL DEFAULT TRUE)"
        )
        cur.execute("INSERT INTO watchlists (name) VALUES ('legacy')")
        cur.execute("INSERT INTO alert_rules (symbol, op, threshold) VALUES ('FPT', '<', 90)")
    conn.close()
    monkeypatch.setattr(dbinit, "_ensured", False)
    assert dbinit.ensure_tables()

    names = [w["name"] for w in tools("watchlist_list", ctx=TEAM)["data"]["watchlists"]]
    assert names == ["legacy"]
    assert [r["symbol"] for r in tools("alert_list", ctx=TEAM)["data"]["rules"]] == ["FPT"]
    assert tools("watchlist_list", ctx=ALICE)["data"]["watchlists"] == []


def test_cycle_rebuilds_are_team_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_CYCLE_WRITE", raising=False)
    ran: list[str] = []

    async def work() -> dict[str, Any]:
        ran.append("x")
        return {"ok": True}

    refused = asyncio.run(cycle_db.guarded_write("cycle_stats_finalize", work, ALICE))
    assert refused["availability"] == "unavailable"
    assert "team" in refused["warnings"][0]
    assert ran == []
    assert asyncio.run(cycle_db.guarded_write("cycle_stats_finalize", work, TEAM)) == {"ok": True}
    assert asyncio.run(cycle_db.guarded_write("cycle_stats_finalize", work)) == {"ok": True}
    assert ran == ["x", "x"]


def test_a_tool_sees_the_jwt_subject_through_the_real_http_stack(monkeypatch: Any) -> None:
    """AuthMiddleware -> SDK -> tool: the user_id it stores is what caller_id reads."""
    import json

    from starlette.testclient import TestClient

    from opentrading_mcp import auth_oauth
    from opentrading_mcp.cli import build_http_app

    monkeypatch.delenv("MCP_BEARER_TEAM", raising=False)
    monkeypatch.delenv("MCP_TOKEN", raising=False)
    monkeypatch.setattr(auth_oauth, "is_configured", lambda: True)
    monkeypatch.setattr(auth_oauth, "validate_jwt", lambda token: {"sub": f"user-{token}"})

    async def fake_quota(*_args: Any) -> tuple[bool, int]:
        return True, 0

    from opentrading_mcp import quota

    monkeypatch.setattr(quota, "check_and_record", fake_quota)
    server = create_server()

    @server.tool()
    async def whoami(ctx: AnyContext) -> str:
        return caller_id(ctx)

    headers = {"Authorization": "Bearer alice", "accept": "application/json, text/event-stream"}
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "whoami", "arguments": {}},
    }
    # The SDK only accepts a localhost Host header by default (DNS-rebinding guard).
    with TestClient(build_http_app(server), base_url="http://127.0.0.1:8000") as client:
        response = client.post("/mcp", json=call, headers=headers)
    assert response.status_code == 200
    data = next(line[5:] for line in response.text.splitlines() if line.startswith("data:"))
    assert json.loads(data)["result"]["content"][0]["text"] == "user-alice"
