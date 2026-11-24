"""Quant shared engine + helpers (used by quant_backtest / quant_stats)."""

from __future__ import annotations

import math
from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable


def _parse_day(label: str) -> Any:
    """Parse YYYY-MM-DD prefix; None when the label carries no date (vnstock day-only t)."""
    import datetime

    try:
        return datetime.date.fromisoformat(str(label).strip()[:10])
    except ValueError:
        return None


def _dated_closes(candles: list[dict[str, Any]]) -> tuple[list[Any], list[float], bool]:
    """Return (dates, closes, dates_missing): ``None`` marks a bar with no date.

    Dates are never invented (#137): a day-only label stays undated, and the
    third value says so, so a calendar filter can refuse instead of silently
    matching every bar. One undated bar no longer relabels the whole series.
    """
    closes = [float(c["c"]) for c in candles if c.get("c")]
    dates = [_parse_day(str(c.get("t", ""))) for c in candles if c.get("c")]
    return dates, closes, any(d is None for d in dates)


def _align_returns(
    series: dict[str, list[dict[str, Any]]],
) -> tuple[list[Any], dict[str, list[float]], bool]:
    """Inner-join daily closes on date; returns (dates, {symbol: returns}, missing).

    Undated bars are dropped rather than given a guessed business day, and the
    flag tells the caller that the joined window is shorter than the raw feed.
    """
    dated: dict[str, dict[Any, float]] = {}
    dates_missing = False
    for sym, candles in series.items():
        dates, closes, missing = _dated_closes(candles)
        dates_missing = dates_missing or missing
        dated[sym] = {d: c for d, c in zip(dates, closes, strict=True) if d is not None}
    common = sorted(set.intersection(*(set(d) for d in dated.values()))) if dated else []
    aligned: dict[str, list[float]] = {}
    for sym, mapping in dated.items():
        closes = [mapping[d] for d in common]
        aligned[sym] = [
            (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0
            for i in range(1, len(closes))
        ]
    return common, aligned, dates_missing


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


def _yf_closes(symbol: str) -> tuple[list[Any], list[float]]:
    """Yahoo daily closes + dates for non-VN condition assets (oil, gold...)."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        df = yf.Ticker(symbol).history(period="2y", auto_adjust=True)
        closes = [float(x) for x in df["Close"].tolist()]
        dates = [d.date() if hasattr(d, "date") else _parse_day(str(d)) for d in df.index]
    except Exception as exc:
        raise ProviderUnavailable(f"yfinance history failed for {symbol}") from exc
    if len(closes) < 30:
        raise ProviderBadData(f"too few yfinance bars for {symbol}")
    if any(d is None for d in dates):
        # #137: an index without observation dates must not fall back to today.
        raise ProviderBadData(f"yfinance history for {symbol} carries no usable dates")
    return dates, closes


def _condition_gate(
    stock_dates: list[Any],
    cond_dates: list[Any],
    cond_closes: list[float],
    rule: str,
    lookback: int,
) -> list[bool]:
    """Per-bar entries-allowed flag from a condition asset (aligned by date)."""
    import datetime as _dt
    import statistics

    # #137: undated condition bars carry no calendar position — drop them instead
    # of letting a ``None`` key match an undated stock bar.
    cmap = {
        d: c
        for d, c in zip(cond_dates, cond_closes, strict=False)
        if d is not None
    }
    lb = max(int(lookback), 2)

    def _value_on(d: Any) -> Any:
        """Exact date, else the nearest prior close within 5 calendar days."""
        c = cmap.get(d)
        if c is None and hasattr(d, "toordinal"):
            for back in range(1, 6):
                try:
                    cand = d - _dt.timedelta(days=back)
                except OverflowError:
                    break
                if cand in cmap:
                    return cmap[cand]
        return c

    # The same lookup feeds the current value and its history window: the history
    # used exact dates only, so every US holiday inside the window (a VN session with
    # no condition close) left it short and blocked entries for `lookback` bars.
    values = [_value_on(d) for d in stock_dates]
    out: list[bool] = []
    for i in range(len(stock_dates)):
        c = values[i]
        if c is None:
            out.append(False)  # missing observations cannot authorize entry
            continue
        hist = values[max(0, i - lb + 1) : i + 1]
        vals = [float(x) for x in hist if isinstance(x, (int, float)) and x == x]
        if len(vals) < lb:
            out.append(False)
            continue
        if rule == "rising":
            out.append(bool(vals[-1] > vals[0]))
        else:  # above_sma
            out.append(bool(vals[-1] > statistics.fmean(vals)))
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
    cond_ok: list[bool] | None = None,
    opens: list[float] | None = None,
) -> dict[str, Any]:
    """Long-only engine: buy_hold | sma_cross | momentum | rsi_meanrev.

    Trades count entries. months/quarters (1-12 / 1-4): entries only allowed on
    matching bars; off-window bars force flat (exits always allowed, so no stuck
    positions). rsi_meanrev: long when RSI14 < rsi_low, flat when RSI14 > rsi_high.
    cond_ok: optional per-bar entries-allowed flags from a condition asset.
    Missing cond_ok data blocks entry (F05b: missing can never authorize a trade).
    An undated bar can never satisfy a calendar filter (#137) — allowing it would
    turn the filter into a silent no-op; such bars are counted and reported.

    Fill convention (F05a, user-approved): a decision at close[i-1] fills at
    open[i] (next-bar-open) and the position accrues open-to-open until its exit
    fill. When `opens` is unavailable the engine falls back to next-bar-close
    fills and marks `fill="next-bar-close-fallback"` in the output. The final
    open position is marked to the last close. cost_bps is charged per side,
    once at each actual fill; final marking is not a liquidation.
    """
    import statistics

    n = len(closes)
    need = max(int(fast), int(slow), 15 if strategy == "rsi_meanrev" else 2) + 1
    if n < need or strategy not in ("buy_hold", "sma_cross", "momentum", "rsi_meanrev"):
        return {"trades": 0, "net_return": 0.0, "note": "too few bars or unknown strategy"}
    month_set = {int(m) for m in (months or []) if 1 <= int(m) <= 12} or None
    quarter_set = {int(q) for q in (quarters or []) if 1 <= int(q) <= 4} or None
    gated = bool(month_set or quarter_set)
    undated_blocked = 0

    def _bar_month(i: int) -> int | None:
        if not dates or i >= len(dates):
            return None
        d = dates[i]
        month = getattr(d, "month", None)
        if month is not None:
            try:
                return int(month)
            except (TypeError, ValueError):
                pass
        # CR6 (cross-review): ISO date STRINGS must gate too — silently treating
        # them as undated made month/quarter filters no-op for string dates.
        if isinstance(d, str):
            import datetime as _dt

            try:
                return int(_dt.date.fromisoformat(d[:10]).month)
            except (TypeError, ValueError):
                return None
        return None

    def _allowed(i: int) -> bool:
        nonlocal undated_blocked
        if not gated:
            base = True
        else:
            m = _bar_month(i)
            if m is None:
                # #137: an undated bar can never satisfy a calendar filter.
                undated_blocked += 1
                base = False
            elif month_set is not None and m not in month_set:
                base = False
            elif quarter_set is not None and (m - 1) // 3 + 1 not in quarter_set:
                base = False
            else:
                base = True
        if cond_ok is not None:
            # F05b: missing condition data can never authorize an entry.
            if i >= len(cond_ok) or cond_ok[i] is None:
                base = False
            else:
                base = base and bool(cond_ok[i])
        return base

    if strategy == "buy_hold":
        # Same gating contract as the other strategies: entries follow _allowed,
        # non-allowed bars force flat. month_filtered/cond gates are therefore
        # truthful for buy_hold too.
        pos = [1 if _allowed(i) else 0 for i in range(n)]
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
    fee = max(float(cost_bps), 0.0) / 10000  # per actual entry/exit fill

    # ---- F05a fill machinery -------------------------------------------------
    # A decision at close[i-1] fills at px[i] where px = opens (next-bar-open,
    # preferred) or closes (documented fallback). The position held during the
    # leg px[i-1] -> px[i] is the state decided at close[i-2]; equity accrues
    # px-to-px, fees apply at each fill, and a still-open position is marked to
    # the last close. If ANY open is None/0 the whole series falls back to
    # next-bar-close (never a partial mixed-price chain).
    if opens is not None and len(opens) == n:
        candidate = [float(o) if o is not None else None for o in opens]
        px_ok = all(p is not None and math.isfinite(p) and p > 0 for p in candidate)
    else:
        candidate, px_ok = None, False
    px: list[float]
    if px_ok and candidate is not None:
        px = [p for p in candidate if p is not None]  # px_ok: none of them is None
        fill_mode = "next-bar-open"
    else:
        px = list(closes)
        fill_mode = "next-bar-close-fallback"

    state = 0  # position decided at close[i-1], filled at px[i]
    in_pos = False
    entry_eq = 1.0
    trades = 0
    pnls: list[float] = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0

    def record_equity() -> None:
        nonlocal peak, max_dd
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else 0.0)

    prev_px = px[0] if px_ok else (closes[0] if closes else None)
    for i in range(1, n):
        leg_px = px[i] if px_ok else closes[i]
        if not leg_px or not prev_px:
            prev_px = leg_px
            continue
        leg_ret = (leg_px - prev_px) / prev_px
        if in_pos:
            equity *= 1 + leg_ret
            record_equity()
        prev_px = leg_px
        # decision made at close[i-1] fills at px[i]
        want = pos[i - 1]
        if want != state:
            if want == 1 and not in_pos:
                in_pos = True
                state = 1
                trades += 1
                entry_eq = equity
                equity *= 1 - fee
                record_equity()
            elif want == 0 and in_pos:
                in_pos = False
                state = 0
                equity *= 1 - fee
                record_equity()
                pnls.append(equity - entry_eq)
    if in_pos:
        # mark the final open position to the last close
        if prev_px:
            last_close = closes[-1] if closes else prev_px
            equity *= last_close / prev_px
            record_equity()
        pnls.append(equity - entry_eq)

    wins = sum(1 for p in pnls if p > 0)
    # Historical backtests deliberately contain old data: stale here describes
    # missing/invalid observation dates, not the age of the sample.
    stale = dates is None or len(dates) < n or any(d is None for d in dates)
    out: dict[str, Any] = {
        "trades": trades,
        "net_return": round(equity - 1, 4),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(wins / len(pnls), 4) if pnls else 0.0,
        "bars": n,
        "stale": stale,
        "fill": fill_mode,
        "date_basis": "observed" if not stale else "missing",
        "cost_basis": "bps per side at actual fills; final mark is not liquidation",
    }
    if stale:
        out["stale_note"] = "stale: observation dates are missing or invalid (never inferred)"
    if gated:
        out["month_filtered"] = True
        out["note"] = "entries only in selected months/quarters; exits always allowed"
        if undated_blocked:
            out["undated_bars_blocked"] = undated_blocked
            out["note"] += (
                f"; {undated_blocked} bars carry no observation date and never enter "
                "(a calendar filter cannot be checked without dates)"
            )
    return out
