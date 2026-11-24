"""Worker loops: pump realtime snapshots into Redis for web + tools.

- yf_loop: yfinance global/commodities (works from anywhere).
- dnse_ws_loop: DNSE WS (HMAC auth, JSON encoding) -> per-symbol snapshot
  keys every 5s. Needs a Vietnam egress IP; Singapore/timeout >>> skip with
  backoff instead of crashing. Outside market hours the server sends no data;
  snapshots are then flagged stale but kept for graceful reads.
- heartbeat_loop: liveness marker.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any

from opentrading_mcp.cache import TTL_SECONDS, cache_key
from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.store import cache_set
from opentrading_mcp.schemas import utc_now_iso
from opentrading_mcp.vn_time import VN_TZ

SYMBOLS_OHLC = ["VN30F1M"]
INDICES = ["VNINDEX", "VN30"]

# Phiên DNSE (giờ Việt Nam, thứ Hai-thứ Sáu): 09:00-11:30 và 13:00-15:00.
# Nghỉ trưa 11:30-13:00 server không gửi data → recv timeout 30s → reconnect,
# churn log/CPU (#144). Ngoài phiên: ngủ tới phiên kế tiếp thay vì giữ vòng
# connect. Ngày lễ: DNSE working-dates (best-effort, cache 6h); không có lịch
# thì chỉ bỏ cuối tuần + log, không bao giờ bỏ nhầm một phiên thật.
# VN không có DST → offset cố định +07:00 (vn_time.VN_TZ), không cần tzdata.
DNSE_SESSIONS = ((9, 0, 11, 30), (13, 0, 15, 0))
DNSE_START_HOUR = DNSE_SESSIONS[0][0]
DNSE_END_HOUR = DNSE_SESSIONS[-1][2]
_TRADING_DAYS_TTL = 6 * 3600.0
_TRADING_DAYS: tuple[float, frozenset[str]] = (0.0, frozenset())


def _vn(now: datetime | None = None) -> datetime:
    """`now` về múi giờ VN; naive được hiểu là giờ VN."""
    moment = now or datetime.now(VN_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _day(now: datetime | None = None) -> datetime:
    return _vn(now).replace(hour=0, minute=0, second=0, microsecond=0)


def dnse_sessions(now: datetime | None = None) -> list[tuple[datetime, datetime]]:
    """Hai phiên [start, end) của ngày chứa `now` (09:00-11:30, 13:00-15:00)."""
    day = _day(now)
    out: list[tuple[datetime, datetime]] = []
    for start_h, start_m, end_h, end_m in DNSE_SESSIONS:
        out.append(
            (
                day.replace(hour=start_h, minute=start_m),
                day.replace(hour=end_h, minute=end_m),
            )
        )
    return out


def dnse_session(now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """Phiên chứa `now`, hoặc None khi nghỉ trưa / ngoài giờ / cuối tuần."""
    moment = _vn(now)
    if moment.weekday() >= 5:
        return None
    for start, end in dnse_sessions(moment):
        if start <= moment < end:
            return start, end
    return None


def dnse_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Cả ngày [09:00, 15:00) giờ VN (giữ cho caller cũ; phiên tách ở nghỉ trưa)."""
    moment = _vn(now)
    start = moment.replace(hour=DNSE_START_HOUR, minute=0, second=0, microsecond=0)
    end = moment.replace(hour=DNSE_END_HOUR, minute=0, second=0, microsecond=0)
    return start, end


def dnse_off_hours(now: datetime | None = None) -> bool:
    """True nếu không nằm trong phiên giao dịch nào (gồm nghỉ trưa, cuối tuần)."""
    return dnse_session(now) is None


def _is_trading_day(day: datetime, trading_days: frozenset[str] | None) -> bool:
    """Weekday, and not a holiday proven by a calendar that actually covers `day`."""
    if day.weekday() >= 5:
        return False
    if not trading_days:
        return True
    iso = day.date().isoformat()
    if iso in trading_days:
        return True
    # Absence proves a holiday only while the calendar still reaches this day.
    return iso > max(trading_days)


def _next_session_start(
    now: datetime | None = None, trading_days: frozenset[str] | None = None
) -> datetime:
    moment = _vn(now)
    day = _day(moment)
    if _is_trading_day(day, trading_days):
        for start, _end in dnse_sessions(day):
            if moment < start:
                return start
    for offset in range(1, 15):
        candidate = day + timedelta(days=offset)
        if _is_trading_day(candidate, trading_days):
            return candidate.replace(hour=DNSE_SESSIONS[0][0], minute=DNSE_SESSIONS[0][1])
    return day + timedelta(days=1)


