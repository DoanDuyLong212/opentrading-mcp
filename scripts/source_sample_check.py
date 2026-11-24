#!/usr/bin/env python3
"""Sample-check published values against primary sources (#141).

Usage: .venv/bin/python scripts/source_sample_check.py --env FILE [--out FILE]

Read-only: calls the MCP tools, prints the value each one publishes, and leaves
the `primary source` / `match` columns for a person to fill from HOSE/HNX, the
company's IR report, SBV or GSO. Without source credentials the tools answer
`unavailable`; those rows are reported with the reason, never filled with a
guess.

The env file only needs the provider keys (VIETSTOCK_*, DNSE_*, SSI_*).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
_PREFIXES = ("VIETSTOCK_", "DNSE_", "SSI_", "TRADING_AGENTS_DIR", "VNSTOCK_", "DATABASE_URL")


def _load_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.strip().partition("=")
        key = key.strip()
        if key.startswith(_PREFIXES):
            os.environ[key] = value.strip().strip('"')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample-check published values (#141)")
    parser.add_argument("--env", type=Path, help="env file with provider credentials")
    parser.add_argument("--out", type=Path, help="write markdown here (default: stdout)")
    parser.add_argument("--group", default="", help="statement|price|index|macro")
    parser.add_argument("--json", action="store_true", help="print the raw rows as JSON")
    args = parser.parse_args(argv)
    if args.env:
        _load_env(args.env)
    os.environ.setdefault("VNSTOCK_TELEMETRY", "0")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from opentrading_mcp.source_sample import SAMPLES, collect, render_markdown

    samples = SAMPLES
    if args.group:
        samples = tuple(s for s in samples if s.group == args.group.strip().lower())
        if not samples:
            print(f"no samples for group {args.group!r}", file=sys.stderr)
            return 2
    rows = asyncio.run(collect(samples))
    text = render_markdown(rows)
    if args.json:
        import json

        print(
            json.dumps(
                [
                    {
                        "id": row.sample.id,
                        "status": row.status,
                        "value": row.value,
                        "as_of": row.as_of,
                        "warnings": row.warnings,
                        "note": row.note,
                    }
                    for row in rows
                ],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    elif args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(rows)} rows)")
    else:
        print(text)
    collected = sum(1 for row in rows if row.status == "collected")
    print(f"collected {collected}/{len(rows)} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
