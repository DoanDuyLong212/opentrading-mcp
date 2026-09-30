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


async def test_vs_news_search_error_is_unavailable(monkeypatch):
    import json

    class FakeResp:
        text = json.dumps(
            {"Message": "No HTTP resource was found that matches the request URI 'x'."}
        )

    monkeypatch.setattr("httpx.post", lambda *a, **k: FakeResp())
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_news_search")
    assert tool is not None
    env = await tool.fn(query="VCB")
    assert env["availability"] == "unavailable"


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

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        raise ProviderBadData("dnse foreign-trading error 400: range exceeds maximum time range")

    import opentrading_mcp.tools.dnse_ext as ext_mod

    monkeypatch.setattr(ext_mod, "run_blocking", fake_block)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("dnse_foreign_rest")
    assert tool is not None
    env = await tool.fn(symbol="VCB")
    assert env["availability"] == "unavailable"


async def test_financial_values_empty_rows_is_unavailable(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return {"symbol": "VCB", "norms": 256, "rows": []}

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_financial_values")
    assert tool is not None
    env = await tool.fn(symbol="VCB")
    assert env["availability"] == "unavailable"
    assert any("mirror" in w for w in env["warnings"])


async def test_financial_values_package_error_is_unavailable(monkeypatch):
    from opentrading_mcp.providers.errors import ProviderAuthMissing

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        raise ProviderAuthMissing("vietstock package limited: Package_Permission_Year_Period")

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_financial_values")
    assert tool is not None
    env = await tool.fn(symbol="VCB")
    assert env["availability"] == "unavailable"


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


async def test_stock_industry_empty_model_is_empty(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return []

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_stock_industry")
    assert tool is not None
    env = await tool.fn(industry_id=3)
    assert env["availability"] == "empty"


async def test_stock_industry_model_list_passes(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return [{"StockCode": "VCB", "BusinessTypeID": 3}]

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_stock_industry")
    assert tool is not None
    env = await tool.fn(industry_id=3)
    assert env["availability"] == "available"
    assert env["data"]["stocks"][0]["StockCode"] == "VCB"
