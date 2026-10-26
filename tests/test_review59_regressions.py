"""Independent financial and tool-boundary regressions from PR #59 review."""
from __future__ import annotations

import asyncio
import threading
from datetime import date, timedelta

import pytest

from opentrading_mcp.resources import _EXCHANGES
from opentrading_mcp.server import create_server
from opentrading_mcp.tools.quant_shared import _condition_gate, _run_strategy


def test_final_close_loss_is_in_drawdown():
    out = _run_strategy([100., 100., 50.], "buy_hold", 1, 2, 0., opens=[100.] * 3)
    assert out["net_return"] == -0.5
    assert out["max_drawdown"] == 0.5


def test_fee_once_per_side_and_full_fee_drawdown():
    out = _run_strategy([100.] * 4, "buy_hold", 1, 2, 10., opens=[100.] * 4,
                        cond_ok=[True, False, False, False])
    expected_loss = round(1 - 0.999**2, 4)
    assert out["trades"] == 1
    assert out["net_return"] == -expected_loss
    assert out["max_drawdown"] == expected_loss


@pytest.mark.parametrize("bad_open", [None, 0., -1., float("inf"), float("nan")])
def test_invalid_open_uses_honest_close_fallback(bad_open):
    out = _run_strategy([100., 110., 121.], "buy_hold", 1, 2, 0.,
                        opens=[100., bad_open, 110.])
    assert out["fill"] == "next-bar-close-fallback"
    assert out["net_return"] == .1


def test_upcom_continuous_to_1500_without_atc():
    venue = _EXCHANGES["venues"]["UPCOM"]
    assert venue["session"] == "09:00-11:30, 13:00-15:00 continuous"
    assert venue["auction"].startswith("no ATO/ATC;")


def test_missing_condition_blocks_at_alignment_boundary():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(5)]
    assert _condition_gate(days, [], [], "rising", 2) == [False] * 5


@pytest.mark.asyncio
@pytest.mark.parametrize("sweep", [False, True])
async def test_tool_reports_inferred_dates(monkeypatch, sweep):
    from opentrading_mcp.tools import quant_backtest as qb

    async def fake_rb(*args, **kwargs):
        return [{"c": float(100+i), "o": float(100+i)} for i in range(40)]

    monkeypatch.setattr(qb, "run_blocking", fake_rb)
    server = create_server()
    qb.register_quant_backtest_tools(server)
    name = "param_sweep" if sweep else "backtest_strategies"
    fn = server._tool_manager.get_tool(name).fn
    args = {"fast_range": [2], "slow_range": [3]} if sweep else {"fast": 2, "slow": 3}
    env = await fn(symbol="REVIEW", strategy="sma_cross", **args)
    rows = env["data"]["ranked"] if sweep else [env["data"]]
    assert rows and all(r["stale"] and r["date_basis"] == "inferred" for r in rows)


@pytest.mark.asyncio
async def test_watchlist_connect_and_close_stay_on_worker(monkeypatch):
    from opentrading_mcp.tools import watchlist as wl

    main_thread = threading.get_ident()
    started, release = threading.Event(), threading.Event()
    seen = []

    class Cursor:
        def __enter__(self):
            seen.append(threading.get_ident())
            return self
        def __exit__(self, *args):
            pass
        def execute(self, *args):
            pass
        def fetchone(self):
            return {"id": 1}  # duplicate path still needs cleanup

    class Conn:
        def cursor(self, **kwargs):
            return Cursor()
        def close(self):
            seen.append(threading.get_ident())

    def connect():
        seen.append(threading.get_ident())
        started.set()
        assert release.wait(5)
        return Conn()

    monkeypatch.setattr(wl, "_pg", connect)
    server = create_server()
    wl.register_watchlist_tools(server)
    task = asyncio.create_task(server._tool_manager.get_tool("watchlist_create").fn(name="core"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert not task.done()  # event loop stayed responsive during connect
    finally:
        release.set()
    await task
    assert len(seen) == 3 and all(t != main_thread for t in seen)
