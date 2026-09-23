from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_mongo_anywhere():
    text = (ROOT / "docker-compose.mcp.yml").read_text()
    assert "mongo" not in text.lower()
    init = (ROOT / "docker" / "postgres" / "init.sql").read_text()
    assert "mcp_auth_tokens" in init
    assert "mcp_tool_usage" in init
    assert "reports" in init
