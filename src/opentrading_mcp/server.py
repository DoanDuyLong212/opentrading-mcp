"""FastMCP server factory with the 5 locked gaps.

Gap mapping (opencode / Claude / Cursor):
1. instructions -> FastMCP(instructions=...) read at initialize.
2. roots -> server never assumes roots; tools work with or without ListRoots.
3. cancel/progress -> tools accept Context and use ctx.report_progress + ctx.log;
   long tools check cancellation via request_context.
4. logging -> never print() to stdout; ctx.log routes to MCP logging channel,
   local fallback goes to stderr.
5. timeouts -> TIMEOUT_MATRIX is the contract; clients configure their side
   (opencode per-server ms, Codex tool_timeout_sec).
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from opentrading_mcp.app import OpenTradingMCP

# Read by clients at initialize (Claude Code and OpenTrading cap it at 2048 chars):
# a routing guide, not a parameter reference — codes live in the term-types resource.
SERVER_INSTRUCTIONS = (
    "OpenTrading: Vietnam stock market (HOSE/HNX/UPCOM) plus global market data. "
    "Times are Asia/Ho_Chi_Minh.\n"
    "Every result is JSON {data, provenance{source, as_of, timezone}, warnings[], availability}. "
    "availability: available | partial (use what came back, read warnings) | "
    "empty (valid 'no data', do not retry) | unavailable (isError; try the fallback "
    "named in warnings once). Cite provenance.source and as_of with every number.\n"
    "Routing: unsure ticker -> symbol_lookup. Market pulse -> market_overview. "
    "Price history -> vn_quote_history; many symbols -> vn_equity_quote_batch or "
    "market_candles_batch. Foreign/prop flows -> money_flow. Company -> stock_overview, "
    "financial_statements, company_events, signals_technical, valuation_run. "
    "Screening -> stock_screener. VN macro -> vs_indicator_data, sbv_rates; global -> "
    "fred_series, yf_world_indices. News -> news_symbol, news_market. "
    "Backtests -> quant_backtest, backtest_strategies. Data problems -> source_status.\n"
    "At most 5 calls in parallel (Vietstock tools 4, Yahoo tools 3). "
    "Code tables (btype, tids, termTypeID): resource opentrading://reference/term-types. "
    "Tool names refer to preset all; smaller presets expose a subset."
)

TIMEOUT_MATRIX: dict[str, int] = {
    "tools_list": 30,
    "market_snapshot": 15,
    "breadth_scan": 15,
    "yf_mega_flows": 60,
    "dnse_ohlc_history": 60,
    "quant_backtest": 120,
    "quant_factors": 120,
    "stock_screener": 60,
    "signals_screener_columns": 30,
    "watchlist_get": 30,
    "alert_check": 30,
}

PRESETS = ("market", "scan", "quant", "brief", "intel", "all")

PRESET_MODULES: dict[str, tuple[str, ...]] = {
    "market": (
        "market",
        "web",
        "vn",
        "vs",
        "vs_bctc",
        "vn_ext",
        "yf",
        "yf_world",
        "dnse_tools",
        "dnse_ext",
        "crypto",
    ),
    "scan": ("scan", "compute", "watchlist", "corp"),
    "quant": ("quant",),
    "brief": ("brief",),
    "intel": ("intel", "web"),
    "all": (
        "market",
        "vn",
        "vs",
        "vs_bctc",
        "vn_ext",
        "yf",
        "yf_world",
        "dnse_tools",
        "dnse_ext",
        "crypto",
        "scan",
        "compute",
        "corp",
        "watchlist",
        "quant",
        "brief",
        "intel",
        "web",
    ),
}

# Market-data agent scope per spec needs the full vs/vn/dnse/yf set in one
# preset; every other preset stays lean to keep tools/list fast.
# scan raised 50->60 for the corp research module (P6).
# market raised 70->75 for the crypto module (P6).
PRESET_CAPS = {"market": 75, "scan": 60, "quant": 50, "brief": 50, "intel": 50}

_REGISTER_BY_MODULE = {
    "market": "register_market_tools",
    "vn": "register_vn_tools",
    "vs": "register_vs_tools",
    "vs_bctc": "register_vs_bctc_tools",
    "vn_ext": "register_vn_ext_tools",
    "yf": "register_yf_tools",
    "yf_world": "register_yf_world_tools",
    "dnse_tools": "register_dnse_tools",
    "dnse_ext": "register_dnse_ext_tools",
    "crypto": "register_crypto_tools",
    "scan": "register_scan_tools",
    "compute": "register_compute_tools",
    "corp": "register_corp_tools",
    "watchlist": "register_watchlist_tools",
    "quant": "register_quant_tools",
    "brief": "register_brief_tools",
    "intel": "register_intel_tools",
    "web": "register_web_tools",
}


def transport_security() -> TransportSecuritySettings | None:
    raw = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return None
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts)


def create_server(preset: str = "market") -> FastMCP:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}, expected one of {PRESETS}")
    return OpenTradingMCP(
        "opentrading",
        instructions=SERVER_INSTRUCTIONS,
        stateless_http=True,
        streamable_http_path="/mcp",
        sse_path="/sse",
        json_response=False,
        transport_security=transport_security(),
    )


def register_preset(server: FastMCP, preset: str = "market") -> list[dict[str, Any]]:
    """Register every tool module for a preset; returns tool descriptors."""
    import importlib

    from opentrading_mcp.prompts import register_prompts
    from opentrading_mcp.resources import register_resources

    collected: list[dict[str, Any]] = []
    for module in PRESET_MODULES[preset]:
        func_name = _REGISTER_BY_MODULE[module]
        mod = importlib.import_module(f"opentrading_mcp.tools.{module}")
        collected.extend(getattr(mod, func_name)(server))
    register_prompts(server)
    register_resources(server)
    server._opentrading_preset = preset  # type: ignore[attr-defined]  # read by resources
    names = [t["name"] for t in collected]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate tool names in preset {preset!r}")
    if preset != "all" and len(collected) > PRESET_CAPS.get(preset, 50):
        raise ValueError(f"preset {preset!r} has {len(collected)} tools over cap")
    return collected
