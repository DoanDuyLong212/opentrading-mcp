"""FastMCP server factory — single full tool surface (no presets).

Lịch sử: server từng chia --preset market/scan/... (custom, không phải chuẩn MCP).
Từ bản này server luôn expose full tools/list; client lọc phía mình
(OpenTrading activeTools, opencode glob, Cursor toggle, Claude tool search).
Giữ CLI --preset như deprecated alias để tương thích.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

SERVER_INSTRUCTIONS = (
    "OpenTrading market-data MCP. Timezone Asia/Ho_Chi_Minh tz-aware. "
    "Single full tools/list; clients filter (OpenTrading activeTools, opencode glob, "
    "Cursor toggle, Claude tool search). "
    "Envelope {data, provenance{source,as_of,timezone}, warnings[], availability}. "
    "Detail maps: termTypeID/tids/btype in opentrading://reference/term-types. "
    "Long lists support limit/offset+columns/summary; results may include "
    "page{total,offset,limit,next}."
)

# Xóa TIMEOUT_MATRIX stale (11 entries/138 tools). Per-tool timeout qua
# run_blocking(secs=) + client toolTimeoutMs. Giữ tên để tương thích import cũ.
TIMEOUT_MATRIX: dict[str, int] = {}

# Full module surface — thứ tự ổn định để tools/list ổn định (cache-friendly).
ALL_MODULES: tuple[str, ...] = (
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
    "compute_financial",
    "compute_intel",
    "compute_infra",
    "corp",
    "watchlist",
    "quant_backtest",
    "quant_stats",
    "brief",
    "intel",
    "web",
    "cycle_stats",
    "asset_cycle",
)

# Deprecated compat: PRESETS/PRESET_MODULES/PRESET_CAPS giữ để import cũ không vỡ.
PRESETS = ("all", "market", "scan", "quant", "brief", "intel")
PRESET_MODULES: dict[str, tuple[str, ...]] = {
    "market": ALL_MODULES,
    "scan": ALL_MODULES,
    "quant": ALL_MODULES,
    "brief": ALL_MODULES,
    "intel": ALL_MODULES,
    "all": ALL_MODULES,
}
PRESET_CAPS: dict[str, int] = {}

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
    "compute_financial": "register_compute_financial_tools",
    "compute_intel": "register_compute_intel_tools",
    "compute_infra": "register_compute_infra_tools",
    "corp": "register_corp_tools",
    "watchlist": "register_watchlist_tools",
    "quant_backtest": "register_quant_backtest_tools",
    "quant_stats": "register_quant_stats_tools",
    "brief": "register_brief_tools",
    "intel": "register_intel_tools",
    "web": "register_web_tools",
    "cycle_stats": "register_cycle_stats_tools",
    "asset_cycle": "register_asset_cycle_tools",
}


def transport_security() -> TransportSecuritySettings | None:
    raw = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return None
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts)


def create_server(preset: str = "all") -> FastMCP:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}, expected one of {PRESETS}")
    return FastMCP(
        "opentrading",
        instructions=SERVER_INSTRUCTIONS,
        stateless_http=True,
        streamable_http_path="/mcp",
        sse_path="/sse",
        json_response=False,
        transport_security=transport_security(),
    )


def register_all(server: FastMCP) -> list[dict[str, Any]]:
    """Register full tool surface; returns tool descriptors (single shape)."""
    import importlib

    from opentrading_mcp.prompts import register_prompts
    from opentrading_mcp.resources import register_resources

    collected: list[dict[str, Any]] = []
    for module in ALL_MODULES:
        func_name = _REGISTER_BY_MODULE[module]
        mod = importlib.import_module(f"opentrading_mcp.tools.{module}")
        collected.extend(getattr(mod, func_name)(server))
    register_prompts(server)
    register_resources(server)
    names = [t["name"] for t in collected]
    if len(names) != len(set(names)):
        raise ValueError("duplicate tool names in full surface")
    return collected


def register_preset(server: FastMCP, preset: str = "all") -> list[dict[str, Any]]:
    """Deprecated alias: mọi preset đều trả full surface (tương thích CLI cũ)."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}, expected one of {PRESETS}")
    return register_all(server)
