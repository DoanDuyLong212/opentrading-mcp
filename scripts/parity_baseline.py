#!/usr/bin/env python3
"""Capture a vnstock v4 parity baseline before the 2026-11-10 auth cutoff.

Run with the project .venv (vnstock 4.0.2):  .venv/bin/python scripts/parity_baseline.py
Writes JSON probes to tests/fixtures/parity_v4_<date>/ for the gen-6 migration
comparison (see plans/vnstock-gen6-migration-2026-11-08.md, Task 1/8).

Each probe is independent: a failure is recorded as {"error": ...} and the run
continues. Every probe retries once. Output is truncated where a probe returns
the whole market (listing) so fixtures stay reviewable.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from opentrading_mcp.providers import vnstock as vn  # noqa: E402

OUT_DIR = REPO / "tests" / "fixtures" / f"parity_v4_{date.today().isoformat()}"


def _load_env_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO, timeout=10
        ).stdout.strip()
    except Exception:
        return "unknown"


def _jsonable(obj: object) -> object:
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)[:2000]


def _probe(name: str, fn, *, truncate: int | None = None, attempts: int = 2):
    last_error = None
    for _attempt in range(attempts):
        started = time.monotonic()
        try:
            result = fn()
            rows = result
            payload: dict = {"ok": True, "elapsed_s": round(time.monotonic() - started, 2)}
            if isinstance(rows, list) and truncate is not None and len(rows) > truncate:
                payload["total_rows"] = len(rows)
                payload["rows"] = rows[:truncate]
            else:
                payload["rows"] = rows if isinstance(rows, list) else None
                if not isinstance(rows, list):
                    payload["data"] = _jsonable(rows)
            return payload
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
    return {"ok": False, "elapsed_s": round(time.monotonic() - started, 2), "error": last_error}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    socket.setdefaulttimeout(45)
    env = _load_env_dotenv(REPO / ".env")
    if env.get("VNSTOCK_API_KEY") and "VNSTOCK_API_KEY" not in os.environ:
        os.environ["VNSTOCK_API_KEY"] = env["VNSTOCK_API_KEY"]
    vn.ensure_api_key()

    probes: dict[str, dict] = {}

    for sym in ("FPT", "VCB", "SSI", "VNINDEX"):
        probes[f"quote_history_{sym}"] = _probe(
            sym, lambda s=sym: vn.quote_history(s, days=60, interval="1D")
        )
    probes["equity_quote_batch"] = _probe(
        "batch", lambda: vn.equity_quote_batch(["FPT", "VCB", "SSI", "HPG", "VNM"])
    )
    probes["equity_ohlcv_FPT"] = _probe("FPT", lambda: vn.equity_ohlcv("FPT", count=30))
    probes["index_ohlcv_VNINDEX"] = _probe("VNINDEX", lambda: vn.index_ohlcv("VNINDEX", count=30))
    probes["futures_ohlcv_VN30F1M"] = _probe(
        "VN30F1M", lambda: vn.futures_ohlcv("VN30F1M", count=30)
    )
    probes["forex_ohlcv_USDVND"] = _probe("USDVND", lambda: vn.forex_ohlcv("USDVND", count=30))
    probes["crypto_ohlv_BTCUSDT"] = _probe("BTCUSDT", lambda: vn.crypto_ohlv("BTCUSDT", count=30))
    probes["global_index_USA30"] = _probe("USA30", lambda: vn.global_index("USA30", count=30))
    probes["equity_trades_FPT"] = _probe("FPT", lambda: vn.equity_trades("FPT", limit=20))
    probes["listing_symbols"] = _probe("listing", vn.listing_symbols, truncate=50)
    for sym in ("FPT", "VCB", "SSI"):
        probes[f"equity_ratios_{sym}"] = _probe(
            sym, lambda s=sym: vn.equity_ratios(s, period="year")
        )
    probes["equity_fundamentals_FPT"] = _probe(
        "FPT", lambda: vn.equity_fundamentals("FPT", period="year")
    )
    probes["cashflow_FPT_quarter"] = _probe("FPT", lambda: vn.cashflow("FPT", period="quarter"))
    probes["reference_equity_HOSE"] = _probe("HOSE", vn.reference_equity, truncate=50)
    probes["company_info_FPT"] = _probe("FPT", lambda: vn.company_info("FPT", detail=True))
    probes["insider_trading_FPT"] = _probe("FPT", lambda: vn.insider_trading("FPT", limit=10))
    probes["corp_events_FPT"] = _probe("FPT", lambda: vn.corp_events("FPT", limit=10))
    probes["msn_fx_gold"] = _probe("msn", vn.msn_fx_gold)

    meta = {
        "captured_at": datetime.now(UTC).isoformat(),
        "vnstock_version": importlib.metadata.version("vnstock"),
        "python_version": sys.version.split()[0],
        "git_sha": _git_sha(),
        "api_key_state": "set" if env.get("VNSTOCK_API_KEY") else "missing",
        "probe_count": len(probes),
        "ok_count": sum(1 for p in probes.values() if p.get("ok")),
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    for name, payload in probes.items():
        (OUT_DIR / f"{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
        )
    print(json.dumps(meta, indent=2))
    failed = [n for n, p in probes.items() if not p.get("ok")]
    print("FAILED probes:", failed if failed else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
