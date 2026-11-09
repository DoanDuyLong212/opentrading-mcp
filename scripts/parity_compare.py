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


def compare_crypto(v4: Any, v6: Any) -> tuple[str, str]:
    """v4 priced BTCUSDT in VND (close 1.94e9 on 2026-11-07); gen 6 (binance) in
    USDT (~75,800). A v4/v6 ratio equal to USD/VND is that unit change, not noise."""
    old, new = _closes(v4), _closes(v6)
    shared = sorted(set(old) & set(new))
    ratios = sorted(old[d] / new[d] for d in shared if new[d])
    if ratios and 20_000 <= ratios[len(ratios) // 2] <= 30_000:
        mid = ratios[len(ratios) // 2]
        return "expected DIFF (unit VND -> USDT)", (
            f"{len(shared)} shared days; v4/v6 median ratio {mid:,.0f} = USD/VND, so v4 was "
            "VND-denominated and gen 6 is USDT"
        )
    return compare_candles(v4, v6)


def compare_listing(v4: Any, v6: Any) -> tuple[str, str]:
    old = {r["symbol"]: r.get("name", "") for r in v4 if isinstance(r, dict)}
    new = {r["symbol"]: r.get("name", "") for r in v6 if isinstance(r, dict)}
    shared = set(old) & set(new)
    same_name = sum(1 for s in shared if old[s].strip().lower() == new[s].strip().lower())
    status = "match" if old and len(shared) == len(old) else "DIFF"
    example = next((s for s in sorted(shared) if old[s] != new[s]), None)
    sample = f"; e.g. {example}: v4 {old[example]!r} vs v6 {new[example]!r}" if example else ""
    return status, (
        f"{len(shared)}/{len(old)} baseline symbols present; names equal for "
        f"{same_name}/{len(shared)}{sample}; v6 lists {len(new)} symbols in total"
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


def _second(row: dict[str, Any]) -> str:
    return str(row.get("time", "")).replace("T", " ")[:19]


def compare_trades(v4: Any, v6: Any) -> tuple[str, str]:
    """Volume traded per price inside the baseline's time window.

    v4 (KBS) aggregated fills per second and its clock ran about a second early;
    dnse lists every fill to the millisecond (v4 "14:27:52 50.9 x 6200" =
    dnse 14:27:53.488 x 700 + 14:27:53.489 x 5500). So prints cannot be matched
    one by one, but the volume at each price over the window must agree; a volume
    unit change (dnse lots of 10) is off by 10x and fails.
    """
    from datetime import datetime, timedelta

    old = [r for r in v4 if isinstance(r, dict)]
    if not old:
        return "NO OVERLAP", "empty baseline"
    first, last = min(_second(r) for r in old), max(_second(r) for r in old)
    end = (datetime.fromisoformat(last) + timedelta(seconds=2)).isoformat(sep=" ")

    def by_price(rows: list[dict[str, Any]], lo: str, hi: str) -> dict[float, float]:
        out: dict[float, float] = {}
        for r in rows:
            if lo <= _second(r) <= hi:
                price = float(r.get("price") or 0)
                out[price] = out.get(price, 0.0) + float(r.get("volume") or 0)
        return out

    a = by_price(old, first, last)
    b = by_price([r for r in v6 if isinstance(r, dict)], first, end)
    total_a, total_b = sum(a.values()), sum(b.values())
    gap = abs(total_b - total_a) / total_a if total_a else 1.0
    levels = ", ".join(f"{p:g}: v4 {a.get(p, 0):,.0f} vs v6 {b.get(p, 0):,.0f}"
                       for p in sorted(set(a) | set(b)))
    detail = (f"window {first[11:]}-{last[11:]} (+1 s clock skew): v4 {total_a:,.0f} vs "
              f"v6 {total_b:,.0f} shares ({gap * 100:.1f} %); by price {levels}")
    return ("match" if gap <= 0.05 else "DIFF"), detail


def compare_board(v4: Any, v6: Any) -> tuple[str, str]:
    """Batch quote rows against the v4 board, only when both are the same session."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")

    def day(row: dict[str, Any]) -> str:
        stamp = row.get("time")
        if isinstance(stamp, (int, float)):  # v4: epoch milliseconds
            return datetime.fromtimestamp(stamp / 1000, vn_tz).date().isoformat()
        return str(stamp or "")[:10]

    old = {r["symbol"]: r for r in v4 if isinstance(r, dict) and "symbol" in r}
    new = {r["symbol"]: r for r in v6 if isinstance(r, dict) and "symbol" in r}
    shared = sorted(set(old) & set(new))
    if not shared:
        return "NO OVERLAP", "no common symbol"
    if any(day(old[s]) != day(new[s]) for s in shared):
        return "expected DIFF (different session)", (
            f"board is for {day(new[shared[0]])}, baseline for {day(old[shared[0]])}"
        )
    fields = ("close_price", "reference_price", "volume_accumulated", "total_value",
              "bid_price_1", "bid_vol_1", "ask_price_1", "ask_vol_1")
    diffs = [f"{s}.{f} v4 {old[s].get(f)} vs v6 {new[s].get(f)}" for s in shared for f in fields
             if old[s].get(f) is not None and new[s].get(f) is not None
             and float(old[s][f]) != float(new[s][f])]
    return ("match" if not diffs else "DIFF"), (
        f"{len(shared)} symbols x {len(fields)} fields; " + ("; ".join(diffs[:3]) or "all equal")
    )


def compare_reference(v4: Any, v6: Any) -> tuple[str, str]:
    old = {r["symbol"]: r for r in v4 if isinstance(r, dict)}
    new = {r["symbol"]: r for r in v6 if isinstance(r, dict)}
    shared = set(old) & set(new)
    same_exchange = sum(1 for s in shared if old[s].get("exchange") == new[s].get("exchange"))
    status = "match" if old and len(shared) == len(old) and same_exchange == len(shared) else "DIFF"
    return status, (
        f"{len(shared)}/{len(old)} baseline symbols present; exchange equal for "
        f"{same_exchange}/{len(shared)}; v6 lists {len(new)} rows for the exchange"
    )


def compare_corp_events(v4: Any, v6: Any) -> tuple[str, str]:
    """Q1: v4's dividend/share-issue rows (DIV/ISS with an ex-right date) must be in
    the ssi calendar answer on the same ex-right date with the same amount/ratio.
    v4 (fhsc) also listed insider registrations and listings, which ssi does not."""
    def key(row: dict[str, Any]) -> tuple[str, str]:
        return str(row.get("event_code")), str(row.get("exright_date") or "")[:10]

    wanted = [r for r in v4 if r.get("event_code") in ("DIV", "ISS") and r.get("exright_date")]
    got = {key(r): r for r in v6}
    if not wanted:
        return "match", "no dividend/issue rows in the baseline window"
    missing, diffs = [], []
    for row in wanted:
        hit = got.get(key(row))
        if hit is None:
            missing.append(key(row))
            continue
        for field in ("value_per_share", "exercise_ratio"):
            a, b = row.get(field), hit.get(field)
            if a is not None and (b is None or abs(float(a) - float(b)) > 1e-9):
                diffs.append(f"{key(row)} {field}: v4 {a} vs v6 {b}")
    if missing or diffs:
        return "UNEXPECTED VALUE", f"missing {missing}; {diffs}"
    return "match", (f"{len(wanted)}/{len(wanted)} dividend/issue events equal "
                     f"(e.g. {key(wanted[0])}); v4-only insider/listing rows not compared")


def compare_none(v4: Any, v6: Any) -> tuple[str, str]:
    """Routes without a source: a value means something answered unexpectedly."""
    return "UNEXPECTED VALUE", f"route answered {type(v6).__name__}; update this probe"


# --- probes ----------------------------------------------------------------------


def _count_since(name: str, minimum: int) -> int:
    """Bars to request so the window still reaches back to the baseline's first
    day. The baseline is fixed (2026-08 to 2026-11); "the last N bars" would stop
    overlapping it within weeks and the weekly smoke would fail for no reason."""
    closes = _closes(_baseline(name))
    if not closes:
        return minimum
    first = date.fromisoformat(min(closes))
    return max(minimum, (date.today() - first).days + 10)  # calendar days ≥ sessions


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

    def n(name: str, minimum: int) -> int:
        return _count_since(name, minimum)

    return [
        ("quote_history_FPT", chain,
         lambda: vn.quote_history("FPT", days=n("quote_history_FPT", 60)), candles),
        ("quote_history_VCB", chain,
         lambda: vn.quote_history("VCB", days=n("quote_history_VCB", 60)), candles),
        ("quote_history_SSI", chain,
         lambda: vn.quote_history("SSI", days=n("quote_history_SSI", 60)), candles),
        ("quote_history_VNINDEX", chain,
         lambda: vn.quote_history("VNINDEX", n("quote_history_VNINDEX", 60)), candles),
        ("equity_ohlcv_FPT", chain,
         lambda: vn.equity_ohlcv("FPT", count=n("equity_ohlcv_FPT", 30)), candles),
        ("index_ohlcv_VNINDEX", chain,
         lambda: vn.index_ohlcv("VNINDEX", count=n("index_ohlcv_VNINDEX", 30)), candles),
        ("futures_ohlcv_VN30F1M", chain,
         lambda: vn.futures_ohlcv("VN30F1M", count=n("futures_ohlcv_VN30F1M", 30)), candles),
        ("crypto_ohlv_BTCUSDT", (),
         lambda: vn.crypto_ohlv("BTCUSDT", count=n("crypto_ohlv_BTCUSDT", 30)), compare_crypto),
        ("forex_ohlcv_USDVND", (),
         lambda: yf.fx_history("USDVND", count=n("forex_ohlcv_USDVND", 30)), candles),
        ("global_index_USA30", (),
         lambda: yf.global_index("USA30", count=n("global_index_USA30", 30)), candles),
        ("listing_symbols", chain, lambda: vn.listing_symbols(), compare_listing),
        ("reference_equity_HOSE", chain, lambda: vn.reference_equity("HOSE"), compare_reference),
        # The baseline holds 20 prints of 2026-11-06; fetch that whole session.
        ("equity_trades_FPT", ("dnse",),
         lambda: vn.equity_trades("FPT", limit=50_000, from_date="2026-11-06",
                                  to_date="2026-11-06"),
         compare_trades),
        ("equity_ratios_FPT", ("vietstock",), ratios("FPT"), compare_ratios),
        ("equity_ratios_VCB", ("vietstock",), ratios("VCB"), compare_ratios),
        ("equity_ratios_SSI", ("vietstock",), ratios("SSI"), compare_ratios),
        ("equity_fundamentals_FPT", ("vietstock",), fundamentals, compare_fundamentals),
        ("msn_fx_gold", (), lambda: yf.fx_gold(days=35), compare_fx_gold),
        # No source since fhsc/fmp were dropped: report the explicit status.
        # #111: the board comes from the project DNSE client (v4 KBS shape).
        ("equity_quote_batch", ("dnse",),
         lambda: vn.equity_quote_batch(["FPT", "VCB", "HPG", "VNM", "MWG"]), compare_board),
        ("cashflow_FPT_quarter", (), lambda: vn.cashflow("FPT", period="quarter"), compare_none),
        ("company_info_FPT", (), lambda: vn.company_info("FPT"), compare_none),
        ("insider_trading_FPT", (), lambda: vn.insider_trading("FPT", limit=10), compare_none),
        # Q1: the ssi calendar (whole market, ~4 min per year) is loaded first.
        ("corp_events_FPT", ("ssi",), corp_events, compare_corp_events),
    ]


def corp_events() -> Any:
    from datetime import date

    from opentrading_mcp.providers import events_calendar
    from opentrading_mcp.providers import vnstock as vn

    events_calendar.warm([date.today().year])
    return vn.corp_events("FPT", limit=50)


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
    parser.add_argument(
        "--fail-on-diff", action="store_true",
        help="exit 1 when any probe is DIFF / NO OVERLAP / error / UNEXPECTED VALUE",
    )
    args = parser.parse_args(argv)
    if BASELINE is None:
        print("no parity_v4_* fixture directory found", file=sys.stderr)
        return 1
    socket.setdefaulttimeout(45)
    _load_env(args.env, no_vietstock_login=args.no_vietstock_login)
    rows = run()
    report = render(rows)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    print(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"report written to {args.out}", file=sys.stderr)
    bad = failing(rows)
    if args.fail_on_diff and bad:
        print(f"unexpected parity results: {', '.join(bad)}", file=sys.stderr)
        return 1
    return 0


def failing(rows: list[dict[str, str]]) -> list[str]:
    """Probes whose status is not a match, an explained difference or a known gap."""
    ok = {"match", "not_configured", "skipped", "v4 empty", "no baseline"}
    return [
        r["probe"] for r in rows
        if r["status"] not in ok and not r["status"].startswith("expected")
    ]


if __name__ == "__main__":
    raise SystemExit(main())
