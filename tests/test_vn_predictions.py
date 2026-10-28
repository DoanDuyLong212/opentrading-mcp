"""vn_predictions tool: registration + read semantics without a live database."""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

mod = importlib.import_module("opentrading_mcp.tools.vn_predictions")
server_mod = importlib.import_module("opentrading_mcp.server")


def _tools():
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("test")
    mod.register_vn_predictions_tools(server)
    get = server._tool_manager.get_tool
    return {name: get(name).fn for name in
            ("vn_predictions_check", "vn_predictions_latest", "vn_predictions_sparkline")}


def test_registered_in_all_modules_and_registry():
    assert "vn_predictions" in server_mod.ALL_MODULES
    assert server_mod._REGISTER_BY_MODULE["vn_predictions"] == "register_vn_predictions_tools"


def test_tools_register_on_fastmcp():
    listed = _tools()
    assert {"vn_predictions_check", "vn_predictions_latest",
            "vn_predictions_sparkline"} <= set(listed)


@pytest.mark.asyncio
async def test_missing_store_reads_as_unavailable_envelope():
    async def boom(*a, **k):
        raise RuntimeError('relation "predictions.predictions_daily" does not exist')

    listed = _tools()
    with patch.object(mod.db, "read_rows", boom):
        out = await listed["vn_predictions_check"]()
    assert out["provenance"]["source"] == "vn_predictions"
    assert any("unavailable" in w for w in out.get("warnings", []))


@pytest.mark.asyncio
async def test_latest_builds_filters_and_defaults():
    captured = {}

    async def fake(tool, source, sql, args, cols, filtered=False):
        captured["sql"], captured["args"], captured["filtered"] = sql, tuple(args), filtered
        return {"data": {"rows": [{"asset": "Họ GELEX", "currency": "USD",
                 "as_of_date": "2026-10-28", "p_profit": 0.77}]},
                "provenance": {"source": "vn_predictions"}}

    listed = _tools()
    with patch.object(mod.db, "read_rows", fake):
        out = await listed["vn_predictions_latest"](currency="usd", asset="GELEX")
    assert out["provenance"]["source"] == "vn_predictions"
    assert "SELECT MAX(as_of_date)" in captured["sql"]
    assert "currency = %s" in captured["sql"] and "asset ILIKE %s" in captured["sql"]
    assert captured["args"] == ("USD", "%GELEX%")
    assert captured["filtered"] is True


@pytest.mark.asyncio
async def test_sparkline_clamps_days():
    captured = {}

    async def fake(tool, source, sql, args, cols, filtered=False):
        captured["args"] = tuple(args)
        return {"rows": []}

    listed = _tools()
    with patch.object(mod.db, "read_rows", fake):
        await listed["vn_predictions_sparkline"](asset="Họ GELEX", days=999)
    assert captured["args"][-1] == 365
