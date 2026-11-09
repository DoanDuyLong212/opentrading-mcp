"""Q2 (owner decision 2026-11-09): with fhsc dropped there is no detailed company,
shareholder or insider source. The tools stay unavailable/not_configured and
vn_company points at vs_company_info (name, exchange, type)."""

from __future__ import annotations

import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.server import create_server, register_preset


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(vn_p, "SRC_FUNDAMENTAL", ())
    srv = create_server("all")
    register_preset(srv, "all")
    return srv


async def test_vn_company_is_not_configured_and_suggests_vs_company_info(server):
    env = await server._tool_manager.get_tool("vn_company").fn(symbol="FPT")
    assert env["availability"] == "unavailable"
    assert env["reason"] == "not_configured"
    assert env["retryable"] is False
    assert env["alternatives"] == ["vs_company_info"]


async def test_vn_holders_and_insiders_are_not_configured(server):
    holders = await server._tool_manager.get_tool("holders").fn(symbol="FPT", region="vn")
    assert holders["availability"] == "unavailable" and holders["reason"] == "not_configured"
    insider = await server._tool_manager.get_tool("insider_trading").fn(symbol="FPT")
    assert insider["availability"] == "unavailable" and insider["reason"] == "not_configured"
