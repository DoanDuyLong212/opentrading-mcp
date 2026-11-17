"""#145: async tool bodies must not block the loop; cache keys must not embed data.

``dnse_foreign_flow`` used to call the network-Redis snapshot reader directly
inside the coroutine, and ``quant_risk`` used the whole returns list as its
cache fingerprint (huge keys straight into Redis).
"""

from __future__ import annotations


def _tool(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("all")
    register_preset(server, "all")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


async def test_dnse_foreign_flow_reads_snapshot_off_the_loop(monkeypatch):
    from opentrading_mcp.tools import dnse_tools as dt

    seen: list[str] = []

    async def fake_run_blocking(fn, tool, timeout_secs=60.0, **kwargs):
        seen.append(getattr(fn, "__name__", str(fn)))
        return {"scope": "VN30F1M", "flow": {"buy": 1.0, "sell": -2.0}}

    monkeypatch.setattr(dt, "run_blocking", fake_run_blocking)
    env = await _tool("dnse_foreign_flow")()
    assert seen == ["ws_foreign_snapshot"], (
        "the snapshot read must go through run_blocking, not run on the loop"
    )
    assert env["data"]["flow"]["buy"] == 1.0


async def test_quant_risk_cache_key_is_hashed(monkeypatch):
    from opentrading_mcp.tools import quant_stats as qs

    seen: list[str] = []

    async def fake_lookup(name: str, fp: str):
        seen.append(fp)
        return None

    monkeypatch.setattr(qs, "cache_lookup", fake_lookup)
    big = [0.001 * (i % 7) for i in range(400)]
    await _tool("quant_risk")(returns=big, periods_per_year=252)
    fp1 = seen[-1]
    assert len(fp1) <= 80, "the returns list must not become a Redis key"
    assert "0.001" not in fp1
    # deterministic: the same input hashes to the same key
    await _tool("quant_risk")(returns=list(big), periods_per_year=252)
    assert seen[-1] == fp1
    # and a different input hashes differently
    await _tool("quant_risk")(returns=[0.002 * (i % 5) for i in range(400)], periods_per_year=252)
    assert seen[-1] != fp1


def test_no_direct_snapshot_calls_in_async_bodies():
    """Grep guard (#145): dnse_foreign_flow must not call the network reader inline."""
    import pathlib
    import re

    src = (pathlib.Path("src/opentrading_mcp/tools") / "dnse_tools.py").read_text("utf-8")
    start = src.index("async def dnse_foreign_flow(")
    nxt = src.find("    @server.tool", start + 1)
    body = src[start : nxt if nxt != -1 else len(src)]
    inline = [
        m
        for m in re.finditer(r"dnse_p\.ws_foreign_snapshot\(", body)
        if "run_blocking" not in body[max(0, m.start() - 40) : m.start()]
    ]
    assert not inline, (
        "dnse_foreign_flow calls ws_foreign_snapshot directly on the loop; wrap it in run_blocking"
    )
