"""Quant stats: risk, factors, correlation, seasonality, optimize, events."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.quant_shared import _align_returns, _dated_closes
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
)
from opentrading_mcp.tools.shared import (
    run_blocking as _run_blocking,
)


async def run_blocking(fn, tool, timeout_secs=60.0):
    """Compute-module alias: all blocking work here rides the heavy pool."""
    return await _run_blocking(fn, tool, timeout_secs, heavy=True)


def register_quant_stats_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def quant_risk(returns: list[float], periods_per_year: int = 252) -> dict[str, Any]:
        """Sharpe, sụt giảm tối đa và tỷ lệ thắng từ chuỗi lợi nhuận. Dùng khi chấm rủi ro một chiến
            lược/mô hình.

        Dùng khi: đánh giá backtest xong, "chiến lược này rủi ro thế nào".
        Không dùng khi: chưa có chuỗi return (lấy nến từ vn_quote_history/vn_equity_ohlcv rồi tự
            tính % thay đổi trước — KHÔNG gọi khi thiếu returns); cần thực hiện giao dịch thật (tool
            này chỉ tính số).

        returns: lợi nhuận đơn giản mỗi kỳ (BẮT BUỘC — tự dựng trước, ví dụ từ
        cột close của vn_quote_history lấy % thay đổi, hoặc closes của vn_equity_ohlcv).
        Không có tool nào tên risk_metrics — chính là tool này. periods_per_year: hệ số
        năm hóa cho Sharpe (252 ngày, 52 tuần, 12 tháng).
        Ví dụ: {"returns": [0.01, -0.005, 0.02], "periods_per_year": 252}.
        """
        fp = f"{returns}|{periods_per_year}"
        hit = await cache_lookup("quant_risk", fp)
        if hit is not None:
            return hit
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
        return await cache_store(
            "quant_risk",
            fp,
            TTL_SECONDS["overview"],
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
        fp = f"{symbol}|{lookback}"
        hit = await cache_lookup("quant_factors", fp)
        if hit is not None:
            return hit
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

        def _max_dd(prices: list[float]) -> float:
            """Largest peak-to-later-trough fall (0.08 = 8%); a rise is not a drawdown."""
            peak, worst = prices[0], 0.0
            for price in prices:
                peak = max(peak, price)
                worst = max(worst, (peak - price) / peak if peak else 0.0)
            return worst

        max_dd_full = _max_dd(closes)
        factors = {
            "symbol": symbol.upper(),
            "lookback": max(int(lookback), 30),
            # 20 sessions back is closes[-21] (closes[-20] was 19 sessions)
            "momentum_20d_pct": round((closes[-1] - closes[-21]) / closes[-21] * 100, 2),
            "vol_20d_ann_pct": round(statistics.pstdev(rets[-20:]) * (252**0.5) * 100, 2),
            # was (min - max) / max even when the low came before the high
            "max_dd_20d_pct": round(-_max_dd(closes[-20:]) * 100, 2),
            "max_dd_full_pct": round(max_dd_full * 100, 2),
        }
        return await cache_store(
            "quant_factors", fp, TTL_SECONDS["overview"],
            factors, source="computed-local",
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
        fp = f"{symbols}|{days}"
        hit = await cache_lookup("correlation_matrix", fp)
        if hit is not None:
            return hit
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
        return await cache_store(
            "correlation_matrix", fp, TTL_SECONDS["overview"],
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
        fp = f"{symbol}|{window}"
        hit = await cache_lookup("seasonality", fp)
        if hit is not None:
            return hit
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
        return await cache_store(
            "seasonality", fp, TTL_SECONDS["hour"],
            {
                "symbol": symbol.upper(),
                "window": win,
                "months": stats,
                "date_note": "business-day walkback (approx)" if walked else "upstream ISO dates",
            },
            source="computed-local",
        )

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
        fp = f"{symbols}|{objective}|{days}"
        hit = await cache_lookup("portfolio_optimize", fp)
        if hit is not None:
            return hit
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
        elif objective == "max_sharpe":  # closed form, clipped long-only
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
        return await cache_store(
            "portfolio_optimize", fp, TTL_SECONDS["hour"],
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
    async def event_study(
        symbol: str,
        dates: list[str],
        window_before: int = 10,
        window_after: int = 10,
        benchmark: str = "VNINDEX",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Abnormal returns around event dates vs benchmark. Use for event effects.

        dates: ISO event dates (pre-Tet, dividends, meetings); each needs
        window_before+window_after trading bars around it (nearest trading day
        within 3 days is used when the exact date is missing). CAR = cumulative
        (stock - benchmark) daily returns in %.
        """
        import datetime

        fp = f"{symbol}|{dates}|{window_before}|{window_after}|{benchmark}"
        hit = await cache_lookup("event_study", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"event_study {symbol} {len(dates or [])} dates")
        if not dates:
            return make_envelope(
                {"symbol": symbol.upper(), "events": 0, "rows": []},
                source="computed-local",
                warnings=["no event dates given"],
                availability="empty",
            )
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, 400),
                "event_study",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "event_study"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        warnings: list[str] = []
        try:
            bench_candles = await run_blocking(
                functools.partial(vn_p.quote_history, benchmark, 400),
                "event_study",
                timeout_secs=90.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            bench_candles = []
            warnings.append(f"benchmark unavailable — raw returns: {exc}")
        s_dates, s_closes, _ = _dated_closes(candles)
        b_dates, b_closes, _ = _dated_closes(bench_candles)
        s_map = dict(zip(s_dates, s_closes, strict=False))
        b_map = dict(zip(b_dates, b_closes, strict=False))
        common = sorted(set(s_map) & set(b_map)) if b_map else sorted(s_map)
        bwd = max(int(window_before), 1)
        fwd = max(int(window_after), 1)
        rows = []
        skipped = 0
        for raw in dates:
            try:
                target = datetime.date.fromisoformat(str(raw).strip()[:10])
            except ValueError:
                skipped += 1
                continue
            idx = next((i for i, d in enumerate(common) if d == target), None)
            note = None
            if idx is None:
                near = [(abs((d - target).days), i) for i, d in enumerate(common)]
                dist, idx = min(near, default=(99, None)) if near else (99, None)
                if idx is None or dist > 3:
                    skipped += 1
                    continue
                note = f"nearest trading day {common[idx]} (off by {dist}d)"
            if idx is None or idx - bwd < 0 or idx + fwd >= len(common):
                skipped += 1
                continue
            cars = []
            for k in range(idx - bwd + 1, idx + fwd + 1):
                d0, d1 = common[k - 1], common[k]
                rs = (s_map[d1] - s_map[d0]) / s_map[d0] if s_map[d0] else 0.0
                rb = (b_map[d1] - b_map[d0]) / b_map[d0] if d1 in b_map and b_map[d0] else 0.0
                cars.append(rs - rb)
            car = round(sum(cars) * 100, 2)
            stock_ret = (
                round(
                    (s_map[common[idx + fwd]] - s_map[common[idx - bwd]])
                    / s_map[common[idx - bwd]]
                    * 100,
                    2,
                )
                if s_map[common[idx - bwd]]
                else 0.0
            )
            rows.append(
                {
                    "date": str(target),
                    "used_date": str(common[idx]),
                    "car_pct": car,
                    "stock_ret_pct": stock_ret,
                    "bars": bwd + fwd,
                    "note": note,
                }
            )
        if not rows:
            return make_envelope(
                {"symbol": symbol.upper(), "events": 0, "rows": [], "skipped": skipped},
                source="computed-local",
                warnings=[*warnings, "no event had enough bars around it"],
                availability="empty",
            )
        cars_all = [float(r.get("car_pct") or 0.0) for r in rows]
        return await cache_store(
            "event_study",
            fp,
            TTL_SECONDS["hour"],
            {
                "symbol": symbol.upper(),
                "events": len(rows),
                "skipped": skipped,
                "window": [bwd, fwd],
                "benchmark": benchmark.upper(),
                "avg_car_pct": round(sum(cars_all) / len(cars_all), 2),
                "hit_rate": round(sum(1 for c in cars_all if c > 0) / len(cars_all), 4),
                "best_car_pct": max(cars_all),
                "worst_car_pct": min(cars_all),
                "rows": rows,
            },
            source="computed-local",
            warnings=warnings,
        )

    return [
        {"name": "quant_risk"},
        {"name": "quant_factors"},
        {"name": "correlation_matrix"},
        {"name": "seasonality"},
        {"name": "portfolio_optimize"},
        {"name": "event_study"},
    ]
