"""P11 contract: breadth case-insensitive, reference KBS source (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


async def test_breadth_counts_capitalized_change(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {"Code": "AAA", "Change": 1.5},
            {"Code": "BBB", "Change": -0.5},
            {"Code": "CCC", "Change": 0.0},
        ]

    import opentrading_mcp.tools.market as market_mod

    monkeypatch.setattr(market_mod, "run_blocking", fake_block)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("breadth_scan")
    assert tool is not None
    env = await tool.fn()
    assert env["availability"] == "available"
    assert env["data"]["advancers"] == 1
    assert env["data"]["decliners"] == 1
    assert env["data"]["rows"] == 3


def test_reference_equity_uses_kbs_source(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    seen: dict[str, Any] = {}

    class FakeEquity:
        def list_by_exchange(self, source: str = "kbs") -> Any:
            seen["source"] = source
            import pandas as pd

            return pd.DataFrame(
                [
                    {"symbol": "VCB", "organ_name": "Vietcombank", "exchange": "HOSE"},
                    {"symbol": "ABC", "organ_name": "ABC", "exchange": "HNX"},
                ]
            )

    class FakeReference:
        def __init__(self) -> None:
            self.equity = FakeEquity()

    import sys
    import types

    fake_mod = types.ModuleType("vnstock")
    fake_mod.Reference = FakeReference  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vnstock", fake_mod)
    rows = vn_p.reference_equity("HOSE")
    assert seen["source"] == "KBS"
    assert [r["symbol"] for r in rows] == ["VCB"]


def test_btmc_gold_parses_direct_payload():
    from opentrading_mcp.providers import vn_public as pub_p

    payload = {
        "DataList": {
            "Data": [
                {
                    "@row": "1",
                    "@n_1": "VÀNG MIẾNG SJC 1L",
                    "@k_1": "",
                    "@h_1": "",
                    "@pb_1": "180000000",
                    "@ps_1": "182000000",
                    "@pt_1": "4155",
                    "@d_1": "01/10/2026 10:22",
                }
            ]
        }
    }
    rows = pub_p._parse_btmc(payload)
    assert rows[0]["name"] == "VÀNG MIẾNG SJC 1L"
    assert rows[0]["buy_price"] == "180000000"
    assert rows[0]["sell_price"] == "182000000"


async def test_retail_gold_prefers_direct_fetch(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [{"name": "VÀNG MIẾNG SJC 1L", "buy_price": "1", "sell_price": "2"}]

    import opentrading_mcp.tools.vn as vn_mod

    monkeypatch.setattr(vn_mod, "run_blocking", fake_block)
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vn_retail_gold")
    assert tool is not None
    env = await tool.fn()
    assert env["availability"] == "available"
    assert env["data"]["rows"][0]["name"] == "VÀNG MIẾNG SJC 1L"
