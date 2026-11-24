"""#143: basket statistics are computed from *current* constituents.

Delisted or suspended names are absent from the whole history, so long-run
basket returns are biased upward. Every basket-based cycle-statistics output
must say so in ``warnings`` — otherwise a model quotes the number as if it were
a tradable, point-in-time return.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.schemas import make_envelope

BASKET_TOOLS = (
    "cycle_seasonality",
    "cycle_chains",
    "cycle_tet",
    "cycle_yearly",
    "cycle_trough_events",
)


def _tool(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("all")
    register_preset(server, "all")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, name
    return tool.fn


@pytest.fixture
def empty_table(monkeypatch):
    """read_rows returns one dummy row so every tool reaches its success path."""
    from opentrading_mcp.tools import cycle_db

    async def fake_read_rows(tool, source, sql, args, cols, filtered=False):
        return make_envelope({"rows": [dict.fromkeys(cols, 1)]}, source=source)

    monkeypatch.setattr(cycle_db, "read_rows", fake_read_rows)


@pytest.mark.parametrize("name", BASKET_TOOLS)
async def test_basket_stat_output_warns_about_current_members_only(empty_table, name):
    env = await _tool(name)()
    joined = " ".join(env["warnings"]).lower()
    assert "delisted" in joined or "suspended" in joined, env["warnings"]
    assert "current" in joined, env["warnings"]


@pytest.mark.parametrize("name", BASKET_TOOLS)
async def test_warning_survives_the_not_seeded_path(monkeypatch, name):
    """An empty table is exactly when a model is tempted to read stale numbers."""
    from opentrading_mcp.tools import cycle_db

    async def fake_read_rows(tool, source, sql, args, cols, filtered=False):
        return make_envelope(
            {"tool": tool},
            source="unavailable",
            warnings=["cycle tables not seeded"],
            availability="unavailable",
        )

    monkeypatch.setattr(cycle_db, "read_rows", fake_read_rows)
    env = await _tool(name)()
    joined = " ".join(env["warnings"]).lower()
    assert "cycle tables not seeded" in joined
    assert "current" in joined and ("delisted" in joined or "suspended" in joined)
