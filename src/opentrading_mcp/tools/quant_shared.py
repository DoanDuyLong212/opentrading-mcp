"""Quant shared engine + helpers (used by quant_backtest / quant_stats)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable


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


def _yf_closes(symbol: str) -> tuple[list[Any], list[float]]:
    """Yahoo daily closes + dates for non-VN condition assets (oil, gold...)."""
    import datetime

    try:
        import yfinance as yf
    except ImportError as exc:
        raise ProviderUnavailable("yfinance not installed") from exc
    try:
        df = yf.Ticker(symbol).history(period="2y", auto_adjust=True)
        closes = [float(x) for x in df["Close"].tolist()]
        dates = [d.date() if hasattr(d, "date") else datetime.date.today() for d in df.index]
    except Exception as exc:
        raise ProviderUnavailable(f"yfinance history failed for {symbol}") from exc
    if len(closes) < 30:
        raise ProviderBadData(f"too few yfinance bars for {symbol}")
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

    cmap = dict(zip(cond_dates, cond_closes, strict=False))
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
            out.append(True)  # no condition data: never block
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
) -> dict[str, Any]:
    """Long-only engine: buy_hold | sma_cross | momentum | rsi_meanrev.

    Trades count entries. months/quarters (1-12 / 1-4): entries only allowed on
    matching bars; off-window bars force flat (exits always allowed, so no stuck
    positions). rsi_meanrev: long when RSI14 < rsi_low, flat when RSI14 > rsi_high.
    cond_ok: optional per-bar entries-allowed flags from a condition asset.
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
            base = True
        else:
            m = _bar_month(i)
            if m is None:
                base = True  # undated bars never block
            elif month_set is not None and m not in month_set:
                base = False
            elif quarter_set is not None and (m - 1) // 3 + 1 not in quarter_set:
                base = False
            else:
                base = True
        if cond_ok is not None and i < len(cond_ok):
            base = base and bool(cond_ok[i])
        return base

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
