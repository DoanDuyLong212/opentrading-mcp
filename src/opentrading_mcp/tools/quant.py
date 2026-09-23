"""Quant preset: backtest, factors, risk, labels, scenario (sandbox local)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def register_quant_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def quant_backtest(
        symbol: str, cost_bps: float = 10.0, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Buy-and-hold backtest with costs over available history. Use for baseline stats."""
        if ctx is not None:
            await ctx.report_progress(0, 2, "load candles")
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 365),
                "quant_backtest",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "quant_backtest"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        if len(closes) < 2:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        gross = closes[-1] / closes[0] - 1
        net = gross - cost_bps / 10000 * 2
        if ctx is not None:
            await ctx.report_progress(2, 2, "done")
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "gross_return": round(gross, 4),
                "net_return": round(net, 4),
                "bars": len(closes),
                "cost_bps": cost_bps,
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def quant_risk(returns: list[float]) -> dict[str, Any]:
        """Sharpe, max drawdown and win rate from a return series. Use to gate models."""
        if not returns:
            return make_envelope({"note": "empty series"}, source="local", availability="empty")
        import statistics

        mean = statistics.fmean(returns)
        std = statistics.pstdev(returns) or 1e-9
        equity = 1.0
        max_dd = 0.0
        peak_eq = 1.0
        for r in returns:
            equity *= 1 + r
            peak_eq = max(peak_eq, equity)
            max_dd = max(max_dd, (peak_eq - equity) / peak_eq)
        wins = sum(1 for r in returns if r > 0)
        return make_envelope(
            {
                "sharpe_proxy": round(mean / std, 4),
                "max_drawdown": round(max_dd, 4),
                "win_rate": round(wins / len(returns), 4),
                "n": len(returns),
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def quant_factors() -> dict[str, Any]:
        """Factor mining sandbox status. Use to expand the feature universe."""
        return make_envelope(
            {"sandbox": "local", "factors": []}, source="local", availability="empty"
        )

    @server.tool(annotations=READ_ONLY)
    async def scenario_simulate(scenario: str) -> dict[str, Any]:
        """What-if simulation with explicit assumptions. Use for sizing under uncertainty."""
        return make_envelope(
            {"scenario": scenario, "result": "stub: wire simulate.py next"},
            source="stub",
            availability="empty",
        )

    return [
        {"name": "quant_backtest"},
        {"name": "quant_risk"},
        {"name": "quant_factors"},
        {"name": "scenario_simulate"},
    ]