def _seconds_until_open(
    now: datetime | None = None, trading_days: frozenset[str] | None = None
) -> float:
    """Số giây tới đầu phiên kế tiếp (0 khi đang trong phiên), bỏ trưa/cuối tuần/lễ."""
    moment = _vn(now)
    if dnse_session(moment) is not None:
        return 0.0
    return max(0.0, (_next_session_start(moment, trading_days) - moment).total_seconds())


def _parse_trading_days(payload: Any) -> frozenset[str]:
    """Ngày giao dịch (ISO) từ payload DNSE ``/market/working-dates``."""
    rows: Any = payload
    if isinstance(payload, dict):
        rows = next(
            (payload[key] for key in ("dates", "tradingDays", "workingDates", "data")
             if isinstance(payload.get(key), list)),
            [],
        )
    out: set[str] = set()
    if isinstance(rows, list):
        for row in rows:
            value = row.get("date") if isinstance(row, dict) else row
            if isinstance(value, str) and len(value) >= 10:
                out.add(value[:10])
    return frozenset(out)


async def _exchange_trading_days() -> frozenset[str] | None:
    """Lịch giao dịch DNSE (cache 6h); None khi không lấy được (thuần thứ 2-6)."""
    global _TRADING_DAYS
    fetched, days = _TRADING_DAYS
    if days and time.time() - fetched < _TRADING_DAYS_TTL:
        return days
    try:
        payload = await asyncio.wait_for(asyncio.to_thread(dnse_p.working_dates), timeout=10)
    except Exception as exc:
        _log(
            f"dnse trading calendar unavailable ({type(exc).__name__}: {exc}); "
            "weekday-only sleep"
        )
        _TRADING_DAYS = (time.time(), frozenset())
        return None
    days = _parse_trading_days(payload)
    _TRADING_DAYS = (time.time(), days)
    return days or None


def _log(message: str) -> None:
    print(f"[loops] {message}", file=sys.stderr, flush=True)


async def yf_loop(interval_seconds: int = 60) -> None:
    while True:
        try:
            cache_set(
                cache_key("yf_global_indices", "loop"),
                {"indices": yf_p.batch_last(yf_p.GLOBAL_9), "fetched_at": utc_now_iso()},
                TTL_SECONDS["world"],
            )
            cache_set(
                cache_key("yf_commodities", "loop"),
                {"items": yf_p.batch_last(yf_p.COMMO_13), "fetched_at": utc_now_iso()},
                TTL_SECONDS["world"],
            )
            _log("yf loop pumped")
        except Exception as exc:
            _log(f"yf loop skipped: {exc}")
        await asyncio.sleep(interval_seconds)


async def heartbeat_loop(interval_seconds: int = 30) -> None:
    while True:
        cache_set("mcp:health:worker", {"ts": time.time()}, interval_seconds * 2)
        _log("heartbeat")
        await asyncio.sleep(interval_seconds)


def _pick(message: dict[str, Any], *names: str, default: Any = 0) -> Any:
    for name in names:
        if message.get(name) not in (None, ""):
            return message[name]
    return default


async def dnse_ws_loop(publish_seconds: int = 5) -> None:
    try:
        import importlib.util

        if importlib.util.find_spec("websockets") is None:
            raise ImportError("websockets")
    except ImportError:
        _log("dnse ws skipped: websockets not installed")
        return
    api_key = os.environ.get("DNSE_API_KEY", "").strip()
    api_secret = os.environ.get("DNSE_SECRET", "").strip()
    if not api_key or not api_secret:
        _log("dnse ws skipped: DNSE_API_KEY/SECRET not set")
        return
    backoff = 5
    while True:
        if dnse_off_hours():
            wait = _seconds_until_open(trading_days=await _exchange_trading_days())
            _log(f"dnse ws ngoài phiên: tạm dừng {int(wait)}s tới phiên kế tiếp")
            await asyncio.sleep(wait)
            continue
        try:
            await _dnse_ws_once(api_key, api_secret, publish_seconds)
            backoff = 5
        except Exception as exc:
            _log(f"dnse ws error: {type(exc).__name__}: {exc} (retry in {backoff}s)")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


