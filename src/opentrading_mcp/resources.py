"""MCP resources: static references + live tool catalog (EODHD pattern).

Resources are read-only reference data; the tool catalog is generated
from the tools registered on the server instance.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

TOOL_CATALOG_URI = "opentrading://catalog/tools"
TERM_TYPES_URI = "opentrading://reference/term-types"
EXCHANGES_URI = "opentrading://reference/exchanges"
GICS_URI = "opentrading://reference/gics"

_TERM_TYPES = {
    "termTypeID": {
        "1": "daily",
        "2": "monthly",
        "3": "quarterly",
        "4": "yearly",
        "5": "YTD",
        "6": "MoM",
        "7": "YoY",
        "8": "QoQ",
    },
    "tids": {
        "1": "full-year",
        "2": "Q1",
        "3": "Q2",
        "4": "Q3",
        "5": "Q4",
        "9": "half-year",
        "12": "9M",
    },
    "btype": {"1": "general", "2": "securities", "3": "bank", "5": "insurance"},
    "interval_vs_resolution": {
        "interval": "bar size for vn quotes (1D daily; 1m/15m intraday where supported)",
        "resolution": "bar size in minutes for DNSE ohlc (1/5/15/30/60)",
    },
    "page_sizes": {"financeinfo": 4, "document": 60, "dnse_ohlc": 10000},
}

_EXCHANGES = {
    "timezone": "Asia/Ho_Chi_Minh",
    "venues": {
        "HOSE": {
            "session": "09:00-11:30, 13:00-15:00",
            "auction": "ATO 09:00-09:15, ATC 14:30-14:45",
        },
        "HNX": {"session": "09:00-11:30, 13:00-15:00", "auction": "continuous, no ATO/ATC"},
        "UPCOM": {"session": "09:00-11:30, 13:00-15:00", "auction": "continuous, no price limits"},
    },
    "settlement": "T+2",
}

_GICS = {
    "sectors": [
        "Energy",
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Consumer Staples",
        "Health Care",
        "Financials",
        "Information Technology",
        "Communication Services",
        "Utilities",
        "Real Estate",
    ]
}


def build_tool_catalog(server: Any) -> str:
    """JSON catalog of tools registered on this server instance (single surface)."""
    tools: list[dict[str, str]] = []
    manager = getattr(server, "_tool_manager", None)
    registry = getattr(manager, "_tools", {}) if manager is not None else {}
    for name in sorted(registry):
        desc = (registry[name].description or "").strip().split("\n")[0]
        tools.append({"name": name, "description": desc})
    return json.dumps({"preset": "all", "count": len(tools), "tools": tools})


def build_term_types() -> str:
    return json.dumps(_TERM_TYPES)


def register_resources(server: FastMCP) -> list[str]:
    @server.resource(TOOL_CATALOG_URI, description="Live catalog of registered tools.")
    def tool_catalog() -> str:
        return build_tool_catalog(server)

    @server.resource(TERM_TYPES_URI, description="termTypeID/tids/btype/page-size maps.")
    def term_types() -> str:
        return build_term_types()

    @server.resource(EXCHANGES_URI, description="VN venues, sessions and settlement.")
    def exchanges() -> str:
        return json.dumps(_EXCHANGES)

    @server.resource(GICS_URI, description="GICS top-level sectors.")
    def gics() -> str:
        return json.dumps(_GICS)

    return [TOOL_CATALOG_URI, TERM_TYPES_URI, EXCHANGES_URI, GICS_URI]
