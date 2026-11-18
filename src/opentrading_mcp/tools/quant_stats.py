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


async def run_blocking(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
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
        Dates inner-join on observed ISO dates only; undated bars are dropped
        from the join, never given a guessed calendar day (#137, see date_note).
        """
        # v2: undated bars are dropped from the join, never guessed (#137).
        fp = f"v2|{symbols}|{days}"
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
        common, aligned, dates_missing = _align_returns(fetched)
        if len(common) < 21:
            reason = (
                "no common observation dates: bars carry no dates and dates are never "
                "invented (#137)"
                if dates_missing and not common
                else "fewer than 20 common dates"
            )
            return make_envelope(
                {"symbols": universe},
                source="vnstock",
                warnings=[reason],
                availability="unavailable" if dates_missing and not common else "empty",
            )
        warn: list[str] = []
        if dates_missing:
            warn.append(
                "some bars carry no observation date; they are dropped from the join, "
                "never given a guessed calendar day"
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
                "date_note": (
                    "observed ISO dates; undated bars dropped from the join"
                    if dates_missing
                    else "upstream ISO dates"
                ),
            },
            source="computed-local",
            warnings=warn or None,
            availability="partial" if dates_missing else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def seasonality(
        symbol: str, window: int = 21, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Rolling-window return stats per calendar month. Use for seasonal bias.

        window: trading days per window, 5-63 (21 ~= month). Buckets by window
        end month; bars without an observation date are skipped, never given a
        guessed calendar day (#137).
        """
        # v2: undated bars are skipped, never given a guessed month (#137).
        fp = f"v2|{symbol}|{window}"
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
        dates, closes, dates_missing = _dated_closes(candles)
        months: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        undated = 0
        for i in range(win, len(closes)):
            if not closes[i - win]:
                continue
            d = dates[i] if i < len(dates) else None
            if d is None:
                undated += 1
                continue
            months[d.month].append(closes[i] / closes[i - win] - 1)
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
        if not stats:
            return make_envelope(
                {"symbol": symbol.upper(), "window": win, "months": {}},
                source="computed-local",
                warnings=[
                    "no observation dates in the candle series; seasonality buckets by "
                    "calendar month and dates are never invented (#137)"
                ],
                availability="unavailable",
            )
        warn: list[str] = []
        if dates_missing:
            warn.append(
                f"{undated} window ends carry no observation date; they are skipped, "
                "never assigned a guessed calendar month"
            )
        return await cache_store(
            "seasonality", fp, TTL_SECONDS["hour"],
            {
                "symbol": symbol.upper(),
                "window": win,
                "months": stats,
                "date_note": (
                    "observed ISO dates; undated window ends skipped"
                    if dates_missing
                    else "upstream ISO dates"
                ),
            },
            source="computed-local",
            warnings=warn or None,
            availability="partial" if dates_missing else None,
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
        # v2: undated bars are dropped from the join, never guessed (#137).
        fp = f"v2|{symbols}|{objective}|{days}"
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
        common, aligned, dates_missing = _align_returns(fetched)
        if len(common) < 31:
            reason = (
                "no common observation dates: bars carry no dates and dates are never "
                "invented (#137)"
                if dates_missing and not common
                else "fewer than 30 common dates"
            )
            return make_envelope(
                {"symbols": universe},
                source="vnstock",
                warnings=[reason],
                availability="unavailable" if dates_missing and not common else "empty",
            )
        warn: list[str] = []
        if dates_missing:
            warn.append(
                "some bars carry no observation date; they are dropped from the join, "
                "never given a guessed calendar day"
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
            warnings=warn or None,
            availability="partial" if dates_missing else None,
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

        # v2: undated bars are dropped from the maps, never guessed (#137).
        fp = f"v2|{symbol}|{dates}|{window_before}|{window_after}|{benchmark}"
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
        # #137: undated bars carry no calendar position — drop them, never guess a day.
        s_map = {d: c for d, c in zip(s_dates, s_closes, strict=False) if d is not None}
        b_map = {d: c for d, c in zip(b_dates, b_closes, strict=False) if d is not None}
        if not s_map:
            return make_envelope(
                {"tool": "event_study"},
                source="unavailable",
                warnings=[
                    "no observation dates in the candle series; event windows need real "
                    "dates and dates are never invented (#137)"
                ],
                availability="unavailable",
            )
        if bench_candles and not b_map:
            warnings.append(
                f"benchmark {benchmark} carries no observation dates; raw returns only"
            )
        common = sorted(set(s_map) & set(b_map)) if b_map else sorted(s_map)
        bwd = max(int(window_before), 1)
        fwd = max(int(window_after), 1)
        rows: list[dict[str, Any]] = []
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

    @server.tool(annotations=READ_ONLY)
    async def series_stats(
        symbols: list[str],
        window: int = 60,
        metrics: list[str] | None = None,
        benchmark: str | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Mean, stdev, total return, annualised vol and rank over N sessions.

        Dùng khi: "so sánh 3 mã 60 phiên qua", "mã nào mạnh nhất", "độ biến động
            60 phiên", "relative strength so với VNINDEX".
        Không dùng khi: chỉ cần giá một mã (vn_quote_history); đã có chuỗi return
            và chỉ cần Sharpe/drawdown (quant_risk).

        symbols: tối đa 30 mã. window: số phiên (2-250, mặc định 60).
        metrics: tập con của mean_return_pct, stdev_return_pct, total_return_pct,
        vol_ann_pct, relative_strength_pct (viết tắt mean/stdev/total_return/vol/
        relative_strength cũng được; mặc định tất cả); rank luôn có.
        benchmark: mã chỉ số/cổ phiếu để tính relative strength (ví dụ VNINDEX).

        Dates inner-join; nến không có ngày bị loại và được ghi cảnh báo, không
        đoán ngày (#137). Trả kèm inputs đã dùng (first/last date, sessions,
        adjusted) và `units`.
        """
        allowed = (
            "mean_return_pct",
            "stdev_return_pct",
            "total_return_pct",
            "vol_ann_pct",
            "relative_strength_pct",
        )
        aliases = {
            "mean": "mean_return_pct",
            "stdev": "stdev_return_pct",
            "total_return": "total_return_pct",
            "vol": "vol_ann_pct",
            "relative_strength": "relative_strength_pct",
        }
        selected = [
            aliases.get(str(m).strip().lower(), str(m).strip().lower())
            for m in (metrics or allowed)
        ]
        selected = list(dict.fromkeys(m for m in selected if m in allowed))
        if not selected:
            return make_envelope(
                {"tool": "series_stats"},
                source="local",
                warnings=[f"metrics must be a subset of {', '.join(allowed)}"],
                availability="empty",
            )
        sessions = max(2, min(int(window), 250))
        universe = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))[:30]
        if not universe:
            return make_envelope(
                {"tool": "series_stats"},
                source="local",
                warnings=["need at least 1 symbol"],
                availability="empty",
            )
        bench = benchmark.strip().upper() if benchmark and benchmark.strip() else None
        fp = f"v1|{'/'.join(universe)}|{sessions}|{','.join(selected)}|{bench or ''}"
        hit = await cache_lookup("series_stats", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"series_stats {universe} window={sessions}")
        warn: list[str] = []
        try:
            fetched: dict[str, list[dict[str, Any]]] = {}
            for sym in universe:
                fetched[sym] = await run_blocking(
                    functools.partial(vn_p.quote_history, sym, sessions + 1),
                    "series_stats",
                    timeout_secs=90.0,
                )
            if bench is not None:
                try:
                    fetched[bench] = await run_blocking(
                        functools.partial(vn_p.quote_history, bench, sessions + 1),
                        "series_stats",
                        timeout_secs=90.0,
                    )
                except (ProviderUnavailable, ProviderBadData) as exc:
                    warn.append(f"benchmark {bench} unavailable: {exc}")
                    bench = None
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "series_stats"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        common, aligned, dates_missing = _align_returns(fetched)
        if len(common) < 2:
            return make_envelope(
                {"symbols": universe},
                source="vnstock",
                warnings=[
                    "no two common observation dates: bars carry no dates and "
                    "dates are never invented (#137)"
                ],
                availability="empty",
            )
        import statistics

        def _compound_pct(rets: list[float]) -> float:
            equity = 1.0
            for ret in rets:
                equity *= 1.0 + ret
            return (equity - 1.0) * 100.0

        bench_returns = aligned.get(bench or "", [])
        bench_total = _compound_pct(bench_returns[-sessions:]) if bench else None
        rows: list[dict[str, Any]] = []
        for sym in universe:
            rets = aligned[sym][-sessions:]
            if not rets:
                continue
            mean = statistics.fmean(rets)
            stdev = statistics.pstdev(rets)
            total = _compound_pct(rets)
            row: dict[str, Any] = {"symbol": sym, "sessions": len(rets)}
            if "mean_return_pct" in selected:
                row["mean_return_pct"] = round(mean * 100, 4)
            if "stdev_return_pct" in selected:
                row["stdev_return_pct"] = round(stdev * 100, 4)
            if "total_return_pct" in selected:
                row["total_return_pct"] = round(total, 4)
            if "vol_ann_pct" in selected:
                row["vol_ann_pct"] = round(stdev * (252**0.5) * 100, 4)
            if "relative_strength_pct" in selected and bench_total is not None:
                row["relative_strength_pct"] = round(total - bench_total, 4)
            row["_total"] = total
            rows.append(row)
        if not rows:
            return make_envelope(
                {"symbols": universe},
                source="vnstock",
                warnings=[*warn, "no symbol had at least one return in the window"],
                availability="empty",
            )
        totals = sorted((row["_total"] for row in rows), reverse=True)
        for row in rows:
            row["rank"] = 1 + sum(1 for value in totals if value > row["_total"] + 1e-12)
            row.pop("_total")
        rows.sort(key=lambda row: row["rank"])
        used = min(len(aligned[sym]) for sym in universe)
        used = min(used, sessions)
        if used < sessions:
            warn.append(
                f"chỉ có {used} phiên chung trong cửa sổ {sessions} phiên được yêu cầu"
            )
        if dates_missing:
            warn.append(
                "một số nến không có ngày nên đã bị loại khỏi cửa sổ, không đoán ngày"
            )
        first_date = common[-(used + 1)].isoformat()
        last_date = common[-1].isoformat()
        return await cache_store(
            "series_stats",
            fp,
            TTL_SECONDS["overview"],
            {
                "rows": rows,
                "inputs": {
                    "window": sessions,
                    "sessions": used,
                    "first_date": first_date,
                    "last_date": last_date,
                    "adjusted": "vnstock default (not controlled by this tool)",
                    "benchmark": bench,
                    "dates_missing": dates_missing,
                },
                "as_of": last_date,
                "method": (
                    "close-to-close daily returns over the common dates; total return "
                    "compounds the window; vol annualised with 252 sessions; relative "
                    "strength = symbol total return - benchmark total return"
                ),
            },
            source="computed-local",
            warnings=warn or None,
            availability="partial" if dates_missing else None,
        )

    return [
        {"name": "quant_risk"},
        {"name": "quant_factors"},
        {"name": "correlation_matrix"},
        {"name": "seasonality"},
        {"name": "portfolio_optimize"},
        {"name": "event_study"},
        {"name": "series_stats"},
    ]
