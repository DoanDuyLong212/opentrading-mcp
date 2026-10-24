"""Market timing: O'Neil distribution-day count + follow-through state.

Counting rules ported from Trading_Agents/wyckoff/timing.py
(distribution_days + follow_through), adapted to MCP candle rows
({t/o/h/l/c/v} or {time/open/high/low/close/volume}).

- Phiên phân phối: đóng cửa giảm >= 0.2% so với phiên trước VÀ volume cao
  hơn phiên trước. Chỉ tính cửa sổ 25 phiên gần nhất; phiên rớt khi quá
  25 phiên hoặc giá hồi +5% trên giá đóng của nó.
- Follow-through: sau nhịp giảm, Day 1 là phiên tăng đầu tiên từ đáy; FTD nổ
  từ Day 4 với tăng >= 1.25% + volume cao hơn; giữ ngày FTD đầu tiên để
  làm mốc đếm phiên phân phối;
  gãy khi low trong phiên thủng đáy Day 1; không bao giờ Day 2-3.
- Có FTD xác nhận thì đếm lại phiên phân phối từ đầu (rally mới xóa đếm cũ).
"""

from __future__ import annotations

import functools
import math
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
    in_vn_session,
    pick_value,
    price_ttl,
    run_blocking,
)

DD_DROP_PCT = 0.002
DD_WINDOW = 25
DD_RALLY_RESET = 0.05

FTD_FIRST_GAIN = 0.0125
FTD_MIN_DAY = 4
FTD_MAX_DAY = 25
FTD_LOOKBACK = 60

_CLOSE_KEYS = ("c", "close", "Close", "CLOSE")
_OPEN_KEYS = ("o", "open", "Open", "OPEN")
_HIGH_KEYS = ("h", "high", "High", "HIGH")
_LOW_KEYS = ("l", "low", "Low", "LOW")
_VOL_KEYS = ("v", "volume", "Volume", "VOLUME", "vol")
_DATE_KEYS = ("t", "time", "Time", "date", "Date")


def _bar_day(row: Any) -> str:
    """YYYY-MM-DD of a candle row ("" when it has no date)."""
    if not isinstance(row, dict):
        return ""
    return str(pick_value(row, _DATE_KEYS) or "")[:10]


def _series(
    rows: list[dict[str, Any]],
) -> tuple[list[float], list[float], list[float], list[str]] | None:
    """Extract parallel close/volume/low/date series; None when unusable."""
    closes, volumes, lows, dates = [], [], [], []
    for r in rows:
        if not isinstance(r, dict):
            return None
        try:
            c = float(pick_value(r, _CLOSE_KEYS))
            v = float(pick_value(r, _VOL_KEYS))
            lo = float(pick_value(r, _LOW_KEYS))
            raw_high = pick_value(r, _HIGH_KEYS)
            raw_open = pick_value(r, _OPEN_KEYS)
            hi = float(raw_high) if raw_high is not None else None
            op = float(raw_open) if raw_open is not None else None
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(x) for x in (c, v, lo)):
            return None
        if c <= 0 or v < 0 or lo <= 0 or lo > c:
            return None
        if hi is not None and (not math.isfinite(hi) or hi < max(c, lo)):
            return None
        if op is not None and (
            not math.isfinite(op) or op < lo or (hi is not None and op > hi)
        ):
            return None
        closes.append(c)
        volumes.append(v)
        lows.append(lo)
        # ISO date ("2026-10-22"), not the upstream "2026-10-22 00:00:00"; every
        # reader (distribution days, FTD state, the FTD cut) uses this same list.
        dates.append(_bar_day(r))
    if len(closes) < 6:
        return None
    return closes, volumes, lows, dates


def _distribution_days(
    closes: list[float], volumes: list[float], dates: list[str], window: int = DD_WINDOW
) -> list[dict[str, Any]]:
    """Active distribution days in the rolling window (oldest-first)."""
    n = len(closes)
    days: list[dict[str, Any]] = []
    for i in range(1, n):
        if closes[i - 1] <= 0 or volumes[i - 1] < 0:
            continue
        drop = closes[i] / closes[i - 1] - 1.0
        if drop <= -DD_DROP_PCT and volumes[i] > volumes[i - 1]:
            age = n - 1 - i
            if age >= window:
                continue
            invalidated = any(
                closes[j] >= closes[i] * (1.0 + DD_RALLY_RESET) for j in range(i + 1, n)
            )
            days.append(
                {
                    "date": dates[i],
                    "drop_pct": round(drop * 100, 2),
                    "age": age,
                    "invalidated": invalidated,
                }
            )
    return [d for d in days if not d["invalidated"]]


