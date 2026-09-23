from opentrading_mcp.server import PRESET_CAPS, PRESET_MODULES, create_server, register_preset


def test_market_preset_tool_count_under_50():
    server = create_server("market")
    tools = register_preset(server, "market")
    assert 1 <= len(tools) <= PRESET_CAPS["market"]
    names = [t["name"] for t in tools]
    assert "market_snapshot" in names
    assert "source_status" in names
    assert "vn_quote_history" in names
    assert "vs_financeinfo" in names
    assert "yf_global_indices" in names
    assert "dnse_ohlc_history" in names


def test_all_presets_capped_except_all():
    for preset in PRESET_MODULES:
        server = create_server(preset)
        tools = register_preset(server, preset)
        assert len(tools) >= 1
        if preset != "all":
            assert len(tools) <= PRESET_CAPS[preset], preset
