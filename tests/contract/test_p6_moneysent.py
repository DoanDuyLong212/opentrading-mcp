"""P12b contract: sentiment list-body + money_flow fallback path (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def test_fireant_posts_accepts_bare_list(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    monkeypatch.setenv("FIREANT_TOKEN", "test-token")

    class FakeResp:
        status_code = 200

        def json(self) -> Any:
            return [{"post_id": 1, "content": "VCB ngon", "user": {"name": "a"}, "likes": 5}]

    monkeypatch.setattr("httpx.get", lambda *a, **k: FakeResp())
    out = intel_p.fireant_posts("VCB", 3)
    assert isinstance(out, list) and len(out) == 1


async def test_money_flow_uses_nn_chart_fallback(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    def boom(symbols: list[str] | None = None) -> Any:
        raise ProviderUnavailable("ws worker has not published yet")

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        from opentrading_mcp.providers import vietstock as vs_mod

        assert fn is vs_mod.nn_flow_chart
        return [["/Date(1)/"], [{"BuyVol": 2.0}]]

    monkeypatch.setattr(dnse_p, "ws_snapshot", boom)
    import opentrading_mcp.tools.scan as scan_mod

    monkeypatch.setattr(scan_mod, "run_blocking", fake_block)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("money_flow")
    assert tool is not None
    env = await tool.fn(symbols=["VNINDEX"])
    assert env["availability"] == "available"
    assert env["data"]["primary"] == "vietstock"


async def test_sentiment_score_end_to_end(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if tool == "s":
            return [{"text": "VCB quá ngon, múc mạnh", "likes": 10}]
        return '{"score": 0.8}'

    import opentrading_mcp.tools.compute as comp_mod

    monkeypatch.setattr(comp_mod, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("sentiment_score")
    assert tool is not None
    env = await tool.fn(symbol="VCB", limit=3)
    assert env["availability"] == "available"
