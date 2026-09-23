from opentrading_mcp.server import PRESETS, SERVER_INSTRUCTIONS, TIMEOUT_MATRIX, create_server


def test_server_boot_market_preset():
    server = create_server("market")
    assert server.name == "opentrading"
    assert "Asia/Ho_Chi_Minh" in SERVER_INSTRUCTIONS
    assert TIMEOUT_MATRIX["tools_list"] == 30
    assert TIMEOUT_MATRIX["market_snapshot"] == 15
    assert TIMEOUT_MATRIX["quant_backtest"] == 120
    assert "market" in PRESETS
