"""Intel preset: odds, geo, regime, compare, redteam, evidence bundle."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY


def register_intel_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def world_prediction_odds(query: str | None = None) -> dict[str, Any]:
        """Prediction-market odds via jina proxy to Gamma, then Kalshi. Use for Fed/macro odds."""
        return make_envelope(
            {"query": query, "events": [], "note": "wire jina->Gamma cache 45m next"},
            source="stub",
            availability="empty",
        )

    @server.tool(annotations=READ_ONLY)
    async def geo_intel(topic: str | None = None) -> dict[str, Any]:
        """Geopolitical hotspots and escalation. Use when geopolitics threatens markets."""
        return make_envelope({"topic": topic, "hotspots": []}, source="stub", availability="empty")

    @server.tool(annotations=READ_ONLY)
    async def assets_rotation() -> dict[str, Any]:
        """Cross-asset phases and RISK-ON/OFF regime. Use when positioning across regimes."""
        return make_envelope(
            {"regime": "unknown", "note": "wire yf_regime_assets next"},
            source="stub",
            availability="empty",
        )

    @server.tool(annotations=READ_ONLY)
    async def compare_equities(symbols: list[str]) -> dict[str, Any]:
        """Head-to-head ratios, growth and price action. Use when picking tickers."""
        return make_envelope({"symbols": symbols, "rows": []}, source="stub", availability="empty")

    @server.tool(annotations=READ_ONLY)
    async def evidence_bundle(claim_ids: list[str]) -> dict[str, Any]:
        """Lock weighted conclusion by evidence bundle. Use last for final verdict."""
        return make_envelope({"claims": claim_ids, "locked": False}, source="local")

    @server.tool(annotations=READ_ONLY)
    async def oracle_meta() -> dict[str, Any]:
        """Aggregator snapshot plus source health. Use for dashboard meta."""
        return make_envelope({"aggregator": "stub", "health": "see source_status"}, source="local")

    return [
        {"name": "world_prediction_odds"},
        {"name": "geo_intel"},
        {"name": "assets_rotation"},
        {"name": "compare_equities"},
        {"name": "evidence_bundle"},
        {"name": "oracle_meta"},
    ]
