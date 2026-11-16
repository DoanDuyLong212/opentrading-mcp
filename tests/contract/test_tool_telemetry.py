"""#127: tool telemetry is measured around the tool, not from the HTTP status.

On prod (16/11/2026) every timed-out vn_retail_gold call was logged as
{"ok": true, "duration_ms": 4.0}: the streamed response sent its headers before the
tool ran, and a failed tool is still HTTP 200.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from opentrading_mcp import obs
from opentrading_mcp.server import create_server, register_all


def _server_with(fn_factory: Any) -> Any:
    server = create_server()

    @server.tool()
    async def probe_tool() -> dict[str, Any]:
        return await fn_factory()

    obs.apply_tool_telemetry(server)
    return server


async def test_unavailable_envelope_is_an_error_with_its_reason(capsys):
    obs.reset()
    obs.enable_tool_call_log()
    try:

        async def slow_timeout() -> dict[str, Any]:
            await asyncio.sleep(0.05)
            return {"data": {}, "availability": "unavailable", "reason": "upstream_timeout"}

        server = _server_with(slow_timeout)
        await server._tool_manager.get_tool("probe_tool").fn()
    finally:
        obs.enable_tool_call_log(False)
    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert line["event"] == "tool_call" and line["tool"] == "probe_tool"
    assert line["ok"] is False
    assert line["error_code"] == "upstream_timeout"
    assert line["duration_ms"] >= 45  # the real tool time, not the time to headers
    metrics = obs.render_metrics()
    assert 'tool_errors_total{tool="probe_tool",error="upstream_timeout"} 1' in metrics
    assert 'tool_calls_total{tool="probe_tool"} 1' in metrics


async def test_available_envelope_is_ok_and_stdio_stays_quiet(capsys):
    obs.reset()
    obs.enable_tool_call_log(False)  # an HTTP app built by an earlier test turns it on

    async def fine() -> dict[str, Any]:
        return {"data": {"rows": [1]}, "availability": "available"}

    server = _server_with(fine)
    await server._tool_manager.get_tool("probe_tool").fn()
    assert capsys.readouterr().err == ""  # the log line is off unless HTTP enables it
    metrics = obs.render_metrics()
    assert 'tool_calls_total{tool="probe_tool"} 1' in metrics
    assert "tool_errors_total{" not in metrics


async def test_exception_is_recorded_and_reraised():
    obs.reset()

    async def boom() -> dict[str, Any]:
        raise RuntimeError("x")

    server = _server_with(boom)
    try:
        await server._tool_manager.get_tool("probe_tool").fn()
    except RuntimeError:
        pass
    else:
        raise AssertionError("the exception must propagate")
    assert 'error="exception"' in obs.render_metrics()


def test_every_registered_tool_is_wrapped_once():
    server = create_server()
    register_all(server)
    obs.apply_tool_telemetry(server)  # a second pass must not double-wrap
    for tool in server._tool_manager.list_tools():
        assert getattr(tool.fn, "__ot_telemetry__", False), tool.name
        assert not getattr(getattr(tool.fn, "__wrapped__", None), "__ot_telemetry__", False)


async def test_a_cancelled_call_is_not_counted_as_an_exception():
    obs.reset()

    async def hang() -> dict[str, Any]:
        await asyncio.sleep(10)
        return {}

    server = _server_with(hang)
    task = asyncio.ensure_future(server._tool_manager.get_tool("probe_tool").fn())
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    metrics = obs.render_metrics()
    assert 'error="cancelled"' in metrics
    assert 'error="exception"' not in metrics
