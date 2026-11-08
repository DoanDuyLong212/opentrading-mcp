#!/usr/bin/env python3
"""Read-only check of the DNSE board rows (#84), meant for TRADING HOURS.

Usage: .venv/bin/python scripts/board_check.py --env FILE [--symbols FPT,VCB]

Prints each row the batch quote builds and says whether DNSE's secdef and last
trade refer to the same session. During the session (09:00-15:00 Asia/Ho_Chi_Minh)
expect no ``quote_note`` and non-None ceiling/floor; outside it expect
``quote_note`` and ``next_session``. Only DNSE/ssi variables are read from the
env file; nothing is written and no other service is called.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
_KEYS = {"DNSE_API_KEY", "DNSE_SECRET", "DNSE_API_SECRET", "SSI_API_KEY", "SSI_API_SECRET"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DNSE board rows, read-only")
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--symbols", default="FPT,VCB,HPG")
    args = parser.parse_args(argv)
    for line in args.env.read_text(encoding="utf-8").splitlines():
        key, _, value = line.strip().partition("=")
        if key.strip() in _KEYS:
            os.environ[key.strip()] = value.strip().strip('"')
    os.environ.setdefault("VNSTOCK_TELEMETRY", "0")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from opentrading_mcp.providers import vnstock as vn_p

    rows = vn_p.equity_quote_batch([s.strip() for s in args.symbols.split(",") if s.strip()])
    for row in rows:
        if "_missing" in row:
            print("MISSING", json.dumps(row, ensure_ascii=False))
            continue
        session = "CLOSED (next-session secdef)" if row.get("quote_note") else "IN SESSION"
        print(f"{row['symbol']}: {session}  time={row.get('time')}  close={row.get('close_price')} "
              f"ref={row.get('reference_price')} ceil={row.get('ceiling_price')} "
              f"floor={row.get('floor_price')} chg%={row.get('percent_change')} "
              f"bid1={row.get('bid_price_1')}x{row.get('bid_vol_1')} "
              f"ask1={row.get('ask_price_1')}x{row.get('ask_vol_1')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
