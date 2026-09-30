"""P8 contract: RS vs index + 52w position + sma150 in technicals (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _bars(
    n: int, start: float = 100.0, step: float = 0.1, day: str = "2026-01-02"
) -> list[dict[str, Any]]:
    import datetime

    d = datetime.date.fromisoformat(day)
    out = []
    c = start
    for _ in range(n):
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        out.append({"t": d.isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000.0})
        c += step
        d += datetime.timedelta(days=1)
    return out


def test_rs_positive_when_outperforming():
    from opentrading_mcp.providers import technicals as tech_p

    sym = _bars(250, start=100.0, step=0.2)  # ~+9% over trailing 63d
    bench = [100.0] * 250
    out = tech_p.compute(sym, benchmark=bench)
    assert out["rs_vs_bench"] is not None and out["rs_vs_bench"] > 5.0


def test_rs_none_without_benchmark():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_bars(100))
    assert out["rs_vs_bench"] is None


def test_pos_52w_edges():
    from opentrading_mcp.providers import technicals as tech_p

    up = tech_p.compute(_bars(250, start=100.0, step=0.1))
    assert up["pos_52w"] is not None and up["pos_52w"] > 0.9
    down = tech_p.compute(_bars(250, start=100.0, step=-0.1))
    assert down["pos_52w"] is not None and down["pos_52w"] < 0.1


def test_sma150_needs_length():
    from opentrading_mcp.providers import technicals as tech_p

    assert tech_p.compute(_bars(100))["sma150"] is None
    assert isinstance(tech_p.compute(_bars(250))["sma150"], float)


async def test_signals_technical_includes_rs(monkeypatch):
    import opentrading_mcp.tools.scan as scan_mod

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        sym = getattr(fn, "args", [None])[0]
        if sym == "VNINDEX":
            return _bars(250, start=1000.0, step=0.0)
        return _bars(250, start=100.0, step=0.04)

    monkeypatch.setattr(scan_mod, "run_blocking", fake_block)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("signals_technical")
    assert tool is not None
    env = await tool.fn(symbol="VCB", indicators=["rs_vs_bench", "pos_52w", "sma150"])
    assert env["data"]["rs_vs_bench"] is not None
    assert env["data"]["pos_52w"] is not None
    assert env["data"]["sma150"] is not None
