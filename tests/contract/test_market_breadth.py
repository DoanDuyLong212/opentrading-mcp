"""Breadth comes from per-exchange marketinfo boards; overview ranks by percent_change.

Fixture: live deployed MCP output of 2026-10-23 (session of 2026-10-22). The old
breadth_scan counted the 7 rows of /data/getmarketprice (VN-Index, HNX-Index,
VS100, gold, oil, VN30F1M) as "stocks"; market_overview sorted and counted on a
`change` key the vnstock board does not have, so it always said 0 up / 0 down.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opentrading_mcp.server import create_server, register_preset

FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "market_board_20261022.json").read_text(
        encoding="utf-8"
    )
)
HOSE = FIXTURE["marketinfo_hose"]
# Same row shape as the live HOSE board, other counts.
HNX = [{**HOSE[0], "c": "HNX-Index", "e": "HNX", "up": 60, "upc": 4, "st": 40, "dn": 70, "dnf": 1}]
UPCOM = [{**HOSE[0], "c": "UPCOM", "e": "UPCOM", "up": 120, "upc": 9, "st": 300, "dn": 110,
          "dnf": 5}]


def _tool_fn(name: str):
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _fake_boards(monkeypatch, boards: dict[str, Any], calls: list[str] | None = None) -> None:
    import opentrading_mcp.tools.market as market_mod
    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        if getattr(fn, "func", None) is vs_p.market_info_board:
            venue = fn.args[0]
            if calls is not None:
                calls.append(venue)
            board = boards.get(venue)
            if isinstance(board, Exception):
                raise board
            return board
        raise ProviderUnavailable(f"unexpected upstream {fn}")

    monkeypatch.setattr(market_mod, "run_blocking", fake_rb)


async def test_breadth_sums_the_three_exchange_boards(monkeypatch):
    _fake_boards(monkeypatch, {"HOSE": HOSE, "HNX": HNX, "UPCOM": UPCOM})
    env = await _tool_fn("breadth_scan")()
    data = env["data"]
    assert env["availability"] == "available"
    assert data["exchanges"][0] == {
        "exchange": "HOSE",
        "advancers": 147,
        "decliners": 164,
        "unchanged": 57,
        "ceiling": 2,
        "floor": 3,
    }
    assert data["advancers"] == 147 + 60 + 120
    assert data["decliners"] == 164 + 70 + 110
    assert data["unchanged"] == 57 + 40 + 300
    assert data["advancers_pct"] == round(327 / (327 + 344 + 397) * 100, 1)


async def test_breadth_one_exchange_only_calls_that_board(monkeypatch):
    calls: list[str] = []
    _fake_boards(monkeypatch, {"HOSE": HOSE}, calls)
    env = await _tool_fn("breadth_scan")(exchange="hose")
    assert calls == ["HOSE"]
    assert env["data"]["advancers"] == 147
    assert env["data"]["advancers_pct"] == round(147 / (147 + 164 + 57) * 100, 1)


async def test_breadth_unknown_exchange_is_unavailable(monkeypatch):
    calls: list[str] = []
    _fake_boards(monkeypatch, {}, calls)
    env = await _tool_fn("breadth_scan")(exchange="NYSE")
    assert env["availability"] == "unavailable"
    assert calls == []


async def test_breadth_partial_when_an_exchange_fails(monkeypatch):
    from opentrading_mcp.providers.errors import ProviderUnavailable

    _fake_boards(
        monkeypatch, {"HOSE": HOSE, "HNX": ProviderUnavailable("timeout"), "UPCOM": UPCOM}
    )
    env = await _tool_fn("breadth_scan")()
    assert env["availability"] == "partial"
    assert [b["exchange"] for b in env["data"]["exchanges"]] == ["HOSE", "UPCOM"]
    assert any("HNX" in w for w in env["warnings"])


async def test_breadth_falls_back_to_the_daily_snapshot(monkeypatch):
    import opentrading_mcp.tools.market as market_mod
    from opentrading_mcp import snapshots
    from opentrading_mcp.providers.errors import ProviderUnavailable

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        if getattr(fn, "func", None) is snapshots.load:
            return [{"date": "2026-10-22", "kind": "breadth_3ex", "payload": [HOSE, HNX, UPCOM]}]
        raise ProviderUnavailable("vietstock down")

    monkeypatch.setattr(market_mod, "run_blocking", fake_rb)
    env = await _tool_fn("breadth_scan")(exchange="HNX")
    assert env["availability"] == "stale"
    assert env["data"]["from_snapshot"] is True
    assert env["data"]["exchanges"] == [
        {"exchange": "HNX", "advancers": 60, "decliners": 70, "unchanged": 40, "ceiling": 4,
         "floor": 1}
    ]


async def test_market_overview_ranks_and_counts_on_percent_change(monkeypatch):
    import opentrading_mcp.tools.market as market_mod
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import vnstock as vn_p

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        assert getattr(fn, "func", None) is vn_p.equity_quote_batch
        return [dict(q) for q in FIXTURE["board_quotes"]]

    monkeypatch.setattr(market_mod, "run_blocking", fake_rb)
    monkeypatch.setattr(dnse_p, "ws_snapshot", lambda symbols: {"mock": True})
    env = await _tool_fn("market_overview")(top_n=2)
    data = env["data"]
    # VCB -0.18, HPG +0.47, SSI -1.23, VIC +4.16, VHM +3.56, MSN +0.27
    assert data["breadth"] == {"advancers": 4, "decliners": 2, "flat": 0}
    assert [m["symbol"] for m in data["movers"]] == ["VIC", "VHM"]
    assert [m["symbol"] for m in data["losers"]] == ["SSI", "VCB"]
