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
        symbol: str,
        cost_bps: float = 10.0,
        strategy: str = "buy_hold",
        slippage_bps: float = 5.0,
        benchmark: str = "VNINDEX",
        ctx: AnyContext | None = None,
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
        net = gross - (cost_bps + slippage_bps) / 10000 * 2
        if ctx is not None:
            await ctx.report_progress(2, 2, "done")
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "strategy": strategy,
                "benchmark": benchmark,
                "gross_return": round(gross, 4),
                "net_return": round(net, 4),
                "bars": len(closes),
                "cost_bps": cost_bps,
                "slippage_bps": slippage_bps,
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def quant_risk(returns: list[float], periods_per_year: int = 252) -> dict[str, Any]:
        """Sharpe, max drawdown and win rate from a return series. Use to gate models."""
        if not returns:
            return make_envelope({"note": "empty series"}, source="local", availability="empty")
        import statistics

        mean = statistics.fmean(returns)
        std = statistics.pstdev(returns) or 1e-9
        annualize = max(int(periods_per_year), 1) ** 0.5
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
                "sharpe_proxy": round(mean / std * annualize, 4),
                "max_drawdown": round(max_dd, 4),
                "win_rate": round(wins / len(returns), 4),
                "n": len(returns),
                "periods_per_year": max(int(periods_per_year), 1),
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def quant_factors(symbol: str = "VCB", lookback: int = 60) -> dict[str, Any]:
        """Momentum, volatility and drawdown factors from candles. Use to expand features."""
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, max(int(lookback), 30) + 20),
                "quant_factors",
                timeout_secs=60.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "quant_factors"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        if len(closes) < 30:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        import statistics

        window = closes[-20:]
        peak = closes[0]
        max_dd_full = 0.0
        for price in closes:
            peak = max(peak, price)
            max_dd_full = max(max_dd_full, (peak - price) / peak if peak else 0.0)
        factors = {
            "symbol": symbol.upper(),
            "lookback": max(int(lookback), 30),
            "momentum_20d_pct": round((closes[-1] - closes[-20]) / closes[-20] * 100, 2),
            "vol_20d_ann_pct": round(statistics.pstdev(rets[-20:]) * (252**0.5) * 100, 2),
            "max_dd_20d_pct": round((min(window) - max(window)) / max(window) * 100, 2),
            "max_dd_full_pct": round(max_dd_full * 100, 2),
        }
        return make_envelope(factors, source="computed-local")

    @server.tool(annotations=READ_ONLY)
    async def scenario_simulate(
        scenario: str, symbol: str = "VCB", shock_pct: float = -5.0
    ) -> dict[str, Any]:
        """Apply a price shock to latest close and report P/L per 1000 shares. Use for sizing."""
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 10),
                "scenario_simulate",
                timeout_secs=60.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "scenario_simulate"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        if not closes:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        last = closes[-1]
        shocked = round(last * (1 + shock_pct / 100), 2)
        return make_envelope(
            {
                "scenario": scenario,
                "symbol": symbol.upper(),
                "last_close": last,
                "shock_pct": shock_pct,
                "shocked_price": shocked,
                "pnl_per_1000_shares": round((shocked - last) * 1000, 0),
                "assumptions": ["linear shock, no liquidity slippage"],
            },
            source="computed-local",
        )

    return [
        {"name": "quant_backtest"},
        {"name": "quant_risk"},
        {"name": "quant_factors"},
        {"name": "scenario_simulate"},
    ]