def _follow_through(
    closes: list[float],
    volumes: list[float],
    lows: list[float],
    dates: list[str],
    lookback: int = FTD_LOOKBACK,
) -> dict[str, Any]:
    """State machine for the latest rally attempt: none/rally_attempt/confirmed/failed/stale.

    A failed attempt stays the answer only until the next Day 1: once a new attempt
    starts, it is reported, and the failed one moves to `last_failed`.
    """
    n = len(closes)
    none: dict[str, Any] = {
        "state": "none",
        "day1_date": None,
        "day1_low": None,
        "ftd_date": None,
        "ftd_gain_pct": None,
        "days_since_day1": None,
    }
    if n < 6:
        return none
    start = max(0, n - lookback)

    def pack(state: str, day1: int, day1_low: float, ftd: int | None) -> dict[str, Any]:
        return {
            "state": state,
            "day1_date": dates[day1],
            "day1_low": round(day1_low, 2),
            "ftd_date": dates[ftd] if ftd is not None else None,
            "ftd_gain_pct": (
                round(closes[ftd] / closes[ftd - 1] * 100 - 100, 2)
                if ftd is not None
                else None
            ),
            "days_since_day1": n - 1 - day1,
        }

    rolling_low = lows[start]
    day1: int | None = None
    day1_low = 0.0
    ftd: int | None = None
    outcome = dict(none)
    last_failed: dict[str, Any] | None = None
    j = start + 1
    while j < n:
        # Apply each closed bar in order. A break of an existing attempt takes
        # precedence over any close-based recovery or FTD on that same bar.
        if day1 is not None and lows[j] < day1_low:
            outcome = pack("failed", day1, day1_low, ftd)
            last_failed = {
                "day1_date": dates[day1],
                "day1_low": round(day1_low, 2),
                "failed_date": dates[j],
            }
            day1, ftd = None, None
            rolling_low = lows[j]
            j += 1
            continue
        if day1 is None:
            # Keep the existing close-up Day 1 policy. If a bar makes a new low,
            # do not also start a new attempt on its recovering close.
            if lows[j] < rolling_low:
                rolling_low = lows[j]
            elif closes[j] > closes[j - 1]:
                day1, day1_low, ftd = j, rolling_low, None
                if outcome["state"] == "failed":
                    # a new attempt replaces the failed one as the latest
                    outcome = dict(none)
            j += 1
            continue
        if ftd is None and j - day1 + 1 >= FTD_MIN_DAY:
            gain = closes[j] / closes[j - 1] - 1.0
            if gain >= FTD_FIRST_GAIN and volumes[j] > volumes[j - 1]:
                ftd = j
                outcome = pack("confirmed", day1, day1_low, ftd)
        j += 1
    if day1 is not None:
        if ftd is not None:
            # Retain the first FTD anchor while refreshing the attempt's age.
            outcome = pack("confirmed", day1, day1_low, ftd)
        elif outcome["state"] == "none":
            age = n - 1 - day1
            outcome = pack("stale" if age > FTD_MAX_DAY else "rally_attempt", day1, day1_low, ftd)
    if last_failed is not None and outcome["state"] != "failed":
        outcome["last_failed"] = last_failed
    return outcome


def _status(count: int) -> tuple[str, str]:
    """Risk level over the 25-session window: status key + VI reading of it.

    The reading describes the market state under O'Neil's rule; it is not a
    buy/sell instruction (the harness never gives one).
    """
    if count <= 2:
        return (
            "binh_thuong",
            "0-2 phiên: theo quy tắc O'Neil, xu hướng tăng chưa có dấu hiệu bị phân phối.",
        )
    if count == 3:
        return (
            "quan_sat",
            "3 phiên: theo quy tắc O'Neil, mức cần quan sát — áp lực bán bắt đầu tích lũy.",
        )
    if count == 4:
        return (
            "canh_bao",
            "4 phiên: theo quy tắc O'Neil, mức cảnh báo — áp lực phân phối đã rõ.",
        )
    if count == 5:
        return (
            "canh_bao_cao",
            "5 phiên: theo quy tắc O'Neil, mức cảnh báo cao — xu hướng tăng có nguy cơ gãy.",
        )
    return (
        "nguy_hiem",
        "Trên 5 phiên: theo quy tắc O'Neil, mức nguy hiểm — xu hướng tăng thường đã gãy, "
        "chờ một follow-through mới để xác nhận nhịp hồi.",
    )


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool, "reason": reason},
        source="unavailable",
        warnings=[reason],
        availability="unavailable",
    )


