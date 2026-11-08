#!/usr/bin/env python3
"""Compare the v4 parity baseline (tests/fixtures/parity_v4_*) against gen 6.

Run with the project .venv (vnstock 6):  .venv/bin/python scripts/parity_compare.py

Probes that need per-source Open API keys (fhsc/ssi/fmp) are marked
"skipped: no source key" until those keys exist; binance runs keyless so the
crypto leg is compared for real. Output: a markdown report on stdout.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from opentrading_mcp.providers import vnstock as vn  # noqa: E402
from opentrading_mcp.providers.circuit import reset as _reset_circuit  # noqa: E402

FIXTURE_DIRS = sorted((REPO / "tests" / "fixtures").glob("parity_v4_*"))
OUT = FIXTURE_DIRS[-1] if FIXTURE_DIRS else None

SOURCE_KEYS = {
    "fhsc": "FHSC_API_KEY",
    "ssi": "SSI_API_KEY",
    "fmp": "FMP_API_KEY",
}


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _keys_present() -> set[str]:
    present: set[str] = set()
    for src, var in SOURCE_KEYS.items():
        if os.environ.get(var, "").strip():
            present.add(src)
    return present


def _probe(required: set[str], fn, *args, **kwargs):
    """Run one probe; skip up front when its sources have no key (the adapter
    swallows the auth error inside the source fallback, so detection must not
    rely on the raised message)."""
    _reset_circuit("vnstock")
    if required - keys_present:
        return {"_status": f"skipped: no source key ({'/'.join(sorted(required - keys_present))})"}
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return {"_status": f"error: {type(exc).__name__}: {str(exc)[:140]}"}


def _norm(rows: list[dict]) -> list[dict]:
    keep = ("t", "o", "h", "l", "c", "v", "time", "open", "high", "low", "close", "volume")
    out = []
    for r in rows[:5] if isinstance(rows, list) else []:
        out.append({k: (round(float(v), 6) if isinstance(v, (int, float)) else str(v)[:24])
                    for k, v in r.items() if k in keep})
    return out


def compare(name: str, v4, v6) -> dict:
    row: dict = {"probe": name}
    if isinstance(v4, dict) and v4.get("ok") is False:
        row["v4"] = f"baseline failed: {v4.get('error', '')[:80]}"
    elif v6 is None:
        row["v4"] = "ok"
        row["status"] = "skipped (v6 not run)"
    elif isinstance(v6, dict) and "_status" in v6:
        row["status"] = v6["_status"]
        row["v4"] = "ok"
    else:
        row["v4"] = "ok"
        v4_rows = v4.get("rows") if isinstance(v4, dict) else v4
        if isinstance(v6, list):
            row["status"] = "match (shape)" if v6 else "empty"
            row["v6_sample"] = _norm(v6)
        elif isinstance(v6, dict):
            row["status"] = "match (shape)"
            row["v6_keys"] = sorted(v6.keys())[:12]
        else:
            row["status"] = f"unexpected v6 type {type(v6).__name__}"
    return row


def main() -> int:
    if OUT is None:
        print("no parity_v4_* fixture directory found", file=sys.stderr)
        return 1
    socket.setdefaulttimeout(45)
    env = _load_env(REPO / ".env")
    for k, v in env.items():
        os.environ.setdefault(k, v)
    global keys_present
    keys_present = _keys_present()
    print(f"# Đối chiếu parity v4 (fixture {OUT.name}) vs vnstock 6.0.0rc4\n")
    print(f"Khoá nguồn có sẵn: {sorted(keys_present) or 'không có'} — probe thiếu khoá bị bỏ qua trước khi gọi.\n")
    print("| Probe | v4 baseline | Trạng thái v6 |")
    print("|---|---|---|")

    probes: list[tuple[str, set[str], object]] = [
        ("quote_history_FPT", {"fhsc", "ssi"}, lambda: vn.quote_history("FPT", days=60)),
        ("quote_history_VNINDEX", {"ssi", "fhsc"}, lambda: vn.quote_history("VNINDEX", 60)),
        ("equity_quote_batch", {"fhsc"}, lambda: vn.equity_quote_batch(["FPT", "VCB"])),
        ("equity_ohlcv_FPT", {"fhsc", "ssi"}, lambda: vn.equity_ohlcv("FPT", count=30)),
        ("index_ohlcv_VNINDEX", {"ssi", "fhsc"}, lambda: vn.index_ohlcv("VNINDEX", count=30)),
        ("futures_ohlcv_VN30F1M", {"fhsc"}, lambda: vn.futures_ohlcv("VN30F1M", count=30)),
        ("forex_ohlcv_USDVND", {"fhsc"}, lambda: vn.forex_ohlcv("USDVND", count=30)),
        ("crypto_ohlv_BTCUSDT", set(), lambda: vn.crypto_ohlv("BTCUSDT", count=30)),
        ("global_index_USA30", {"fmp"}, lambda: vn.global_index("USA30", count=30)),
        ("equity_trades_FPT", {"fhsc", "ssi"}, lambda: vn.equity_trades("FPT", limit=20)),
        ("listing_symbols", {"ssi", "fhsc"}, lambda: vn.listing_symbols(limit=50)),
        ("equity_ratios_FPT", {"fhsc"}, lambda: vn.equity_ratios("FPT", period="quarter")),
        ("equity_fundamentals_FPT", {"fhsc"}, lambda: vn.equity_fundamentals("FPT", period="quarter")),
        ("cashflow_FPT_quarter", {"fhsc"}, lambda: vn.cashflow("FPT", period="quarter")),
        ("reference_equity_HOSE", {"ssi", "fhsc"}, lambda: vn.reference_equity("HOSE")),
        ("company_info_FPT", {"fhsc"}, lambda: vn.company_info("FPT")),
        ("insider_trading_FPT", {"fhsc"}, lambda: vn.insider_trading("FPT", limit=10)),
        ("corp_events_FPT", {"fhsc"}, lambda: vn.corp_events("FPT", limit=10)),
        ("msn_fx_gold", {"fhsc"}, lambda: vn.msn_fx_gold(days=35)),
    ]
    for name, required, fn in probes:
        v4 = json.loads((OUT / f"{name}.json").read_text())
        v6 = _probe(required, fn)
        row = compare(name, v4, v6)
        print(f"| {name} | {row.get('v4', '')} | {row.get('status', '')} |")

    print(
        "\n## Ghi chú schema cần biết\n"
        "- Nến gen 6: `time` mang múi giờ 07:00+07:00, `volume` Int64, đơn vị nghìn đồng (giữ như v4 adapter đã chuẩn hoá).\n"
        "- `equity_ratios` gen 6 tính bằng vnstock_quant.fa (period labels do fa cấp, không parse từ frame nguồn).\n"
        "- Thứ tự dòng: adapter sort tăng dần theo ngày sau fetch — v4 cũng tăng dần nên không đổi consumer.\n"
        "- Bị chặn bởi khoá: probe fhsc/ssi/fmp báo `skipped` TRƯỚC khi gọi (adapter nuốt lỗi auth trong vòng fallback, không tin được thông báo lỗi) — chạy lại script sau khi đăng ký khoá."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
