import asyncio

from opentrading_mcp.cli import add_health_routes
from opentrading_mcp.server import create_server, register_all


def test_all_preset_lists_and_health_routes():
    server = create_server()
    tools = register_all(server)
    names = sorted(t["name"] for t in tools)
    assert "quant_backtest" in names
    assert "brief_build" in names
    assert "world_prediction_odds" in names
    assert "evidence_bundle" in names
    add_health_routes(server)
    listed = asyncio.run(server.list_tools())
    assert len(listed) == len(tools)
