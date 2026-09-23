"""Full tool matrix: sample args, timeouts and envelope contract checks.

Every tool gets exactly one representative call. Timeouts mirror
TIMEOUT_MATRIX (tools/list 30s cold, market 15s, slow DNSE/quant 60-120s).
Contract asserts the shared envelope; data availability is NOT asserted
(upstream may be legitimately empty/unavailable offline or off-hours).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opentrading_mcp.verify import VerifyClient

ALLOWED_AVAILABILITY = {"available", "empty", "stale", "partial", "unavailable"}

# (preset, tool, args, timeout_seconds)
MATRIX: list[tuple[str, str, dict[str, Any], float]] = [
    ("market", "market_snapshot", {}, 60.0),
    ("market", "source_status", {}, 20.0),
    ("market", "market_candles_batch", {"symbols": ["VCB", "HPG"], "days": 5}, 60.0),
    ("market", "symbol_lookup", {"query": "Vietcombank"}, 30.0),
    ("market", "market_movers", {"top_n": 5}, 30.0),
    ("market", "breadth_scan", {}, 30.0),
    ("market", "dnse_market_status", {}, 30.0),
    ("market", "vn_quote_history", {"symbol": "VCB", "days": 5}, 60.0),
    ("market", "vn_equity_quote_batch", {"symbols": ["VCB", "HPG"]}, 30.0),
    ("market", "vn_listing", {}, 60.0),
    ("market", "vn_fundamentals", {"symbol": "VCB"}, 60.0),
    ("market", "vn_retail_gold", {}, 30.0),
    ("market", "vn_retail_fx", {}, 30.0),
    ("market", "vs_auth_status", {}, 20.0),
    ("market", "vs_financeinfo", {"symbol": "VCB", "period": "quarter"}, 60.0),
    ("market", "vs_market_price", {}, 30.0),
    ("market", "vs_market_index", {}, 30.0),
    ("market", "vs_nn_flow", {}, 30.0),
    ("market", "vs_categories", {}, 30.0),
    ("market", "vs_indicator_data", {"category_id": 1}, 30.0),
    ("market", "vs_trading_info", {"symbol": "VCB"}, 30.0),
    ("market", "yf_global_indices", {}, 60.0),
    ("market", "yf_commodities", {}, 60.0),
    ("market", "yf_yield_curve", {}, 60.0),
    ("market", "dnse_ohlc_history", {"symbol": "VN30F1M", "resolution": 15}, 90.0),
    ("market", "dnse_latest_trade", {"symbols": ["VN30F1M"]}, 30.0),
    ("market", "dnse_foreign_flow", {}, 30.0),
    ("market", "dnse_ws_snapshot", {}, 30.0),
    ("scan", "stock_screener", {"limit": 5}, 60.0),
    ("scan", "signals_technical", {"symbol": "VCB"}, 60.0),
    ("scan", "sector_performance", {}, 20.0),
    ("scan", "money_flow", {}, 20.0),
    ("scan", "alert_check", {"rules": []}, 20.0),
    ("quant", "quant_backtest", {"symbol": "VCB"}, 120.0),
    ("quant", "quant_risk", {"returns": [0.01, -0.02, 0.03]}, 20.0),
    ("quant", "quant_factors", {}, 20.0),
    ("quant", "scenario_simulate", {"scenario": "VNINDEX -5% in a week"}, 20.0),
    ("brief", "brief_build", {"scope": "vn"}, 20.0),
    ("brief", "news_market", {"limit": 5}, 20.0),
    ("brief", "news_symbol", {"symbol": "VCB", "limit": 5}, 20.0),
    ("brief", "economic_calendar", {"scope": "vn"}, 20.0),
    ("brief", "corporate_calendar", {}, 20.0),
    ("intel", "world_prediction_odds", {"query": "Fed"}, 20.0),
    ("intel", "geo_intel", {}, 20.0),
    ("intel", "assets_rotation", {}, 20.0),
    ("intel", "compare_equities", {"symbols": ["VCB", "HPG"]}, 20.0),
    ("intel", "evidence_bundle", {"claim_ids": ["c1"]}, 20.0),
    ("intel", "oracle_meta", {}, 20.0),
    ("market", "vs_financial_terms", {}, 30.0),
    ("market", "vs_financial_norms", {"btype": 1}, 30.0),
    ("market", "vs_financial_values", {"symbol": "VCB", "btype": 1, "years": 1}, 120.0),
    ("market", "vs_company_info", {"symbol": "VCB"}, 30.0),
    ("market", "vs_overview_trading", {"symbol": "VCB"}, 30.0),
    ("market", "vs_documents", {"symbol": "VCB"}, 30.0),
    ("market", "vs_reports_search", {"symbol": "VCB"}, 30.0),
    ("market", "vs_industry_tree", {}, 30.0),
    ("market", "vs_stock_industry", {"industry_id": 5}, 30.0),
    ("market", "vs_industry_heatmap", {}, 30.0),
    ("market", "vs_selftrading", {}, 30.0),
    ("market", "vs_top_liquidity", {}, 30.0),
    ("market", "vs_gics_index", {}, 30.0),
    ("market", "vs_currency", {}, 30.0),
    ("market", "vs_market_info", {}, 30.0),
    ("market", "vs_news_search", {"query": "VCB"}, 30.0),
    ("market", "vs_xnk_detail", {"direction": "xk"}, 60.0),
    ("market", "vn_index_ohlcv", {"symbol": "VNINDEX", "count": 5}, 60.0),
    ("market", "vn_equity_ohlcv", {"symbol": "VCB", "count": 5}, 60.0),
    ("market", "vn_futures_ohlcv", {"symbol": "VN30F1M", "count": 5}, 60.0),
    ("market", "vn_forex_ohlcv", {"pair": "USDVND", "count": 5}, 60.0),
    ("market", "vn_crypto_ohlv", {"symbol": "BTCUSDT", "count": 5}, 60.0),
    ("market", "vn_global_index", {"symbol": "USA30", "count": 5}, 60.0),
    ("market", "vn_reference", {"exchange": "HOSE"}, 60.0),
    ("market", "vn_company", {"symbol": "VCB"}, 60.0),
    ("market", "vn_msn_fx_gold", {}, 60.0),
    ("market", "yf_world_indices", {}, 120.0),
    ("market", "yf_oracle_markets", {}, 150.0),
    ("market", "yf_regime_assets", {}, 150.0),
    ("market", "yf_mega_flows", {}, 120.0),
    ("market", "yf_alloc_history", {"asset": "GC"}, 120.0),
    ("market", "dnse_orderbook", {"symbol": "VN30F1M"}, 30.0),
    ("market", "dnse_foreign_rest", {"symbol": "VN30F1M"}, 30.0),
    ("market", "dnse_indices", {}, 30.0),
    ("market", "dnse_vn30f1m_live", {}, 120.0),
    ("market", "dnse_working_dates", {}, 30.0),
    ("market", "exchange_calendar", {}, 20.0),
    ("scan", "stock_forensic", {"symbol": "VCB"}, 90.0),
    ("scan", "valuation_run", {"symbol": "VCB"}, 60.0),
    ("scan", "fred_series", {"series_id": "DGS10"}, 30.0),
    ("scan", "world_macro_country", {"iso3": "VNM", "indicator": "NY.GDP.MKTP.KD.ZG"}, 30.0),
    ("scan", "world_fear_greed", {}, 30.0),
    ("scan", "sentiment_score", {"symbol": "VCB"}, 60.0),
    ("scan", "insider_trading", {"symbol": "VCB"}, 20.0),
    ("scan", "stock_overview", {"symbol": "VCB"}, 60.0),
    ("scan", "company_events", {"symbol": "VCB"}, 30.0),
    ("scan", "financial_statements", {"symbol": "VCB"}, 60.0),
    ("scan", "financial_ratios", {"symbol": "VCB"}, 30.0),
    ("scan", "peer_compare", {"symbol": "VCB", "peers": ["HPG"]}, 60.0),
    ("scan", "signals_scan", {"limit": 3}, 120.0),
    ("scan", "pattern_match", {"symbol": "VCB"}, 60.0),
    ("scan", "signals_trade_log", {}, 20.0),
    ("scan", "macro_reports", {"symbol": "VCB"}, 30.0),
    ("scan", "mega_flows", {}, 90.0),
    ("scan", "foreign_flow", {}, 30.0),
    ("scan", "oracle_health", {}, 20.0),
    ("scan", "event_stats", {"query": "stock market"}, 90.0),
    ("scan", "compare_assets", {"assets": ["GC=F", "BTC-USD"]}, 60.0),
    ("scan", "runs_list", {}, 20.0),
    ("scan", "run_get", {"run_id": "none"}, 20.0),
    ("scan", "doctor", {}, 20.0),
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


def calls_for_preset(preset: str) -> list[tuple[str, dict[str, Any], float]]:
    if preset == "all":
        return [(tool, args, timeout) for _, tool, args, timeout in MATRIX]
    return [(tool, args, timeout) for p, tool, args, timeout in MATRIX if p == preset]


async def run_preset_stdio(preset: str) -> list[dict[str, Any]]:
    """Spawn a local server exactly like an opencode local entry and check it."""
    client = VerifyClient(server_label="opentrading")
    command = [sys.executable, "-m", "opentrading_mcp", "serve", "--preset", preset]
    calls = calls_for_preset(preset)
    results = await client.run(calls, "stdio", command)
    rows: list[dict[str, Any]] = []
    for (tool, _, _), res in zip(calls, results, strict=True):
        violations = check_envelope(tool, res.payload) if res.ok else [res.detail]
        rows.append(
            {
                "preset": preset,
                "tool": tool,
                "transport": "stdio",
                "ok": res.ok and not violations,
                "seconds": round(res.seconds, 2),
                "availability": _availability(res.payload) if res.ok else "-",
                "detail": "; ".join(violations),
            }
        )
    return rows


async def run_preset_remote(url: str, preset: str) -> list[dict[str, Any]]:
    """Check the deployed server over StreamableHTTP (SSE fallback inside)."""
    client = VerifyClient(server_label="opentrading", timeout=120.0)
    calls = [
        (tool, args, max(timeout * 3, 90.0)) for tool, args, timeout in calls_for_preset(preset)
    ]
    results = await client.run(calls, "remote", url)
    rows: list[dict[str, Any]] = []
    for (tool, _, _), res in zip(calls, results, strict=True):
        violations = check_envelope(tool, res.payload) if res.ok else [res.detail]
        rows.append(
            {
                "preset": preset,
                "tool": tool,
                "transport": "remote",
                "ok": res.ok and not violations,
                "seconds": round(res.seconds, 2),
                "availability": _availability(res.payload) if res.ok else "-",
                "detail": "; ".join(violations),
            }
        )
    return rows


def _availability(payload: Any) -> str:
    text = extract_text(payload)
    if text is None:
        return "?"
    try:
        return str(json.loads(text).get("availability", "?"))
    except ValueError:
        return "?"
