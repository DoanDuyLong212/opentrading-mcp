"""Quant preset: backtest, factors, risk, labels, scenario (sandbox local)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def _parse_day(label: str) -> Any:
    """Parse YYYY-MM-DD prefix; None when the label carries no date (vnstock day-only t)."""
    import datetime

    try:
        return datetime.date.fromisoformat(str(label).strip()[:10])
    except ValueError:
        return None


def _calendar_map(n: int) -> list[Any]:
    """Business-day walkback ending today (fallback when candles carry no dates)."""
    import datetime

    days: list[Any] = []
    day = datetime.date.today()
    while len(days) < max(n, 1):
        if day.weekday() < 5:
            days.append(day)
        day -= datetime.timedelta(days=1)
    return list(reversed(days))


def _dated_closes(candles: list[dict[str, Any]]) -> tuple[list[Any], list[float], bool]:
    """Return (dates, closes, walked): ISO dates when present, else walkback mapping."""
    closes = [float(c["c"]) for c in candles if c.get("c")]
    parsed = [_parse_day(str(c.get("t", ""))) for c in candles if c.get("c")]
    if all(d is not None for d in parsed) and parsed:
        return parsed, closes, False
    return _calendar_map(len(closes)), closes, True


def _align_returns(
    series: dict[str, list[dict[str, Any]]],
) -> tuple[list[Any], dict[str, list[float]], bool]:
    """Inner-join daily closes on date; returns (dates, {symbol: returns})."""
    dated: dict[str, dict[Any, float]] = {}
    walked = False
    for sym, candles in series.items():
        dates, closes, w = _dated_closes(candles)
        walked = walked or w
        dated[sym] = dict(zip(dates, closes, strict=True))
    common = sorted(set.intersection(*(set(d) for d in dated.values()))) if dated else []
    aligned: dict[str, list[float]] = {}
    for sym, mapping in dated.items():
        closes = [mapping[d] for d in common]
        aligned[sym] = [
            (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0
            for i in range(1, len(closes))
        ]
    return common, aligned, walked


def _rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder RSI per bar (None until warmed up); pure python for the engine."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(closes)):
        if i > period:
            chg = closes[i] - closes[i - 1]
            avg_g = (avg_g * (period - 1) + max(chg, 0.0)) / period
            avg_l = (avg_l * (period - 1) + max(-chg, 0.0)) / period
        if avg_l == 0:
            out[i] = 100.0 if avg_g > 0 else 50.0
        else:
            out[i] = 100 - 100 / (1 + avg_g / avg_l)
    return out


def _run_strategy(
    closes: list[float],
    strategy: str,
    fast: int,
    slow: int,
    cost_bps: float,
    dates: list[Any] | None = None,
    rsi_low: float = 30.0,
    rsi_high: float = 70.0,
    months: list[int] | None = None,
    quarters: list[int] | None = None,
) -> dict[str, Any]:
    """Long-only engine: buy_hold | sma_cross | momentum | rsi_meanrev.

    Trades count entries. months/quarters (1-12 / 1-4): entries only allowed on
    matching bars; off-window bars force flat (exits always allowed, so no stuck
    positions). rsi_meanrev: long when RSI14 < rsi_low, flat when RSI14 > rsi_high.
    """
    import statistics

    n = len(closes)
    need = max(int(fast), int(slow), 15 if strategy == "rsi_meanrev" else 2) + 1
    if n < need or strategy not in ("buy_hold", "sma_cross", "momentum", "rsi_meanrev"):
        return {"trades": 0, "net_return": 0.0, "note": "too few bars or unknown strategy"}
    month_set = {int(m) for m in (months or []) if 1 <= int(m) <= 12} or None
    quarter_set = {int(q) for q in (quarters or []) if 1 <= int(q) <= 4} or None
    gated = bool(month_set or quarter_set)

    def _bar_month(i: int) -> int | None:
        if not dates or i >= len(dates):
            return None
        d = dates[i]
        month = getattr(d, "month", None)
        try:
            return int(month) if month is not None else None
        except (TypeError, ValueError):
            return None

    def _allowed(i: int) -> bool:
        if not gated:
            return True
        m = _bar_month(i)
        if m is None:
            return True  # undated bars never block
        if month_set is not None and m not in month_set:
            return False
        if quarter_set is not None and (m - 1) // 3 + 1 not in quarter_set:
            return False
        return True

    if strategy == "buy_hold":
        pos = [1] * n
    elif strategy == "sma_cross":
        f = max(int(fast), 2)
        s = max(int(slow), f + 1)
        sma_f = [
            statistics.fmean(closes[i - f + 1 : i + 1]) if i >= f - 1 else None for i in range(n)
        ]
        sma_s = [
            statistics.fmean(closes[i - s + 1 : i + 1]) if i >= s - 1 else None for i in range(n)
        ]
        pos = []
        for i in range(n):
            long = False
            if i >= s - 1:
                fast_v = sma_f[i]
                slow_v = sma_s[i]
                long = fast_v is not None and slow_v is not None and fast_v > slow_v
            pos.append(1 if long and _allowed(i) else 0)
    elif strategy == "momentum":
        lb = max(int(slow), 2)
        pos = [1 if i >= lb and closes[i] > closes[i - lb] and _allowed(i) else 0 for i in range(n)]
    else:  # rsi_meanrev: enter oversold, exit overbought, hold between
        rsi = _rsi_series(closes)
        pos = []
        state = 0
        for i in range(n):
            r = rsi[i]
            if r is None:
                pos.append(0)
                continue
            if r < float(rsi_low):
                state = 1
            elif r > float(rsi_high):
                state = 0
            pos.append(state if _allowed(i) else 0)
    fee = max(float(cost_bps), 0.0) / 10000 * 2  # in+out per flip
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    trades = 0
    pnls: list[float] = []
    entry_eq = 0.0
    in_pos = False
    for i in range(1, n):
        if pos[i - 1] and not in_pos:
            in_pos = True
            trades += 1
            entry_eq = equity
            equity *= 1 - fee
        if not pos[i - 1] and in_pos:
            in_pos = False
            pnls.append(equity - entry_eq)
        ret = (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0
        equity *= 1 + (pos[i - 1] * ret)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else 0.0)
    if in_pos:
        pnls.append(equity - entry_eq)
    wins = sum(1 for p in pnls if p > 0)
    out: dict[str, Any] = {
        "trades": trades,
        "net_return": round(equity - 1, 4),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(wins / len(pnls), 4) if pnls else 0.0,
        "bars": n,
    }
    if gated:
        out["month_filtered"] = True
        out["note"] = "entries only in selected months/quarters; exits always allowed"
    return out


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
        """Buy-and-hold backtest with costs over available history. Use for baseline stats.

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
        """Sharpe, max drawdown and win rate from a return series. Use to gate models.

        returns: per-period simple returns. periods_per_year: annualization
        factor for Sharpe (252 daily, 52 weekly, 12 monthly).
        """
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
        """Momentum, volatility and drawdown factors from candles. Use to expand features.

        lookback: daily closes fetched (20d factor windows fixed); also adds
        max_dd_full_pct over the full window.
        """
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
    async def correlation_matrix(
        symbols: list[str], days: int = 90, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Pairwise Pearson correlation of daily returns. Use for diversification reads.

        symbols: up to 8 tickers (same market). days: daily bars each.
        Dates inner-join; vnstock day-only labels fall back to business-day
        walkback (see date_note).
        """
        if ctx is not None:
            await ctx.log("info", f"correlation_matrix {symbols}")
        universe = [s.strip().upper() for s in symbols if s.strip()][:8]
        if len(universe) < 2:
            return make_envelope(
                {"tool": "correlation_matrix"},
                source="unavailable",
                warnings=["need at least 2 symbols"],
                availability="unavailable",
            )
        import numpy as np

        try:
            fetched: dict[str, list[dict[str, Any]]] = {}
            for sym in universe:
                fetched[sym] = await run_blocking(
                    functools.partial(vn_p.quote_history, sym, max(int(days), 30) + 5),
                    "correlation_matrix",
                    timeout_secs=90.0,
                )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "correlation_matrix"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        common, aligned, walked = _align_returns(fetched)
        if len(common) < 21:
            return make_envelope(
                {"symbols": universe},
                source="vnstock",
                warnings=["fewer than 20 common dates"],
                availability="empty",
            )
        matrix = np.corrcoef([aligned[s] for s in universe])
        table = {
            a: {b: round(float(matrix[i][j]), 4) for j, b in enumerate(universe)}
            for i, a in enumerate(universe)
        }
        return make_envelope(
            {
                "symbols": universe,
                "common_dates": len(common),
                "matrix": table,
                "date_note": "business-day walkback (approx)" if walked else "upstream ISO dates",
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def seasonality(
        symbol: str, window: int = 21, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Rolling-window return stats per calendar month. Use for seasonal bias.

        window: trading days per window, 5-63 (21 ~= month). Buckets by window
        end month; vnstock day-only labels use business-day walkback.
        """
        if ctx is not None:
            await ctx.log("info", f"seasonality {symbol}")
        import statistics

        win = min(max(int(window), 5), 63)
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 400),
                "seasonality",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "seasonality"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        dates, closes, walked = _dated_closes(candles)
        months: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        for i in range(win, len(closes)):
            if not closes[i - win]:
                continue
            months[dates[i].month].append(closes[i] / closes[i - win] - 1)
        stats = {}
        for m in range(1, 13):
            rs = months[m]
            if not rs:
                continue
            stats[str(m)] = {
                "n": len(rs),
                "mean_pct": round(statistics.fmean(rs) * 100, 2),
                "median_pct": round(statistics.median(rs) * 100, 2),
                "hit_rate": round(sum(1 for r in rs if r > 0) / len(rs), 2),
                "best_pct": round(max(rs) * 100, 2),
                "worst_pct": round(min(rs) * 100, 2),
            }
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "window": win,
                "months": stats,
                "date_note": "business-day walkback (approx)" if walked else "upstream ISO dates",
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
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Rule-based backtests beyond buy-and-hold. Use to compare timing rules.

        strategy: 'sma_cross' (fast SMA over slow), 'momentum' (close over
        close[slow] ago), 'rsi_meanrev' (long when RSI14 < rsi_low, flat when
        RSI14 > rsi_high), 'buy_hold'. fast/slow: lookback bars. cost_bps:
        in+out bps deducted per position flip. months/quarters: entries only on
        matching calendar months (1-12) / quarters (1-4); exits always allowed.
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
        warn: list[str] = []
        if months or quarters:
            warn.append(
                "month-filtered: entries only in "
                f"months={months} quarters={quarters}; exits always allowed"
            )
        return make_envelope(out, source="computed-local", warnings=warn)

    @server.tool(annotations=READ_ONLY)
    async def portfolio_optimize(
        symbols: list[str],
        objective: str = "max_sharpe",
        days: int = 180,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Long-only weights by rule. Use for allocation starting points.

        objective: 'equal', 'inv_vol' (1/sigma), 'max_sharpe' (closed-form
        long-only heuristic, no scipy). days: daily bars each (max 8 symbols).
        """
        if ctx is not None:
            await ctx.log("info", f"portfolio_optimize {symbols} {objective}")
        if objective not in ("equal", "inv_vol", "max_sharpe"):
            return make_envelope(
                {"tool": "portfolio_optimize"},
                source="unavailable",
                warnings=[f"unknown objective {objective!r}"],
                availability="unavailable",
            )
        import numpy as np

        universe = [s.strip().upper() for s in symbols if s.strip()][:8]
        if len(universe) < 2:
            return make_envelope(
                {"tool": "portfolio_optimize"},
                source="unavailable",
                warnings=["need at least 2 symbols"],
                availability="unavailable",
            )
        try:
            fetched = {}
            for sym in universe:
                fetched[sym] = await run_blocking(
                    functools.partial(vn_p.quote_history, sym, max(int(days), 60) + 5),
                    "portfolio_optimize",
                    timeout_secs=90.0,
                )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "portfolio_optimize"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        common, aligned, _ = _align_returns(fetched)
        if len(common) < 31:
            return make_envelope(
                {"symbols": universe},
                source="vnstock",
                warnings=["fewer than 30 common dates"],
                availability="empty",
            )
        rets = np.array([aligned[s] for s in universe])
        vols = rets.std(axis=1)
        notes = ["long-only heuristic; rebalance and costs not modeled"]
        raw: Any = np.ones(len(universe))
        if objective == "inv_vol":
            raw = 1 / np.where(vols > 0, vols, np.nan)
            raw = np.where(np.isnan(raw), 0.0, raw)
            if raw.sum() == 0:
                raw = np.ones(len(universe))
                notes.append("zero volatility; fell back to equal")
        else:  # max_sharpe closed form, clipped long-only
            mu = np.clip(rets.mean(axis=1), 0, None)
            cov = np.cov(rets) + np.eye(len(universe)) * 1e-6
            try:
                raw = np.linalg.solve(cov, mu)
            except Exception:
                raw = np.ones(len(universe))
                notes.append("singular covariance; fell back to equal")
            raw = np.clip(raw, 0, None)
            if raw.sum() == 0:
                raw = np.ones(len(universe))
                notes.append("non-positive expected returns; fell back to equal")
        weights = np.array([round(float(w), 6) for w in raw / raw.sum()])
        weights = weights / weights.sum()
        port = (rets * weights[:, None]).sum(axis=0)
        stats = {
            "ann_vol_pct": round(float(port.std() * (252**0.5) * 100), 2),
            "sharpe_proxy": round(float(port.mean() / (port.std() or 1e-9) * (252**0.5)), 4),
        }
        return make_envelope(
            {
                "symbols": universe,
                "objective": objective,
                "weights": {s: float(w) for s, w in zip(universe, weights, strict=True)},
                "common_dates": len(common),
                "notes": notes,
                **stats,
            },
            source="computed-local",
        )

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
        {"name": "quant_risk"},
        {"name": "quant_factors"},
        {"name": "scenario_simulate"},
        {"name": "correlation_matrix"},
        {"name": "seasonality"},
        {"name": "backtest_strategies"},
        {"name": "portfolio_optimize"},
        {"name": "param_sweep"},
    ]
