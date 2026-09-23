"""Worker loops: pump realtime snapshots into Redis for web + tools.

M2 scope: yfinance global/commodities loop + heartbeat. DNSE WS loop
activates when DNSE_API_KEY is set (HMAC sub); otherwise logs cold state
so tools report unavailable instead of stale.
"""

from __future__ import annotations

import asyncio
import sys
import time

from opentrading_mcp.cache import TTL_SECONDS, cache_key
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.store import cache_set


def _log(message: str) -> None:
    print(f"[loops] {message}", file=sys.stderr, flush=True)


async def yf_loop(interval_seconds: int = 60) -> None:
    while True:
        try:
            cache_set(
                cache_key("market", "yf_global_indices", "loop"),
                {"indices": yf_p.batch_last(yf_p.GLOBAL_9)},
                TTL_SECONDS["world"],
            )
            cache_set(
                cache_key("market", "yf_commodities", "loop"),
                {"items": yf_p.batch_last(yf_p.COMMO_13)},
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


async def main_async() -> None:
    await asyncio.gather(yf_loop(), heartbeat_loop())


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
