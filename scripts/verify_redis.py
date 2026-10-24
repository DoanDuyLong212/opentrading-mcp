"""Live Redis verification: each sampled tool stores under mcp:{tool}:* with the
expected TTL bucket. Run: .venv/bin/python scripts/verify_redis.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

CASES: list[tuple[str, dict, str, int | None]] = [
    # (tool, args, ttl-bucket, expected seconds; None = dynamic price_ttl)
    ("crypto_spot", {"symbols": ["BTCUSDT"]}, "market(fixed 60s)", 60),
    ("vs_market_price", {"symbols": ["VCB"]}, "price_ttl dynamic", None),
    ("world_fear_greed", {}, "world", 300),
    ("financial_ratios", {"symbol": "VCB"}, "overview", 900),
    ("news_market", {"limit": 5}, "mins10", 600),
    ("block_trades", {"symbol": "VCB"}, "hour", 3600),
    ("stock_forensic", {"symbol": "VCB"}, "financeinfo", 21600),
    ("economic_calendar", {}, "documents", 86400),
    ("vs_categories", {}, "categories", 604800),
    ("distribution_count", {"symbol": "VNINDEX"}, "financeinfo", 21600),
    ("symbol_lookup", {"query": "VCB"}, "categories", 604800),
    ("yf_global_indices", {}, "loop/custom(world)", 300),
]


async def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    from mcp.server.fastmcp.server import Context as _FastCtx

    async def _noop(self, *a: object, **k: object) -> None:
        return None

    _FastCtx.log = _noop  # type: ignore[method-assign]
    _FastCtx.report_progress = _noop  # type: ignore[method-assign]

    from opentrading_mcp.cache import TTL_SECONDS
    from opentrading_mcp.providers import store as store_p
    from opentrading_mcp.server import create_server, register_all
    from opentrading_mcp.tools.shared import in_vn_session

    server = create_server()
    register_all(server)
    cli = store_p._redis()
    print("redis backend:", "UPSTASH" if cli is not None else "MEMORY-ONLY")
    session_now = in_vn_session()
    print("VN session now:", session_now)
    failures = 0
    for tool, args, bucket, expected in CASES:
        prefix = f"mcp:{tool}:"
        for k in [k for k in store_p._memory if k.startswith(prefix)]:
            store_p._memory.pop(k, None)
        if cli is not None:
            try:
                keys = await asyncio.to_thread(cli.keys, prefix + "*")
                if keys:
                    await asyncio.to_thread(cli.delete, *keys)
            except Exception:
                pass
        try:
            res = await asyncio.wait_for(server.call_tool(tool, args), 60)
        except Exception as exc:
            print(f"FAIL {tool}: call raised {type(exc).__name__} {str(exc)[:80]}")
            failures += 1
            continue
        import json

        blocks = res[0] if isinstance(res, tuple) else (getattr(res, "content", []) or [])
        text = "".join(getattr(b, "text", "") for b in blocks)
        try:
            payload = json.loads(text) if text else {}
        except Exception:
            payload = {}
        if isinstance(payload, dict) and payload.get("availability") == "unavailable":
            w = payload.get("warnings") or ["?"]
            print(f"SKIP {tool}: upstream unavailable ({str(w[0])[:70]})")
            continue
        exp = expected
        if exp is None:  # price_ttl dynamic
            exp = TTL_SECONDS["market"] if session_now else TTL_SECONDS["market_offhours"]
        key = None
        ttl = None
        mem_keys = [k for k in store_p._memory if k.startswith(prefix)]
        if mem_keys:
            key = mem_keys[0]
            exp_at, _ = store_p._memory[key]
            ttl = round(exp_at - time.time())
        elif cli is not None:
            try:
                keys = await asyncio.to_thread(cli.keys, prefix + "*")
                if keys:
                    key = keys[0].decode() if isinstance(keys[0], bytes) else keys[0]
                    ttl = await asyncio.to_thread(cli.ttl, key)
            except Exception as exc:
                print(f"FAIL {tool}: redis read error {exc}")
                failures += 1
                continue
        if key is None:
            print(f"FAIL {tool}: no Redis/memory key after success")
            failures += 1
            continue
        ok = abs(ttl - exp) <= 120 if ttl and ttl > 0 else False
        mark = "OK " if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"{mark} {tool}: key={key} ttl={ttl}s expected~{exp}s [{bucket}]")
        await asyncio.sleep(0.5)
    print(f"\n{len(CASES) - failures}/{len(CASES)} verified")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
