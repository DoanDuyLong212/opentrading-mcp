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

from typing import Any

from mcp.server.fastmcp import FastMCP

SERVER_INSTRUCTIONS = (
    "OpenTrading market-data MCP. Timezone Asia/Ho_Chi_Minh tz-aware. "
    "Tool names snake_case prefixed by source (vs_|vn_|yf_|dnse_|world_|signals_|"
    "quant_|brief_|intel_). "
    "Params: btype auto 1 CTCP/2 CK/3 Bank/5 BH, tids [1,2,3,4,5,9,12], "
    "termTypeID 1-8, interval (1D/1h/4h) vs resolution (1m/15m), "
    "source_order VCI->KBS, pageSize 4 financeinfo / 60 document / 10000 DNSE ohlc. "
    "TTL: snapshot 5s, market 60s, world 60-300s, overview 15m, "
    "financeinfo 6h, docs 24h, categories 7d, odds 45m."
)

TIMEOUT_MATRIX: dict[str, int] = {
    "tools_list": 30,
    "market_snapshot": 15,
    "breadth_scan": 15,
    "vs_financial_values": 60,
    "yf_mega_flows": 60,
    "dnse_ohlc_history": 60,
    "quant_backtest": 120,
    "quant_factors": 120,
}

PRESETS = ("market", "scan", "quant", "brief", "intel", "all")

PRESET_MODULES: dict[str, tuple[str, ...]] = {
    "market": ("market", "vn", "vs", "yf", "dnse_tools"),
    "scan": ("scan",),
    "quant": ("quant",),
    "brief": ("brief",),
    "intel": ("intel",),
    "all": ("market", "vn", "vs", "yf", "dnse_tools", "scan", "quant", "brief", "intel"),
}

_REGISTER_BY_MODULE = {
    "market": "register_market_tools",
    "vn": "register_vn_tools",
    "vs": "register_vs_tools",
    "yf": "register_yf_tools",
    "dnse_tools": "register_dnse_tools",
    "scan": "register_scan_tools",
    "quant": "register_quant_tools",
    "brief": "register_brief_tools",
    "intel": "register_intel_tools",
}


def create_server(preset: str = "market") -> FastMCP:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}, expected one of {PRESETS}")
    return FastMCP(
        "opentrading",
        instructions=SERVER_INSTRUCTIONS,
        stateless_http=True,
        streamable_http_path="/mcp",
        sse_path="/sse",
        json_response=False,
    )


def register_preset(server: FastMCP, preset: str = "market") -> list[dict[str, Any]]:
    """Register every tool module for a preset; returns tool descriptors."""
    import importlib

    collected: list[dict[str, Any]] = []
    for module in PRESET_MODULES[preset]:
        func_name = _REGISTER_BY_MODULE[module]
        mod = importlib.import_module(f"opentrading_mcp.tools.{module}")
        collected.extend(getattr(mod, func_name)(server))
    names = [t["name"] for t in collected]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate tool names in preset {preset!r}")
    if preset != "all" and len(collected) > 50:
        raise ValueError(f"preset {preset!r} has {len(collected)} tools, cap is 50")
    return collected
