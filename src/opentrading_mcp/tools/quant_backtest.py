"""Quant backtest: backtest, sweep, scenario (sandbox local)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.quant_shared import (
    _condition_gate,
    _dated_closes,
    _run_strategy,
    _yf_closes,
)
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def register_quant_backtest_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def quant_backtest(
        symbol: str,
        cost_bps: float = 10.0,
        strategy: str = "buy_hold",
        slippage_bps: float = 5.0,
        benchmark: str = "VNINDEX",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Buy-and-hold backtest with costs over available history. Use for baseline stats.

        Deprecated for strategies: use backtest_strategies (real SMA/momentum/RSI
        engine) for anything beyond buy-and-hold baseline.
        strategy: recorded label only (engine is buy-and-hold). cost_bps/slippage_bps:
        round-trip bps each deducted twice from gross. benchmark: reference index label.
        """
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
        base = closes[0] or 1.0
        curve = [round(c / base - 1.0, 4) for c in closes]
        step = max(1, len(curve) // 100)
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
                "equity_curve": curve[::step],
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def scenario_simulate(
        scenario: str, symbol: str = "VCB", shock_pct: float = -5.0
    ) -> dict[str, Any]:
        """Apply a price shock to latest close and report P/L per 1000 shares. Use for sizing.

        shock_pct: percent shock, negative for drops (e.g. -5.0).
        """
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

    @server.tool(annotations=READ_ONLY)
    async def backtest_strategies(
        symbol: str,
        strategy: str = "sma_cross",
        fast: int = 10,
        slow: int = 30,
        cost_bps: float = 10.0,
        rsi_low: float = 30.0,
        rsi_high: float = 70.0,
        months: list[int] | None = None,
        quarters: list[int] | None = None,
        condition_symbol: str | None = None,
        condition_rule: str = "above_sma",
        condition_lookback: int = 20,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Rule-based backtests beyond buy-and-hold. Use to compare timing rules.

        strategy: 'sma_cross' (fast SMA over slow), 'momentum' (close over
        close[slow] ago), 'rsi_meanrev' (long when RSI14 < rsi_low, flat when
        RSI14 > rsi_high), 'buy_hold'. fast/slow: lookback bars. cost_bps:
        in+out bps deducted per position flip. months/quarters: entries only on
        matching calendar months (1-12) / quarters (1-4); exits always allowed.
        condition_symbol: gate entries on another asset (oil/gold/FX: BZ=F, GC=F,
        USDVND...); condition_rule 'above_sma' (over its SMA) or 'rising'
        (up over condition_lookback bars). VN symbols via vnstock, others via
        yfinance daily history.
        """
        if ctx is not None:
            await ctx.log("info", f"backtest_strategies {symbol} {strategy}")
        if strategy not in ("sma_cross", "momentum", "buy_hold", "rsi_meanrev"):
            return make_envelope(
                {"tool": "backtest_strategies"},
                source="unavailable",
                warnings=[f"unknown strategy {strategy!r}"],
                availability="unavailable",
            )
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 365),
                "backtest_strategies",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "backtest_strategies"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        dates, closes, _walked = _dated_closes(candles)
        cond_ok: list[bool] | None = None
        cond_warn: list[str] = []
        if condition_symbol:
            csym = condition_symbol.strip().upper()
            rule = (condition_rule or "above_sma").strip().lower()
            if rule not in ("above_sma", "rising"):
                return make_envelope(
                    {"tool": "backtest_strategies"},
                    source="unavailable",
                    warnings=[f"unknown condition_rule {condition_rule!r}"],
                    availability="unavailable",
                )
            cd: list[Any] | None = None
            cc: list[float] | None = None
            try:
                cc_candles = await run_blocking(
                    functools.partial(vn_p.quote_history, csym, 400),
                    "backtest_strategies",
                    timeout_secs=60.0,
                )
                cd, cc, _ = _dated_closes(cc_candles)
            except (ProviderUnavailable, ProviderBadData):
                try:
                    cd, cc = await run_blocking(
                        functools.partial(_yf_closes, csym),
                        "backtest_strategies",
                        timeout_secs=60.0,
                    )
                except (ProviderUnavailable, ProviderBadData) as exc2:
                    return make_envelope(
                        {"tool": "backtest_strategies"},
                        source="unavailable",
                        warnings=[f"condition asset {csym} unavailable: {exc2}"],
                        availability="unavailable",
                    )
            assert cd is not None and cc is not None
            cond_ok = _condition_gate(dates, cd, cc, rule, condition_lookback)
            cond_warn.append(
                f"condition-gated on {csym} ({rule}/{condition_lookback}); exits always allowed"
            )
        res = _run_strategy(
            closes,
            strategy,
            fast,
            slow,
            cost_bps,
            dates=dates,
            rsi_low=rsi_low,
            rsi_high=rsi_high,
            months=months,
            quarters=quarters,
            cond_ok=cond_ok,
        )
        out: dict[str, Any] = {
            "symbol": symbol.upper(),
            "strategy": strategy,
            "fast": fast,
            "slow": slow,
            "cost_bps": cost_bps,
            **res,
        }
        if strategy == "rsi_meanrev":
            out["rsi_low"] = rsi_low
            out["rsi_high"] = rsi_high
        if months or quarters:
            out["months"] = months
            out["quarters"] = quarters
        if condition_symbol:
            out["condition_symbol"] = condition_symbol.strip().upper()
            out["condition_rule"] = (condition_rule or "above_sma").strip().lower()
            out["condition_lookback"] = condition_lookback
        warn: list[str] = []
        if months or quarters:
            warn.append(
                "month-filtered: entries only in "
                f"months={months} quarters={quarters}; exits always allowed"
            )
        warn.extend(cond_warn)
        return make_envelope(out, source="computed-local", warnings=warn)

    @server.tool(annotations=READ_ONLY)
    async def param_sweep(
        symbol: str,
        strategy: str = "sma_cross",
        fast_range: list[int] | None = None,
        slow_range: list[int] | None = None,
        cost_bps: float = 10.0,
        months: list[int] | None = None,
        quarters: list[int] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Grid-search strategy lookbacks, ranked by net return. Use to avoid overfit picks.

        fast_range/slow_range: candidate bars (product capped at 30 combos).
        rsi_meanrev allowed (fixed 30/70 thresholds). months/quarters passthrough.
        """
        if ctx is not None:
            await ctx.log("info", f"param_sweep {symbol} {strategy}")
        if strategy not in ("sma_cross", "momentum", "rsi_meanrev"):
            return make_envelope(
                {"tool": "param_sweep"},
                source="unavailable",
                warnings=[f"sweep supports sma_cross|momentum|rsi_meanrev, got {strategy!r}"],
                availability="unavailable",
            )
        fasts = [max(int(f), 2) for f in (fast_range or [5, 10, 20])][:6]
        slows = [max(int(s), 3) for s in (slow_range or [20, 30, 60])][:6]
        combos = [(f, s) for f in fasts for s in slows if s > f][:30]
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 365),
                "param_sweep",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "param_sweep"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        closes = [c["c"] for c in candles if c["c"]]
        dates, _, _ = _dated_closes(candles)
        ranked = []
        for f, s in combos:
            res = _run_strategy(
                closes,
                strategy,
                f,
                s,
                cost_bps,
                dates=dates,
                months=months,
                quarters=quarters,
            )
            ranked.append({"fast": f, "slow": s, **res})
        ranked.sort(key=lambda r: r["net_return"], reverse=True)
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "strategy": strategy,
                "combos_evaluated": len(ranked),
                "months": months,
                "quarters": quarters,
                "ranked": ranked,
            },
            source="computed-local",
        )

    return [
        {"name": "quant_backtest"},
        {"name": "scenario_simulate"},
        {"name": "backtest_strategies"},
        {"name": "param_sweep"},
    ]
