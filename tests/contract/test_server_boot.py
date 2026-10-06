from opentrading_mcp.server import SERVER_INSTRUCTIONS, create_server, register_all


def test_server_boot_full_surface():
    server = create_server()
    assert server.name == "opentrading"
    assert "Asia/Ho_Chi_Minh" in SERVER_INSTRUCTIONS
    # full surface, single shape
    tools = register_all(server)
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names)) > 100
