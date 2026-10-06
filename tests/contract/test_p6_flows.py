"""P10 contract: flow-chart payloads + tail (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def test_nn_flow_chart_sends_required_fields(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        seen["path"] = path
        seen["payload"] = payload
        return [[], []]

    monkeypatch.setattr(vs_p, "_post", fake_post)
    vs_p.nn_flow_chart()
    assert seen["path"] == "/data/KQGDGiaoDichNDTNNChart"
    for key in ("selectType", "code", "type", "isRealTime"):
        assert key in seen["payload"], key


async def test_vs_nn_flow_tool_tails_points(monkeypatch):
    rows = [
        {"TradingDate": f"/Date({1788368400000 + i * 86400000})/", "BuyVol": 1.0}
        for i in range(10)
    ]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return [["/Date(1790755200000)/"], rows]

    import opentrading_mcp.tools.vs as vs_mod

    monkeypatch.setattr(vs_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_nn_flow")
    assert tool is not None
    env = await tool.fn(days=3)
    assert env["availability"] == "available"
    assert len(env["data"]["flow"][1]) == 3


def test_selftrading_chart_sends_required_fields(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        seen["path"] = path
        seen["payload"] = payload
        return [[], []]

    monkeypatch.setattr(vs_p, "_post", fake_post)
    vs_p.selftrading_chart()
    assert seen["path"] == "/data/KQGDGiaoDichTuDoanhChart"
    for key in ("selectType", "code", "type"):
        assert key in seen["payload"], key


def test_gics_index_sends_type(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        seen["path"] = path
        seen["payload"] = payload
        return [{"IndustryCode": 1010}]

    monkeypatch.setattr(vs_p, "_post", fake_post)
    out = vs_p.gics_index(group=2)
    assert seen["path"] == "/data/GetGICSIndexMain"
    assert seen["payload"] == {"type": 2}
    assert out == [{"IndustryCode": 1010}]


async def test_vs_gics_index_tool_passes_group(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        assert args == (2,), args
        return [{"IndustryCode": 4520}]

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_gics_index")
    assert tool is not None
    env = await tool.fn(group=2)
    assert env["availability"] == "available"
    assert env["data"]["rows"] == [{"IndustryCode": 4520}]


def test_market_info_sends_type(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        seen["path"] = path
        seen["payload"] = payload
        return [{"exId": 1}]

    monkeypatch.setattr(vs_p, "_post", fake_post)
    out = vs_p.market_info_board(exchange="HNX")
    assert seen["path"] == "/data/marketinfo"
    assert seen["payload"] == {"type": 2}
    assert out == [{"exId": 1}]


async def test_vs_market_info_tool_maps_exchange(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        assert args == ("UPCOM",), args
        return [{"exId": 3}]

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_market_info")
    assert tool is not None
    env = await tool.fn(exchange="UPCOM")
    assert env["availability"] == "available"
    assert env["data"]["rows"] == [{"exId": 3}]


async def test_vs_market_info_bad_exchange_is_unavailable():
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_market_info")
    assert tool is not None
    env = await tool.fn(exchange="NYSE")
    assert env["availability"] == "unavailable"


async def test_indicator_data_defaults_2022_and_macro_path(monkeypatch):

    seen: dict[str, Any] = {}

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        seen["args"] = args
        return {"rows": [{"name": "GDP", "value": 1.0}]}

    import opentrading_mcp.tools.vs as vs_mod

    monkeypatch.setattr(vs_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_indicator_data")
    assert tool is not None
    await tool.fn(category_id=73)
    assert seen["args"] == (3, 73, "", "2022-01-01", None)


async def test_xnk_detail_defaults_current_year(monkeypatch):
    import datetime

    seen: dict[str, Any] = {}

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        seen["args"] = args
        return {"rows": [{"name": "My", "value": 1.0}]}

    import opentrading_mcp.tools.vs_bctc as bctc_mod

    monkeypatch.setattr(bctc_mod, "_call", fake_call)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vs_xnk_detail")
    assert tool is not None
    await tool.fn()
    assert seen["args"][:3] == (2, 64, "")
    assert seen["args"][3] == f"{datetime.date.today().year}-01-01"
