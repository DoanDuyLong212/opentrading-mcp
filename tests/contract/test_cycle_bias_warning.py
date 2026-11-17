"""Contract test: cycle statistics disclose survivorship bias (Issue #143).

Delisted or suspended names since 2018 are excluded from static basket history;
every cycle basket tool output must include the survivorship warning.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.tools import cycle_db
from opentrading_mcp.tools.cycle_stats import SURVIVORSHIP_WARNING


@pytest.fixture
def server():
    srv = create_server()
    register_all(srv)
    return srv


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("cycle_seasonality", {"basket": "bank", "month": 1}),
        ("cycle_chains", {"pair": "bank-securities"}),
        ("cycle_tet", {"basket": "bank"}),
        ("cycle_yearly", {"basket": "bank", "year": 2024}),
        ("cycle_trough_events", {}),
    ],
)
async def test_cycle_stats_include_survivorship_warning_on_data(
    server, monkeypatch: pytest.MonkeyPatch, tool_name: str, args: dict
) -> None:
    # Fake DB select returning dummy row
    dummy_row = (
        "bank", 1, 0.05, 0.8, 0.02, 10,
        "extra1", "extra2", "extra3", "extra4", "extra5", "extra6",
        "extra7", "extra8", "extra9", "extra10", "extra11", "extra12",
    )
    monkeypatch.setattr(cycle_db, "_select", lambda sql, a: [dummy_row])
    tool = server._tool_manager.get_tool(tool_name)
    res = await tool.run(args)
    assert "warnings" in res, f"{tool_name} missing warnings key in envelope"
    assert SURVIVORSHIP_WARNING in res["warnings"], f"{tool_name} missing survivorship warning"


@pytest.mark.asyncio
async def test_cycle_seasonality_filtered_empty_includes_warning(
    server, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cycle_db, "_select", lambda sql, a: [])
    tool = server._tool_manager.get_tool("cycle_seasonality")
    res = await tool.run({"basket": "bank", "month": 1})
    assert "warnings" in res
    assert SURVIVORSHIP_WARNING in res["warnings"]
