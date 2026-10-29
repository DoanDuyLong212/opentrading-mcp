"""vn_screener + vnindex_scenarios tools: registration + read semantics (no live DB)."""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

scr = importlib.import_module("opentrading_mcp.tools.vn_screener")
vsc = importlib.import_module("opentrading_mcp.tools.vnindex_scenarios")
server_mod = importlib.import_module("opentrading_mcp.server")


def _tools(module):
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("t")
    if module is scr:
        module.register_vn_screener_tools(server)
    else:
        module.register_vnindex_scenarios_tools(server)
    get = server._tool_manager.get_tool
    return {name: get(name).fn for name in
            ("vn_screener_check", "vn_screener_top", "vn_screener_symbol",
             "vnindex_scenarios_check", "vnindex_scenarios_latest",
             "vnindex_scenarios_history", "vnindex_risk_heads") if get(name)}


def test_registered_in_all_modules_and_registry():
    assert "vn_screener" in server_mod.ALL_MODULES
    assert "vnindex_scenarios" in server_mod.ALL_MODULES
    assert server_mod._REGISTER_BY_MODULE["vn_screener"] == "register_vn_screener_tools"
    assert server_mod._REGISTER_BY_MODULE["vnindex_scenarios"] == "register_vnindex_scenarios_tools"


def test_screener_tools_register():
    listed = _tools(scr)
    assert {"vn_screener_check", "vn_screener_top", "vn_screener_symbol"} <= set(listed)


def test_vnindex_tools_register():
    listed = _tools(vsc)
    assert {"vnindex_scenarios_check", "vnindex_scenarios_latest",
            "vnindex_scenarios_history", "vnindex_risk_heads"} <= set(listed)


@pytest.mark.asyncio
async def test_screener_top_builds_filters_and_limit():
    captured = {}

    async def fake(tool, source, sql, args, cols, filtered=False):
        captured["sql"], captured["args"] = sql, tuple(args)
        return {"data": {"rows": []}, "provenance": {"source": "vn_screener"}}

    listed = _tools(scr)
    with patch.object(scr.db, "read_rows", fake):
        out = await listed["vn_screener_top"](limit=5, min_probability=0.1)
    assert "p_touch20 >= %s" in captured["sql"]
    assert captured["args"] == (0.1,)
    assert "ORDER BY p_touch20 DESC" in captured["sql"]
    assert out["provenance"]["source"] == "vn_screener"


@pytest.mark.asyncio
async def test_vnindex_latest_defaults_to_max_asof():
    captured = {}

    async def fake(tool, source, sql, args, cols, filtered=False):
        captured["sql"] = sql
        return {"data": {"rows": []}, "provenance": {"source": "vnindex_scenarios"}}

    listed = _tools(vsc)
    with patch.object(vsc.db, "read_rows", fake):
        await listed["vnindex_scenarios_latest"]()
    assert "SELECT MAX(as_of_date)" in captured["sql"]


@pytest.mark.asyncio
async def test_sparkline_clamps_days():
    captured = {}

    async def fake(tool, source, sql, args, cols, filtered=False):
        captured["args"] = tuple(args)
        return {"data": {"rows": []}, "provenance": {"source": "vnindex_scenarios"}}

    listed = _tools(vsc)
    with patch.object(vsc.db, "read_rows", fake):
        await listed["vnindex_scenarios_history"](horizon=20, days=999)
    assert captured["args"] == (20, 180)


@pytest.mark.asyncio
async def test_missing_store_reads_as_unavailable():
    async def boom(*a, **k):
        raise RuntimeError('relation "predictions.screener_signals_daily" does not exist')

    listed = _tools(scr)
    with patch.object(scr.db, "read_rows", boom):
        out = await listed["vn_screener_check"]()
    assert out["provenance"]["source"] == "vn_screener"
    assert any("unavailable" in w for w in out.get("warnings", []))
