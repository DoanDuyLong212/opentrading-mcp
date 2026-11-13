"""vnstock canary: is the installed release still allowed, and does one ssi candle come back?

6.0.0rc5 was switched off by the vendor on 11/11/2026 and prod served no prices for two
days before anyone noticed. This is the cheap, frequent check (1-2 requests): the
vendor's signed verdict from ``vnstock.status()`` and ``quote_history("VCB", 5)``.

Exit 1 (the workflow opens an issue) when the release is disabled, expired, within 30
days of its end, or a candle call is refused by the vendor. Any other candle failure
(network, a missing SSI key) is reported but exits 0: the weekly live-smoke covers the
sources; this job watches the vendor.

    uv run python scripts/vnstock_canary.py [--out canary.md]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from opentrading_mcp import vnstock_release

BAD_RELEASE = {"disabled", "expired", "expiring", "not_installed", "unknown_expiry"}


def run() -> tuple[int, list[str]]:
    from opentrading_mcp.failures import VENDOR_DISABLED
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    lines = [f"# vnstock canary {date.today().isoformat()}", ""]
    failed = False
    release = vnstock_release.release_report()
    until = ""
    if release.get("expires"):
        until = f", until {release['expires']}, {release.get('days_left')} days"
    lines.append(
        f"- release: vnstock {release.get('version')} **{release.get('status')}** "
        f"(source {release.get('source')}{until})"
    )
    if release.get("warning"):
        lines.append(f"- warning: {release['warning']}")
    if release.get("source") != "live":
        lines.append("- note: the vendor verdict could not be read; table fallback shown")
    if release.get("status") in BAD_RELEASE:
        failed = True
    if vn_p.ensure_api_key() != "keyed":
        lines.append("- candle VCB: skipped (no SSI/DNSE keys in this environment)")
    else:
        try:
            rows = vn_p.quote_history("VCB", 5)
            lines.append(f"- candle VCB: ok ({len(rows)} rows)")
        except ProviderUnavailable as exc:
            reason = getattr(exc, "reason", None)
            lines.append(f"- candle VCB: FAILED, reason {reason}: {str(exc)[:400]}")
            if reason == VENDOR_DISABLED:
                failed = True
        except Exception as exc:  # report, never crash the canary
            lines.append(f"- candle VCB: FAILED ({type(exc).__name__}): {str(exc)[:400]}")
    fix = "Fix: upgrade vnstock (see src/opentrading_mcp/vnstock_release.py)."
    lines += ["", fix if failed else "OK"]
    return (1 if failed else 0), lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="also write the report (markdown) to this file")
    args = parser.parse_args()
    code, lines = run()
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