async def _dnse_ws_once(api_key: str, api_secret: str, publish_seconds: int) -> None:
    import websockets

    state: dict[str, Any] = {"ohlc": {}, "index": {}, "foreign": {}}
    last_publish = 0.0
    async with websockets.connect(dnse_p.WS_URL, ping_interval=15, ping_timeout=10) as ws:
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        _log(f"dnse connected sid={welcome.get('sid') or welcome.get('session_id')}")
        ts = int(time.time())
        nonce = str(int(time.time() * 1_000_000))
        await ws.send(json.dumps(dnse_p.build_ws_auth(api_key, api_secret, ts, nonce)))
        auth = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if auth.get("action") != "auth_success":
            raise RuntimeError(f"dnse auth failed: {auth}")
        _log("dnse authenticated")
        await ws.send(json.dumps(dnse_p.build_ws_subscribe("ohlc.1.json", SYMBOLS_OHLC)))
        for index in INDICES:
            await ws.send(json.dumps(dnse_p.build_ws_subscribe(f"market_index.{index}.json", [])))
        await ws.send(json.dumps(dnse_p.build_ws_subscribe("foreign.*.json", SYMBOLS_OHLC)))
        session = dnse_session()
        window_end = session[1] if session else dnse_window()[1]
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except TimeoutError:
                _log("dnse recv timeout, reconnecting")
                return
            if _vn() >= window_end:
                _log(f"dnse ws hết phiên {window_end:%H:%M}: ngắt kết nối tới phiên sau")
                return
            data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
            if data.get("action") == "ping":
                await ws.send(json.dumps({"action": "pong"}))
                continue
            kind = data.get("T")
            now = time.time()
            if kind in ("b", "bc"):
                symbol = str(_pick(data, "symbol", "Symbol", "s", default=""))
                if symbol:
                    state["ohlc"][symbol] = {
                        "symbol": symbol,
                        "open": float(_pick(data, "open", "Open", "o", default=0)),
                        "high": float(_pick(data, "high", "High", "h", default=0)),
                        "low": float(_pick(data, "low", "Low", "l", default=0)),
                        "close": float(_pick(data, "close", "Close", "c", default=0)),
                        "volume": int(_pick(data, "volume", "Volume", "v", default=0)),
                        "time": _pick(data, "time", "Time", "t", default=int(now)),
                    }
            elif kind == "mi":
                name = str(_pick(data, "indexName", "IndexName", default=""))
                if name:
                    state["index"][name] = {
                        "indexName": name,
                        "value": _pick(data, "valueIndexes", "ValueIndexes"),
                        "change": _pick(data, "changedValue", "ChangedValue"),
                        "pct": _pick(data, "changedRatio", "ChangedRatio"),
                    }
            elif kind == "f":
                symbol = str(data.get("Symbol", ""))
                if symbol:
                    buy = float(data.get("BuyTradedAmount", 0) or 0)
                    sell = float(data.get("SellTradedAmount", 0) or 0)
                    state["foreign"][symbol] = {"buy": buy, "sell": sell, "net": buy - sell}
            if now - last_publish >= publish_seconds:
                _publish_dnse_snapshot(state, now)
                last_publish = now


def _publish_dnse_snapshot(state: dict[str, Any], now: float) -> None:
    for symbol, ohlc in state["ohlc"].items():
        cache_set(
            f"mcp:market:dnse_ws_snapshot:{symbol}",
            {"ohlc": ohlc, "stale": now - float(ohlc.get("time", now)) > 300},
            30,
        )
    for name, index in state["index"].items():
        # Issue #38: foreign dict chỉ chứa flow của WS_FOREIGN_SCOPE (VN30F1M),
        # không phải toàn thị trường — payload phải mang nhãn scope.
        payload = {
            "index": index,
            "foreign": state["foreign"],
            "foreign_scope": dnse_p.WS_FOREIGN_SCOPE,
        }
        cache_set(f"mcp:market:dnse_ws_snapshot:{name}", payload, 30)
    if state["foreign"]:
        cache_set(
            "mcp:market:dnse_ws_foreign",
            {"scope": dnse_p.WS_FOREIGN_SCOPE, "flow": state["foreign"]},
            30,
        )
    if state["ohlc"] or state["index"]:
        _log(f"dnse snapshot pumped ohlc={len(state['ohlc'])} idx={len(state['index'])}")


async def main_async() -> None:
    from opentrading_mcp.snapshots import snapshot_loop

    await asyncio.gather(yf_loop(), heartbeat_loop(), dnse_ws_loop(), snapshot_loop())


def start_in_web_loops() -> None:
    """Run the light loops inside the web process (Render free has no worker).

    Gated by MCP_LOOPS (0 disables; local stdio never calls this). Runs on a
    dedicated daemon thread with its own event loop, so a slow pump (yfinance
    TLS, DNSE backoff) can never stall /mcp. snapshot_loop stays worker-only:
    it is a heavy once-a-day batch, pointless on a host that sleeps.
    """
    import threading

    if os.environ.get("MCP_LOOPS", "1") == "0":
        return

    async def _run() -> None:
        await asyncio.gather(yf_loop(), heartbeat_loop(), dnse_ws_loop())

    def _boot() -> None:
        try:
            asyncio.run(_run())
        except Exception as exc:  # pragma: no cover - background pump
            _log(f"in-web loops exited: {exc}")

    threading.Thread(target=_boot, name="in-web-loops", daemon=True).start()
    _log("in-web loops started (yf + heartbeat + dnse-ws)")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
