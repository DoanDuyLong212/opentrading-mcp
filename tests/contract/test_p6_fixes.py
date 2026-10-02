"""P9 contract: news error-payload, accent lookup, foreign_rest dates (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def test_news_search_error_payload_raises():
    import pytest

    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers.errors import ProviderBadData

    with pytest.raises(ProviderBadData):
        vs_p._coerce_articles(
            {"Message": "No HTTP resource was found that matches the request URI 'x'."}
        )


def test_news_search_normal_passthrough():
    from opentrading_mcp.providers import vietstock as vs_p

    rows = [{"Title": "VCB tăng", "Url": "https://x"}]
    assert vs_p._coerce_articles(rows) == rows
    assert vs_p._coerce_articles({"data": rows}) == rows


async def test_symbol_lookup_ignores_accents(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [{"symbol": "HPG", "name": "CTCP Tập đoàn Hòa Phát"}]

    import opentrading_mcp.tools.market as market_mod

    monkeypatch.setattr(market_mod, "run_blocking", fake_block)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("symbol_lookup")
    assert tool is not None
    env = await tool.fn(query="hoa phat")
    assert env["availability"] == "available"
    assert env["data"]["hits"][0]["symbol"] == "HPG"


async def test_foreign_rest_errorcode_is_unavailable(monkeypatch):
    import pytest

    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers.errors import ProviderBadData

    with pytest.raises(ProviderBadData):
        dnse_p._coerce_foreign({"errorCode": 400, "message": "range exceeds maximum time range"})


def test_financial_values_provider_surfaces_package_error(monkeypatch):
    import pytest

    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers.errors import ProviderAuthMissing

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        if "LoadReportData" in path:
            return {"error": {"ErrorCode": "Package_Permission_Year_Period"}}
        return [{"ReportNormID": 2216, "Name": "DT thuần"}]

    monkeypatch.setattr(vs_p, "_post_json", fake_post)
    with pytest.raises(ProviderAuthMissing):
        vs_p.financial_values("VCB", years=1, tids=[5])
