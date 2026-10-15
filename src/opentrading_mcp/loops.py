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
from typing import Any

from opentrading_mcp.cache import TTL_SECONDS, cache_key
from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.store import cache_set
from opentrading_mcp.schemas import utc_now_iso

SYMBOLS_OHLC = ["VN30F1M"]
INDICES = ["VNINDEX", "VN30"]


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
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except TimeoutError:
                _log("dnse recv timeout, reconnecting")
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
        payload = {"index": index, "foreign": state["foreign"]}
        cache_set(f"mcp:market:dnse_ws_snapshot:{name}", payload, 30)
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
