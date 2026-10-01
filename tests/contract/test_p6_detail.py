"""P11 contract: financial_detail free chain (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "scan"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def test_financial_detail_chains_three_calls(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    calls: list[str] = []

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        calls.append(path)
        if "Norm" in path:
            return {"data": [{"ReportNormId": 2206, "ReportNormName": "DTBH"}]}
        if "GetListReportData" in path:
            return {"data": [{"ReportDataID": 11}, {"ReportDataID": 12}]}
        if "DetailValue" in path:
            assert payload["listReportDataIds"] == [11, 12]
            return {"data": [{"Name": "DTBH", "V1": 1.0, "V2": 2.0}]}
        raise AssertionError(path)

    monkeypatch.setattr(vs_p, "_post", fake_post)
    out = vs_p.financial_detail("FPT", statement="KQKD", periods_n=2)
    assert [c.split("/")[-1] for c in calls] == [
        "GetListReportNorm_KQKD_ByStockCode",
        "KQKD_GetListReportData",
        "GetReportDataDetailValue_KQKD_ByReportDataIds",
    ]
    assert out["periods"] == [11, 12]
    assert out["rows"][0]["Name"] == "DTBH"


async def test_financial_detail_tool_shape(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return {
            "symbol": "FPT",
            "statement": "KQKD",
            "unit": "VNDbn",
            "periods": [11, 12],
            "rows": [{"Name": "DTBH", "V1": 1.0}],
        }

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("financial_detail")
    env = await fn(symbol="FPT", statement="KQKD", periods_n=2)
    assert env["availability"] == "available"
    assert env["data"]["statement"] == "KQKD"
    assert env["data"]["unit"] == "VNDbn"


async def test_financial_detail_bad_statement_is_unavailable():
    fn = _tool_fn("financial_detail")
    env = await fn(symbol="FPT", statement="NOPE")
    assert env["availability"] == "unavailable"