def register_market_timing_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def distribution_count(
        symbol: str = "VNINDEX", days: int = 40, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Đếm phiên phân phối O'Neil + trạng thái follow-through. Dùng khi đánh giá
        rủi ro chung của thị trường theo O'Neil.

        Dùng khi: "thị trường có bao nhiêu phiên phân phối", "thị trường đang rủi ro tới
        mức nào", kiểm tra sức khỏe xu hướng theo O'Neil.
        Không dùng khi: rủi ro 1 mã cụ thể (dùng stock_forensic/insider_trading/sentiment_score);
        cần độ rộng toàn sàn (dùng breadth_scan); backtest quy tắc (dùng backtest_strategies).

        symbol: chỉ số VN (mặc định VNINDEX). days: số nến ngày lấy về (mặc định 40,
        tối đa 90); đếm trong 25 phiên gần nhất, chỉ tính phiên đã đóng cửa.
        Mức theo số phiên: 0-2 binh_thuong; 3 quan_sat; 4 canh_bao; 5 canh_bao_cao;
        trên 5 nguy_hiem. Đây là đọc trạng thái thị trường, không phải lệnh mua/bán.
        Có FTD xác nhận thì đếm lại phiên phân phối từ đầu (rally mới xóa đếm cũ).
        Ví dụ: {"symbol": "VNINDEX", "days": 40}.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        sym = (symbol or "VNINDEX").strip().upper()
        want = max(30, min(int(days or 40), 90))
        # Date in fp (VN calendar, not the server's): a new session must recompute.
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        fp = f"v4|{sym}|{want}|{today}"  # v4: finite OHLC, first FTD stays the reset anchor
        hit = await cache_lookup("distribution_count", fp)
        if hit is not None:
            return hit
        try:
            rows = await run_blocking(
                functools.partial(vn_p.index_ohlcv, sym, want, "1D"),
                "distribution_count",
                timeout_secs=60.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("distribution_count", str(exc))
        if not isinstance(rows, list) or not rows:
            return _na("distribution_count", "không có nến chỉ số")
        warnings: list[str] = []
        if in_vn_session() and rows and _bar_day(rows[-1]) == today:
            # O'Neil judges a session at the close: today's bar still has partial volume.
            rows = rows[:-1]
            warnings.append("bỏ nến hôm nay vì phiên chưa đóng cửa")
        parsed = _series(rows)
        if parsed is None:
            return _na("distribution_count", "nến thiếu close/volume/low")
        closes, volumes, lows, dates = parsed

        ftd = _follow_through(closes, volumes, lows, dates)
        reset = False
        if ftd["state"] == "confirmed" and ftd["ftd_date"]:
            try:
                cut = dates.index(ftd["ftd_date"])
            except ValueError:
                cut = -1
            if cut >= 0:
                # Rally mới xóa đếm cũ: chỉ đếm các phiên từ FTD trở đi.
                closes, volumes, dates = closes[cut:], volumes[cut:], dates[cut:]
                reset = True

        active = _distribution_days(closes, volumes, dates)
        count = len(active)
        key, guidance = _status(count)
        hi = max(closes[-DD_WINDOW:]) if len(closes) >= DD_WINDOW else max(closes)
        decline = round(closes[-1] / hi * 100 - 100, 2) if hi else 0.0
        return await cache_store(
            "distribution_count",
            fp,
            # Short in session (a bar closes at 15:00), long when no session can move it.
            price_ttl(),
            {
                "symbol": sym,
                "window_sessions": DD_WINDOW,
                "distribution_days": active,
                "count_25": count,
                "status": key,
                "guidance": guidance,
                "reset_on_ftd": reset,
                "ftd": ftd,
                "decline_from_high_pct": decline,
            },
            source="vnstock",
            warnings=warnings,
            data_time=dates[-1] or None,
        )

    return [{"name": "distribution_count"}]
