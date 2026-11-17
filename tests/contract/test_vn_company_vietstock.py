"""#148: vn_company serves the Vietstock profile; VN shareholders say no source.

Every client used to pay a doomed vnstock call first (fhsc/fmp discontinued)
and then get pointed at vs_company_info by failures.py.
"""

from __future__ import annotations

import pytest


def _tool(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("all")
    register_preset(server, "all")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


@pytest.fixture
def vs_profile(monkeypatch) -> dict:
    from opentrading_mcp.providers import vietstock as vs_p

    payload = {"CompanyOrganName": "FPT Corporation", "Exchange": "HOSE"}
    monkeypatch.setattr(vs_p, "company_info", lambda symbol: payload)
    return payload


async def test_vn_company_serves_the_vietstock_profile(vs_profile):
    env = await _tool("vn_company")(symbol="FPT")
    assert env["data"]["info"] == vs_profile
    assert env["provenance"]["source"] == "vietstock"
    assert env["availability"] != "unavailable"


async def test_vn_company_detail_keeps_the_profile_and_discloses_the_gap(vs_profile):
    env = await _tool("vn_company")(symbol="FPT", detail=True)
    assert env["data"]["info"] == vs_profile
    assert env["availability"] == "partial"
    assert any("shareholder" in w.lower() for w in env["warnings"])


async def test_holders_vn_is_a_clear_no_source_without_a_provider_roundtrip(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("vnstock company_info must not be called for region=vn")

    monkeypatch.setattr(vn_p, "company_info", _must_not_be_called)
    env = await _tool("holders")(symbol="FPT", region="vn")
    assert env["availability"] == "unavailable"
    assert "no source" in " ".join(env["warnings"]).lower()
    assert "fhsc" in " ".join(env["warnings"]).lower()


def test_insider_trading_docstring_says_there_is_no_source():
    fn = _tool("insider_trading")
    assert fn.__doc__ is not None
    assert "nguồn" in fn.__doc__.lower() or "no source" in fn.__doc__.lower()
