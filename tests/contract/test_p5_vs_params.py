"""P5 contract: enriched params for vs.py tools (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str):
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


async def test_vs_market_price_accepts_type(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_market_price(board_type: int = 2):
        seen["board_type"] = board_type
        return [{"code": "VNINDEX"}]

    monkeypatch.setattr(vs_p, "market_price", fake_market_price)
    fn = _tool_fn("vs_market_price")
    env = await fn(type=3)
    _check_envelope(env, "vs_market_price")
    assert seen["board_type"] == 3
    assert env["data"]["rows"] == [{"code": "VNINDEX"}]


async def test_vs_market_price_default_type_is_2(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_market_price(board_type: int = 2):
        seen["board_type"] = board_type
        return []

    monkeypatch.setattr(vs_p, "market_price", fake_market_price)
    fn = _tool_fn("vs_market_price")
    await fn()
    assert seen["board_type"] == 2


async def test_vs_nn_flow_days_truncates_chart():
    import inspect

    # contract: tool must accept days param
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_nn_flow")
    assert tool is not None
    params = inspect.signature(tool.fn).parameters
    assert "days" in params, "vs_nn_flow must accept days"


async def test_vs_nn_flow_days_slices_tail(monkeypatch):
    dates = [f"2026-09-{d:02d}" for d in range(1, 11)]
    rows = [{"TradingDate": d, "BuyVol": 1, "SellVol": 2} for d in dates]

    async def fake_call(tool: str, fn: Any, *args: Any):
        assert tool == "vs_nn_flow"
        return [dates, rows]

    import opentrading_mcp.tools.vs as vs_mod

    monkeypatch.setattr(vs_mod, "_call", fake_call)
    fn = _tool_fn("vs_nn_flow")
    env = await fn(days=3)
    _check_envelope(env, "vs_nn_flow")
    flow = env["data"]["flow"]
    assert flow[0] == dates[-3:]
    assert [r["TradingDate"] for r in flow[1]] == dates[-3:]


async def test_vs_indicator_data_accepts_range_params(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_macro(
        tt: int, cat: int, sub: str = "", frm: str = "2022-01-01", to: str | None = None
    ) -> Any:
        seen.update(tt=tt, cat=cat, sub=sub, frm=frm, to=to)
        return {"rows": [{"name": "GDP", "value": 1.0}]}

    monkeypatch.setattr(vs_p, "macro_report_data", fake_macro)
    fn = _tool_fn("vs_indicator_data")
    env = await fn(
        category_id=73,
        term_type_id=3,
        sub_term_type_id="M1",
        from_date="2020-01-01",
    )
    _check_envelope(env, "vs_indicator_data")
    assert seen == {"tt": 3, "cat": 73, "sub": "M1", "frm": "2020-01-01", "to": None}
    assert env["data"]["rows"][0]["name"] == "GDP"
    assert seen["cat"] == 73


async def test_vs_indicator_data_coerces_model_typing(monkeypatch):
    """Eval 06-10 (S07): model passes ids as int/str/quoted-str — all must coerce."""
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_macro(
        tt: int, cat: int, sub: str = "", frm: str = "2022-01-01", to: str | None = None
    ) -> Any:
        seen.update(tt=tt, cat=cat, sub=sub)
        return {"rows": [{"name": "X", "value": 1.0}]}

    monkeypatch.setattr(vs_p, "macro_report_data", fake_macro)
    fn = _tool_fn("vs_indicator_data")
    env = await fn(category_id=76, term_type_id=7, sub_term_type_id=3)
    _check_envelope(env, "vs_indicator_data")
    assert seen == {"tt": 7, "cat": 76, "sub": "3"}, seen
    env = await fn(category_id=15, term_type_id='"7"', sub_term_type_id='"2"')
    _check_envelope(env, "vs_indicator_data")
    assert seen == {"tt": 7, "cat": 15, "sub": "2"}, seen
