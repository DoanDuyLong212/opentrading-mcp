"""Market timing: O'Neil distribution-day count + follow-through state.

Counting rules ported from Trading_Agents/wyckoff/timing.py
(distribution_days + follow_through), adapted to MCP candle rows
({t/o/h/l/c/v} or {time/open/high/low/close/volume}).

- Phiên phân phối: đóng cửa giảm >= 0.2% so với phiên trước VÀ volume cao
  hơn phiên trước. Chỉ tính cửa sổ 25 phiên gần nhất; phiên rớt khi quá
  25 phiên hoặc giá hồi +5% trên giá đóng của nó.
- Follow-through: sau nhịp giảm, Day 1 là phiên tăng đầu tiên từ đáy; FTD nổ
  từ Day 4 với tăng >= 1.25% + volume cao hơn (>= 1.0% cho xác nhận lần 2);
  gãy khi thủng đáy Day 1; không bao giờ Day 2-3.
- Có FTD xác nhận thì đếm lại phiên phân phối từ đầu (rally mới xóa đếm cũ).
"""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
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
    pick_value,
    run_blocking,
)

DD_DROP_PCT = 0.002
DD_WINDOW = 25
DD_RALLY_RESET = 0.05

FTD_FIRST_GAIN = 0.0125
FTD_CONFIRM_GAIN = 0.01
FTD_MIN_DAY = 4
FTD_MAX_DAY = 25
FTD_LOOKBACK = 60

_CLOSE_KEYS = ("c", "close", "Close", "CLOSE")
_HIGH_KEYS = ("h", "high", "High", "HIGH")
_LOW_KEYS = ("l", "low", "Low", "LOW")
_VOL_KEYS = ("v", "volume", "Volume", "VOLUME", "vol")
_DATE_KEYS = ("t", "time", "Time", "date", "Date")


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
        except (TypeError, ValueError):
            return None
        if c <= 0 or v < 0:
            return None
        closes.append(c)
        volumes.append(v)
        lows.append(lo)
        dates.append(str(pick_value(r, _DATE_KEYS) or ""))
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
    """State machine for the latest rally attempt: none/rally_attempt/confirmed/failed/stale."""
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
    j = start + 1
    while j < n:
        if day1 is None:
            if lows[j] < rolling_low:
                rolling_low = lows[j]
            elif closes[j] > closes[j - 1]:
                day1, day1_low, ftd = j, rolling_low, None
            j += 1
            continue
        if closes[j] < day1_low:
            outcome = pack("failed", day1, day1_low, ftd)
            day1, ftd = None, None
            rolling_low = lows[j]
            j += 1
            continue
        if j - day1 + 1 >= FTD_MIN_DAY:
            gain = closes[j] / closes[j - 1] - 1.0
            thresh = FTD_FIRST_GAIN if ftd is None else FTD_CONFIRM_GAIN
            if gain >= thresh and volumes[j] > volumes[j - 1]:
                ftd = j
                outcome = pack("confirmed", day1, day1_low, ftd)
        j += 1
    if day1 is not None and outcome["state"] == "none":
        age = n - 1 - day1
        outcome = pack("stale" if age > FTD_MAX_DAY else "rally_attempt", day1, day1_low, ftd)
    return outcome


def _status(count: int) -> tuple[str, str]:
    """User thresholds over a 1-month window: status key + VI guidance."""
    if count <= 2:
        return "binh_thuong", "0-2 phiên: không vấn đề, xu hướng tăng được xác nhận."
    if count == 3:
        return "quan_sat", "3 phiên: quan sát, thận trọng với vị thế mua mới."
    if count == 4:
        return "tim_dau_hieu_ban", "4 phiên: tìm dấu hiệu bán, thắt chặt cắt lỗ, không mua đuổi."
    if count == 5:
        return (
            "thoat_moi_co_hoi",
            "5 phiên: tìm mọi cơ hội để thoát, chỉ giữ vị thế có đệm lãi dày.",
        )
    return "nguy_hiem", "Trên 5 phiên: nguy hiểm, nên thoát và đứng ngoài cho tới FTD mới."


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
        rủi ro thị trường (có nên giữ/mua hay thoát).

        Dùng khi: "thị trường có bao nhiêu phiên phân phối", "có nên thoát hàng không",
        kiểm tra sức khỏe xu hướng theo O'Neil.
        Không dùng khi: rủi ro 1 mã cụ thể (dùng stock_forensic/insider_trading/sentiment_score);
        cần độ rộng toàn sàn (dùng breadth_scan); backtest quy tắc (dùng backtest_strategies).

        symbol: chỉ số VN (mặc định VNINDEX). days: số nến ngày lấy về (mặc định 40,
        tối đa 90); đếm trong 25 phiên gần nhất.
        Ngưỡng 1 tháng: 1-2 không vấn đề; 3 quan sát; 4 tìm dấu hiệu bán; 5 tìm mọi cơ hội
        để thoát; trên 5 nguy hiểm nên thoát.
        Có FTD xác nhận thì đếm lại phiên phân phối từ đầu (rally mới xóa đếm cũ).
        Ví dụ: {"symbol": "VNINDEX", "days": 40}.
        """
        sym = (symbol or "VNINDEX").strip().upper()
        want = max(30, min(int(days or 40), 90))
        # Date in fp: derived from daily candles, a new session must recompute.
        from datetime import date

        fp = f"{sym}|{want}|{date.today().isoformat()}"
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
            TTL_SECONDS["financeinfo"],  # daily-candle derived; fp carries the date
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
        )

    return [{"name": "distribution_count"}]
