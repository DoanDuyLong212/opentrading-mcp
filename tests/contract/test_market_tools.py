from opentrading_mcp.server import create_server, register_all


def test_full_surface_contains_market_core():
    server = create_server()
    tools = register_all(server)
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names)) > 100
    assert "market_snapshot" in names
    assert "source_status" in names
    assert "vn_quote_history" in names
    assert "vs_financeinfo" in names
    assert "yf_global_indices" in names
    assert "dnse_ohlc_history" in names
