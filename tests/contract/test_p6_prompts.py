"""P6 contract: MCP prompts + resources (TDD RED)."""

from __future__ import annotations

import json

from opentrading_mcp.server import create_server, register_preset


def _server_with_tools(preset: str = "market"):
    server = create_server(preset)
    register_preset(server, preset)
    return server


async def test_register_prompts_exposes_four():
    from opentrading_mcp.prompts import register_prompts

    server = create_server("market")
    names = register_prompts(server)
    assert sorted(names) == [
        "ai_detect",
        "morning_briefing",
        "pre_earnings",
        "risk_check",
        "sector_rotation",
        "ticker_analysis",
    ]
    listed = await server.list_prompts()
    assert {p.name for p in listed} == set(names)


async def test_prompt_renders_tool_plan():
    from opentrading_mcp.prompts import register_prompts

    server = create_server("market")
    register_prompts(server)
    out = await server.get_prompt("ticker_analysis", {"symbol": "VCB"})
    text = out.messages[0].content.text
    assert "VCB" in text
    for tool in ("signals_technical", "valuation_run", "company_events"):
        assert tool in text


async def test_register_resources_exposes_four_uris():
    from opentrading_mcp.resources import register_resources

    server = _server_with_tools()
    uris = register_resources(server)
    assert sorted(uris) == [
        "opentrading://catalog/tools",
        "opentrading://reference/exchanges",
        "opentrading://reference/gics",
        "opentrading://reference/term-types",
    ]
    listed = await server.list_resources()
    assert {str(r.uri) for r in listed} == set(uris)


async def test_tool_catalog_resource_matches_registered_tools():
    from opentrading_mcp.resources import build_tool_catalog

    server = _server_with_tools()
    catalog = json.loads(build_tool_catalog(server))
    assert catalog["preset"] == "market"
    assert catalog["count"] == len(catalog["tools"]) > 50
    by_name = {t["name"]: t for t in catalog["tools"]}
    assert "market_snapshot" in by_name
    assert by_name["market_snapshot"]["description"].startswith("Snapshot of VN market")


async def test_term_types_resource_covers_key_maps():
    from opentrading_mcp.resources import build_term_types

    ref = json.loads(build_term_types())
    assert ref["termTypeID"]["3"] == "quarterly"
    assert "9" in ref["tids"]
    assert ref["btype"]["2"] == "securities"
