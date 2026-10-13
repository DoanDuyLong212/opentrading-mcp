"""Full tool matrix: sample args, timeouts and envelope contract checks.

Every tool gets exactly one representative call. Timeouts are per-tool
(tools/list 30s cold, market 15s, slow DNSE/quant 60-120s, local CRUD 20s).
Contract asserts the shared envelope; data availability is NOT asserted
(upstream may be legitimately empty/unavailable offline or off-hours).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from opentrading_mcp.verify import VerifyClient

ALLOWED_AVAILABILITY = {"available", "empty", "stale", "partial", "unavailable"}

# Tools that rewrite the shared cycle/asset tables (every user reads them). A verify run
# against a deployed server would refresh and re-finalize production data, so they are
# skipped unless OPENTRADING_VERIFY_WRITES=1 (use it only against a throwaway database).
SHARED_TABLE_WRITES = frozenset(
    {"cycle_stats_refresh", "cycle_stats_finalize", "vn_asset_refresh", "g_asset_refresh"}
)
VERIFY_WRITES_ENV = "OPENTRADING_VERIFY_WRITES"

# (tool, args, timeout_seconds) — single full surface, no presets
MATRIX: list[tuple[str, dict[str, Any], float]] = [
    ("market_snapshot", {}, 60.0),
    ("source_status", {}, 20.0),
    ("market_candles_batch", {"symbols": ["VCB", "HPG"], "days": 5}, 60.0),
    ("symbol_lookup", {"query": "Vietcombank"}, 30.0),
    ("market_movers", {"top_n": 5}, 30.0),
    ("breadth_scan", {}, 30.0),
    ("dnse_market_status", {}, 30.0),
    ("vn_quote_history", {"symbol": "VCB", "days": 5}, 60.0),
    ("vn_equity_quote_batch", {"symbols": ["VCB", "HPG"]}, 30.0),
    ("vn_listing", {}, 60.0),
    ("vn_fundamentals", {"symbol": "VCB"}, 60.0),
    ("vn_retail_gold", {}, 90.0),
    ("vn_retail_fx", {}, 30.0),
    ("vs_auth_status", {}, 20.0),
    ("vs_financeinfo", {"symbol": "VCB", "period": "quarter"}, 60.0),
    ("vs_market_price", {}, 30.0),
    ("vs_market_index", {}, 30.0),
    ("vs_nn_flow", {}, 30.0),
    ("vs_categories", {}, 30.0),
    ("vs_indicator_data", {"category_id": 1}, 30.0),
    ("vs_trading_info", {"symbol": "VCB"}, 30.0),
    ("yf_global_indices", {}, 60.0),
    ("yf_commodities", {}, 60.0),
    ("yf_yield_curve", {}, 60.0),
    ("dnse_ohlc_history", {"symbol": "VN30F1M", "resolution": 15}, 90.0),
    ("dnse_latest_trade", {"symbols": ["VN30F1M"]}, 30.0),
    ("dnse_foreign_flow", {}, 30.0),
    ("dnse_ws_snapshot", {}, 30.0),
    ("stock_screener", {"limit": 5}, 60.0),
    ("signals_screener_columns", {}, 30.0),
    ("signals_technical", {"symbol": "VCB"}, 60.0),
    ("sector_performance", {"level": 1}, 45.0),
    ("money_flow", {}, 60.0),
    ("alert_check", {"rules": [{"symbol": "VCB", "op": ">", "threshold": 10}]}, 60.0),
    ("quant_backtest", {"symbol": "VCB"}, 120.0),
    ("quant_risk", {"returns": [0.01, -0.02, 0.03]}, 20.0),
    ("quant_factors", {"symbol": "VCB"}, 60.0),
    ("scenario_simulate", {"scenario": "VNINDEX -5% week", "shock_pct": -5.0}, 60.0),
    ("brief_build", {"scope": "vn"}, 90.0),
    ("news_market", {"limit": 5}, 60.0),
    ("news_symbol", {"symbol": "VCB", "limit": 5}, 60.0),
    ("economic_calendar", {"scope": "vn"}, 45.0),
    ("corporate_calendar", {}, 45.0),
    ("world_prediction_odds", {"query": "Fed"}, 90.0),
    ("geo_intel", {}, 90.0),
    ("assets_rotation", {}, 150.0),
    ("compare_equities", {"symbols": ["VCB", "HPG"]}, 120.0),
    ("evidence_bundle", {"claim_ids": ["c1"]}, 20.0),
    ("oracle_meta", {}, 90.0),
    # cycle/asset knowledge tables (PG-backed; unavailable offline is fine)
    ("cycle_stats_check", {}, 30.0),
    ("cycle_seasonality", {"basket": "bank"}, 30.0),
    ("cycle_chains", {"pair": "bankRS3m->securities"}, 30.0),
    ("cycle_turning", {"year": 2025}, 30.0),
    ("cycle_tet", {"basket": "bank"}, 30.0),
    ("cycle_yearly", {"basket": "bank"}, 30.0),
    ("cycle_trough_events", {"trough": "2022-11-15"}, 30.0),
    ("vn_asset_check", {}, 30.0),
    ("vn_asset_seasonality", {"asset": "VNINDEX"}, 30.0),
    ("vn_asset_anchors", {}, 30.0),
    ("vn_asset_chains", {}, 30.0),
    ("g_asset_check", {}, 30.0),
    ("g_asset_seasonality", {"asset": "SPY"}, 30.0),
    ("g_asset_phase", {}, 30.0),
    ("g_asset_corr", {"regime": "post22"}, 30.0),
    ("g_asset_outlook", {}, 30.0),
    ("cycle_stats_refresh", {"symbols": ["VCB"]}, 120.0),
    ("vn_asset_refresh", {}, 120.0),
    ("g_asset_refresh", {}, 120.0),
    ("cycle_stats_finalize", {}, 60.0),
    ("web_fetch", {"url": "https://example.com", "format": "text"}, 60.0),
    ("vs_financial_terms", {}, 30.0),
    ("vs_financial_norms", {"btype": 1}, 30.0),
    ("vs_company_info", {"symbol": "VCB"}, 30.0),
    ("vs_overview_trading", {"symbol": "VCB"}, 30.0),
    ("vs_documents", {"symbol": "VCB"}, 30.0),
    ("vs_industry_tree", {}, 30.0),
    ("vs_industry_heatmap", {}, 30.0),
    ("vs_selftrading", {}, 30.0),
    ("vs_gics_index", {}, 30.0),
    ("vs_currency", {}, 30.0),
    ("vs_market_info", {}, 30.0),
    ("vs_xnk_detail", {"direction": "xk"}, 60.0),
    ("vn_index_ohlcv", {"symbol": "VNINDEX", "count": 5}, 60.0),
    ("vn_equity_ohlcv", {"symbol": "VCB", "count": 5}, 60.0),
    ("vn_futures_ohlcv", {"symbol": "VN30F1M", "count": 5}, 60.0),
    ("vn_forex_ohlcv", {"pair": "USDVND", "count": 5}, 60.0),
    ("vn_crypto_ohlcv", {"symbol": "BTCUSDT", "count": 5}, 60.0),
    ("vn_global_index", {"symbol": "USA30", "count": 5}, 60.0),
    ("vn_reference", {"exchange": "HOSE"}, 60.0),
    ("vn_company", {"symbol": "VCB"}, 60.0),
    ("vn_msn_fx_gold", {}, 60.0),
    ("vn_trades", {"symbol": "VCB", "limit": 5}, 60.0),
    ("yf_world_indices", {}, 120.0),
    ("yf_oracle_markets", {}, 150.0),
    ("yf_regime_assets", {}, 150.0),
    ("yf_mega_flows", {}, 120.0),
    ("yf_alloc_history", {"asset": "GC"}, 120.0),
    ("yf_market_pins", {}, 90.0),
    ("dnse_orderbook", {"symbol": "VN30F1M"}, 30.0),
    ("dnse_indices", {}, 30.0),
    ("dnse_vn30f1m_live", {}, 120.0),
    ("dnse_working_dates", {}, 30.0),
    ("exchange_calendar", {}, 20.0),
    ("stock_forensic", {"symbol": "VCB"}, 90.0),
    ("valuation_run", {"symbol": "VCB"}, 60.0),
    ("fred_series", {"series_id": "DGS10"}, 30.0),
    ("world_macro_country", {"iso3": "VNM", "indicator": "NY.GDP.MKTP.KD.ZG"}, 30.0),
    ("world_fear_greed", {}, 30.0),
    ("sentiment_score", {"symbol": "VCB"}, 60.0),
    ("insider_trading", {"symbol": "VCB"}, 60.0),
    ("stock_overview", {"symbol": "VCB"}, 60.0),
    ("company_events", {"symbol": "VCB"}, 30.0),
    ("financial_statements", {"symbol": "VCB"}, 60.0),
    ("financial_ratios", {"symbol": "VCB"}, 30.0),
    ("peer_compare", {"symbol": "VCB", "peers": ["HPG"]}, 60.0),
    ("signals_scan", {"max_symbols": 3}, 120.0),
    ("pattern_match", {"symbol": "VCB"}, 60.0),
    ("event_stats", {"query": "stock market"}, 90.0),
    ("compare_assets", {"assets": ["GC=F", "BTC-USD"]}, 60.0),
    ("runs_list", {}, 20.0),
    ("run_get", {"run_id": "none"}, 20.0),
    ("doctor", {}, 20.0),
    ("market_overview", {"top_n": 3}, 60.0),
    ("symbol_resolve", {"query": "Vang"}, 30.0),
    ("vn_crypto_ohlv", {"symbol": "BTCUSDT", "count": 5}, 60.0),
    ("crypto_spot", {"symbols": ["BTCUSDT"]}, 30.0),
    ("crypto_derivs", {"symbols": ["BTCUSDT"]}, 60.0),
    ("snapshot_history", {"kind": "macro_curated"}, 30.0),
    ("holders", {"symbol": "VCB"}, 60.0),
    ("dividends_splits", {"symbol": "VCB"}, 60.0),
    ("block_trades", {"symbol": "VCB"}, 60.0),
    ("event_calendar_vn", {"event": "dividends", "symbol": "VCB"}, 45.0),
    ("analyst_consensus", {"limit": 5}, 60.0),
    ("financial_detail", {"symbol": "VCB"}, 60.0),
    ("fireant_thread", {"post_id": 1}, 60.0),
    ("futures_basis", {}, 45.0),
    ("ipo_calendar_vn", {}, 45.0),
    ("macro_events_vn", {}, 45.0),
    ("sbv_rates", {}, 45.0),
    ("planned_targets", {"symbol": "VCB"}, 60.0),
    ("polymarket_event", {"slug": "none"}, 60.0),
    ("event_study", {"symbol": "VCB", "dates": ["2026-09-21"]}, 90.0),
    ("correlation_matrix", {"symbols": ["VCB", "HPG"]}, 90.0),
    ("seasonality", {"symbol": "VCB"}, 90.0),
    ("backtest_strategies", {"symbol": "VCB"}, 120.0),
    ("portfolio_optimize", {"symbols": ["VCB", "HPG"]}, 120.0),
    ("param_sweep", {"symbol": "VCB"}, 120.0),
    ("watchlist_create", {"name": "verify-matrix"}, 20.0),
    ("watchlist_list", {}, 20.0),
    ("watchlist_add", {"list_id": 1, "symbols": ["VCB"]}, 20.0),
    ("watchlist_get", {"list_id": 1}, 20.0),
    ("watchlist_update", {"list_id": 1, "name": "verify-matrix-2"}, 20.0),
    ("alert_create", {"symbol": "VCB", "op": ">", "threshold": 999999.0}, 20.0),
    ("alert_list", {}, 20.0),
    ("alert_pause", {"rule_id": 1}, 20.0),
    ("alert_resume", {"rule_id": 1}, 20.0),
    ("alert_delete", {"rule_id": 1}, 20.0),
    ("watchlist_remove", {"list_id": 1, "symbols": ["VCB"]}, 20.0),
    ("watchlist_delete", {"list_id": 1}, 20.0),
]


def extract_text(payload: Any) -> str | None:
    content = getattr(payload, "content", None)
    if not content:
        return None
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts) if parts else None


def check_envelope(tool: str, payload: Any) -> list[str]:
    """Return a list of contract violations (empty = pass)."""
    text = extract_text(payload)
    if text is None:
        return [f"{tool}: no text content in result"]
    try:
        body = json.loads(text)
    except ValueError:
        return [f"{tool}: result text is not JSON"]
    if not isinstance(body, dict):
        return [f"{tool}: envelope is not an object"]
    errors: list[str] = []
    for key in ("data", "provenance", "warnings", "availability"):
        if key not in body:
            errors.append(f"{tool}: envelope missing {key!r}")
    availability = body.get("availability")
    if availability not in ALLOWED_AVAILABILITY:
        errors.append(f"{tool}: bad availability {availability!r}")
    provenance = body.get("provenance")
    if not isinstance(provenance, dict):
        errors.append(f"{tool}: provenance is not an object")
    else:
        if provenance.get("timezone") != "Asia/Ho_Chi_Minh":
            errors.append(f"{tool}: wrong timezone {provenance.get('timezone')!r}")
        if not provenance.get("as_of"):
            errors.append(f"{tool}: provenance missing as_of")
        if not provenance.get("source"):
            errors.append(f"{tool}: provenance missing source")
    warnings = body.get("warnings")
    if not isinstance(warnings, list):
        errors.append(f"{tool}: warnings is not a list")
    return errors


def all_calls() -> list[tuple[str, dict[str, Any], float]]:
    return list(MATRIX)


def writes_allowed() -> bool:
    return os.environ.get(VERIFY_WRITES_ENV, "").strip() == "1"


def runnable_calls(
    calls: list[tuple[str, dict[str, Any], float]],
) -> tuple[list[tuple[str, dict[str, Any], float]], list[str]]:
    """Split calls into those to run and the shared-table writers skipped by default."""
    if writes_allowed():
        return calls, []
    run = [c for c in calls if c[0] not in SHARED_TABLE_WRITES]
    skipped = [c[0] for c in calls if c[0] in SHARED_TABLE_WRITES]
    return run, skipped


def _skipped_rows(tools: list[str], transport: str) -> list[dict[str, Any]]:
    return [
        {
            "tool": tool,
            "transport": transport,
            "ok": True,
            "seconds": 0.0,
            "availability": "skipped",
            "detail": f"skipped: rewrites shared tables (set {VERIFY_WRITES_ENV}=1 to run)",
        }
        for tool in tools
    ]


def calls_for_preset(preset: str = "all") -> list[tuple[str, dict[str, Any], float]]:
    """Deprecated alias giu tuong thich."""
    return all_calls()


async def run_stdio_all() -> list[dict[str, Any]]:
    """Spawn a local server exactly like an opencode local entry and check it."""
    client = VerifyClient(server_label="opentrading")
    command = [sys.executable, "-m", "opentrading_mcp", "serve"]
    calls, skipped = runnable_calls(all_calls())
    results = await client.run(calls, "stdio", command)
    rows: list[dict[str, Any]] = []
    for (tool, _, _), res in zip(calls, results, strict=True):
        violations = check_envelope(tool, res.payload) if res.ok else [res.detail]
        rows.append(
            {
                "tool": tool,
                "transport": "stdio",
                "ok": res.ok and not violations,
                "seconds": round(res.seconds, 2),
                "availability": _availability(res.payload) if res.ok else "-",
                "detail": "; ".join(violations),
            }
        )
    return rows + _skipped_rows(skipped, "stdio")


async def run_preset_stdio(preset: str = "all") -> list[dict[str, Any]]:
    return await run_stdio_all()


async def run_remote_all(url: str) -> list[dict[str, Any]]:
    """Check the deployed server over StreamableHTTP (SSE fallback inside)."""
    client = VerifyClient(server_label="opentrading", timeout=120.0)
    runnable, skipped = runnable_calls(all_calls())
    calls = [(tool, args, max(timeout * 3, 90.0)) for tool, args, timeout in runnable]
    results = await client.run(calls, "remote", url)
    rows: list[dict[str, Any]] = []
    for (tool, _, _), res in zip(calls, results, strict=True):
        violations = check_envelope(tool, res.payload) if res.ok else [res.detail]
        rows.append(
            {
                "tool": tool,
                "transport": "remote",
                "ok": res.ok and not violations,
                "seconds": round(res.seconds, 2),
                "availability": _availability(res.payload) if res.ok else "-",
                "detail": "; ".join(violations),
            }
        )
    return rows + _skipped_rows(skipped, "remote")


async def run_preset_remote(url: str, preset: str = "all") -> list[dict[str, Any]]:
    return await run_remote_all(url)


def _availability(payload: Any) -> str:
    text = extract_text(payload)
    if text is None:
        return "?"
    try:
        return str(json.loads(text).get("availability", "?"))
    except ValueError:
        return "?"
