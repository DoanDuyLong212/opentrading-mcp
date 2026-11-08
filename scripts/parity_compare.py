#!/usr/bin/env python3
"""Compare the vnstock v4 parity baseline with the gen-6 adapter by VALUE (#89).

Run with the project .venv:  .venv/bin/python scripts/parity_compare.py [--env FILE]
    [--out FILE] [--no-vietstock-login]

The baseline (tests/fixtures/parity_v4_*) was captured from vnstock 4.0.2 on
2026-11-08. Each probe calls the CURRENT route for the same data with the same
arguments as the baseline and compares numbers, not just shapes:

- candles: closes matched by date -> overlap count and worst relative gap;
- listing: symbol overlap and name agreement;
- ratios / fundamentals: P/E, P/B, ROE, EPS, BVPS on the shared periods;
- routes with no source since fhsc/fmp were dropped report ``not_configured``.

A probe runs when ANY source of its chain has its keys (the chains fall back),
and it is skipped up front only when none has. The markdown report goes to
stdout and to ``--out`` (default plans/vnstock-gen6-parity-report-<date>.md).
``--no-vietstock-login`` drops VIETSTOCK_EMAIL/PASSWORD so a run from a second
machine can only reuse the stored JWT and never opens a new Vietstock session.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

FIXTURE_DIRS = sorted((REPO / "tests" / "fixtures").glob("parity_v4_*"))
BASELINE = FIXTURE_DIRS[-1] if FIXTURE_DIRS else None
CANDLE_TOLERANCE = 0.005  # 0.5 %: adjusted-price drift between sources, not unit errors

Compare = Callable[[Any, Any], tuple[str, str]]


def _load_env(path: Path, *, no_vietstock_login: bool) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    if no_vietstock_login:
        os.environ.pop("VIETSTOCK_EMAIL", None)
        os.environ.pop("VIETSTOCK_PASSWORD", None)


def _ready(source: str) -> bool:
    if source == "ssi":
        need: tuple[str, ...] = ("SSI_API_KEY", "SSI_API_SECRET")
    elif source == "dnse":
        has_secret = os.environ.get("DNSE_API_SECRET") or os.environ.get("DNSE_SECRET")
        return bool(os.environ.get("DNSE_API_KEY", "").strip() and has_secret)
    elif source == "vietstock":
        need = ("VIETSTOCK_COOKIE_LOGIN",)
    else:
        return False
    return all(os.environ.get(var, "").strip() for var in need)


# --- value comparisons -----------------------------------------------------------


def _closes(rows: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        day = str(row.get("t") or row.get("time") or "")[:10]
        close = row.get("c", row.get("close"))
        if day and isinstance(close, (int, float)):
            out[day] = float(close)
    return out


def compare_candles(v4: Any, v6: Any) -> tuple[str, str]:
    old, new = _closes(v4), _closes(v6)
    shared = sorted(set(old) & set(new))
    if not shared:
        return "NO OVERLAP", f"v4 {len(old)} days, v6 {len(new)} days"
    gaps = {d: abs(new[d] - old[d]) / abs(old[d]) for d in shared if old[d]}
    worst = max(gaps, key=lambda d: gaps[d]) if gaps else shared[-1]
    detail = (
        f"{len(shared)} shared days; worst {worst}: v4 {old[worst]:g} vs v6 {new[worst]:g} "
        f"({gaps.get(worst, 0.0) * 100:.2f} %)"
    )
    return ("match" if gaps.get(worst, 0.0) <= CANDLE_TOLERANCE else "DIFF"), detail


def compare_listing(v4: Any, v6: Any) -> tuple[str, str]:
    old = {r["symbol"]: r.get("name", "") for r in v4 if isinstance(r, dict)}
    new = {r["symbol"]: r.get("name", "") for r in v6 if isinstance(r, dict)}
    shared = set(old) & set(new)
    same_name = sum(1 for s in shared if old[s].strip().lower() == new[s].strip().lower())
    status = "match" if old and len(shared) == len(old) else "DIFF"
    return status, (
        f"{len(shared)}/{len(old)} baseline symbols present; names equal for "
        f"{same_name}/{len(shared)}; v6 lists {len(new)} symbols in total"
    )


_RATIO_IDS = ("p_e", "p_b", "roe", "trailing_eps", "book_value_per_share_bvps")


def compare_ratios(v4: dict[str, Any], v6: dict[str, Any]) -> tuple[str, str]:
    def by_id(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {r["item_id"]: r.get("values") or {} for r in table.get("ratios") or []}

    old, new = by_id(v4), by_id(v6)
    v6_periods = set(v6.get("periods") or [])
    periods = [p for p in v4.get("periods") or [] if p in v6_periods]
    if not periods:
        return "NO OVERLAP", f"v4 periods {v4.get('periods')}, v6 {v6.get('periods')}"
    worst_gap, worst_text, compared = 0.0, "none", 0
    for item in _RATIO_IDS:
        for p in periods:
            a, b = old.get(item, {}).get(p), new.get(item, {}).get(p)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
                compared += 1
                gap = abs(b - a) / abs(a)
                if gap > worst_gap:
                    worst_gap, worst_text = gap, f"{item} {p}: v4 {a:g} vs v6 {b:g}"
    status = "match" if worst_gap <= 0.01 else "DIFF"
    detail = (
        f"{compared} values on {len(periods)} periods; worst {worst_text} "
        f"({worst_gap * 100:.2f} %)"
    )
    return status, detail


def compare_fundamentals(v4: dict[str, Any], v6: dict[str, Any]) -> tuple[str, str]:
    diffs = []
    for key in ("pe", "roe", "eps", "bvps", "period_label", "eps_basis"):
        a, b = v4.get(key), v6.get(key)
        if isinstance(a, float) and isinstance(b, float):
            if a and abs(b - a) / abs(a) > 0.01:
                diffs.append(f"{key} {a:g}->{b:g}")
        elif a != b:
            diffs.append(f"{key} {a!r}->{b!r}")
    return ("match" if not diffs else "DIFF"), "; ".join(diffs) or "pe/roe/eps/bvps/period agree"


def compare_fx_gold(v4: Any, v6: Any) -> tuple[str, str]:
    old = {r["symbol"]: (r.get("last") or {}).get("close") for r in v4}
    new = {r["symbol"]: (r.get("last") or {}).get("close") for r in v6}
    fx = f"USDVND v4 {old.get('USDVND')} vs v6 {new.get('USDVND')}"
    gold = f"gold: v4 MSN SPOT {old.get('XAUUSD')} vs v6 COMEX FUTURES {new.get('GC=F')}"
    return "expected DIFF (spot -> futures)", f"{fx}; {gold}"


def compare_none(v4: Any, v6: Any) -> tuple[str, str]:
    """Routes without a source: a value means something answered unexpectedly."""
    return "UNEXPECTED VALUE", f"route answered {type(v6).__name__}; update this probe"


# --- probes ----------------------------------------------------------------------


def _probes() -> list[tuple[str, tuple[str, ...], Callable[[], Any], Compare]]:
    from opentrading_mcp.providers import vnstock as vn
    from opentrading_mcp.providers import yfinance as yf

    try:  # #108: ratio tools on Vietstock financeinfo
        from opentrading_mcp.providers import vs_ratios
    except ImportError:  # before #108 is merged
        vs_ratios = None

    def missing() -> dict[str, str]:
        return {"_status": "skipped: providers/vs_ratios.py missing (#108)"}

    def ratios(symbol: str) -> Callable[[], Any]:
        if vs_ratios is None:
            return missing
        return lambda: vs_ratios.equity_ratios(symbol, "year")

    def fundamentals() -> Any:
        return missing() if vs_ratios is None else vs_ratios.equity_fundamentals("FPT", "year")

    candles: Compare = compare_candles
    chain = ("ssi", "dnse")
    return [
        ("quote_history_FPT", chain, lambda: vn.quote_history("FPT", days=60), candles),
        ("quote_history_VCB", chain, lambda: vn.quote_history("VCB", days=60), candles),
        ("quote_history_SSI", chain, lambda: vn.quote_history("SSI", days=60), candles),
        ("quote_history_VNINDEX", chain, lambda: vn.quote_history("VNINDEX", 60), candles),
        ("equity_ohlcv_FPT", chain, lambda: vn.equity_ohlcv("FPT", count=30), candles),
        ("index_ohlcv_VNINDEX", chain, lambda: vn.index_ohlcv("VNINDEX", count=30), candles),
        ("futures_ohlcv_VN30F1M", chain, lambda: vn.futures_ohlcv("VN30F1M", count=30), candles),
        ("crypto_ohlv_BTCUSDT", (), lambda: vn.crypto_ohlv("BTCUSDT", count=30), candles),
        ("forex_ohlcv_USDVND", (), lambda: yf.fx_history("USDVND", count=30), candles),
        ("global_index_USA30", (), lambda: yf.global_index("USA30", count=30), candles),
        ("listing_symbols", chain, lambda: vn.listing_symbols(), compare_listing),
        ("equity_ratios_FPT", ("vietstock",), ratios("FPT"), compare_ratios),
        ("equity_ratios_VCB", ("vietstock",), ratios("VCB"), compare_ratios),
        ("equity_ratios_SSI", ("vietstock",), ratios("SSI"), compare_ratios),
        ("equity_fundamentals_FPT", ("vietstock",), fundamentals, compare_fundamentals),
        ("msn_fx_gold", (), lambda: yf.fx_gold(days=35), compare_fx_gold),
        # No source since fhsc/fmp were dropped: report the explicit status.
        ("equity_quote_batch", (), lambda: vn.equity_quote_batch(["FPT", "VCB"]), compare_none),
        ("cashflow_FPT_quarter", (), lambda: vn.cashflow("FPT", period="quarter"), compare_none),
        ("company_info_FPT", (), lambda: vn.company_info("FPT"), compare_none),
        ("insider_trading_FPT", (), lambda: vn.insider_trading("FPT", limit=10), compare_none),
        ("corp_events_FPT", (), lambda: vn.corp_events("FPT", limit=10), compare_none),
    ]


def _baseline(name: str) -> Any:
    assert BASELINE is not None
    payload = json.loads((BASELINE / f"{name}.json").read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("ok") is False:
        return {"_baseline_error": payload.get("error", "")}
    if isinstance(payload, dict) and payload.get("data") is not None:
        return payload["data"]
    return payload.get("rows") if isinstance(payload, dict) else payload


def run() -> list[dict[str, str]]:
    from opentrading_mcp.providers.circuit import reset

    rows: list[dict[str, str]] = []
    for name, chain, call, compare in _probes():
        for breaker in ("vnstock", "yfinance", "vietstock"):
            reset(breaker)
        if chain and not any(_ready(s) for s in chain):
            rows.append({"probe": name, "status": "skipped",
                         "detail": f"no keys for any of {'/'.join(chain)}"})
            continue
        try:
            v6 = call()
        except Exception as exc:
            reason = getattr(exc, "reason", None)
            status = "not_configured" if reason == "not_configured" else "error"
            rows.append({"probe": name, "status": status,
                         "detail": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        if isinstance(v6, dict) and "_status" in v6:
            rows.append({"probe": name, "status": "skipped", "detail": v6["_status"]})
            continue
        v4 = _baseline(name)
        if isinstance(v4, dict) and "_baseline_error" in v4:
            rows.append({"probe": name, "status": "no baseline", "detail": v4["_baseline_error"]})
            continue
        if not v4:
            rows.append({"probe": name, "status": "v4 empty",
                         "detail": "the v4 baseline holds no rows; nothing to compare"})
            continue
        status, detail = compare(v4, v6)
        rows.append({"probe": name, "status": status, "detail": detail})
    return rows


def render(rows: list[dict[str, str]]) -> str:
    assert BASELINE is not None
    lines = [
        f"# Parity: vnstock v4 baseline ({BASELINE.name}) vs current adapter, {date.today()}",
        "",
        "Values compared, not shapes. Candles: closes matched by date, tolerance "
        f"{CANDLE_TOLERANCE * 100:.1f} %. Ratios: P/E, P/B, ROE, EPS, BVPS on shared periods, "
        "tolerance 1 %.",
        "",
        "| Probe | Status | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {r['probe']} | {r['status']} | {r['detail']} |" for r in rows]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines += ["", "Totals: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--env", type=Path, default=REPO / ".env")
    parser.add_argument(
        "--out", type=Path,
        default=REPO / "plans" / f"vnstock-gen6-parity-report-{date.today()}.md",
    )
    parser.add_argument("--no-vietstock-login", action="store_true")
    args = parser.parse_args(argv)
    if BASELINE is None:
        print("no parity_v4_* fixture directory found", file=sys.stderr)
        return 1
    socket.setdefaulttimeout(45)
    _load_env(args.env, no_vietstock_login=args.no_vietstock_login)
    report = render(run())
    print(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"report written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
