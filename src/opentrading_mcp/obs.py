"""Observability: one JSON log line per tool call + Prometheus metrics.

Never logs arguments, results, or headers — tool name, timing and error
code only (upstream responses may contain PII).
"""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any

_lock = threading.Lock()
_calls: dict[str, int] = {}
_errors: dict[tuple[str, str], int] = {}
_latency_ms_sum: dict[str, float] = {}
_latency_ms_max: dict[str, float] = {}
_upstream_failures: dict[str, int] = {}

# Cardinality cap: tool names come from request bodies (tool_name_of), so a
# scanner sending crafted method names must not grow these dicts (and the
# /metrics output) without bound. Overflow folds into "other".
MAX_SERIES = 500


def _series(tool: str, table: dict) -> str:
    if tool in table or len(table) < MAX_SERIES:
        return tool
    return "other"


def reset() -> None:
    with _lock:
        _calls.clear()
        _errors.clear()
        _latency_ms_sum.clear()
        _latency_ms_max.clear()
        _upstream_failures.clear()


def record_tool_call(tool: str, duration_ms: float, ok: bool, error_code: str = "") -> None:
    with _lock:
        tool = _series(tool, _calls)
        _calls[tool] = _calls.get(tool, 0) + 1
        _latency_ms_sum[tool] = _latency_ms_sum.get(tool, 0.0) + duration_ms
        _latency_ms_max[tool] = max(_latency_ms_max.get(tool, 0.0), duration_ms)
        if not ok:
            key = (_series(tool, _calls), error_code or "unknown")
            _errors[key] = _errors.get(key, 0) + 1


def record_upstream_failure(upstream: str) -> None:
    with _lock:
        _upstream_failures[upstream] = _upstream_failures.get(upstream, 0) + 1


def log_tool_call(tool: str, duration_ms: float, ok: bool, error_code: str = "") -> None:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": "tool_call",
        "tool": tool,
        "duration_ms": round(duration_ms, 1),
        "ok": ok,
        "error_code": error_code or None,
    }
    print(json.dumps(entry), file=sys.stderr, flush=True)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_metrics() -> str:
    with _lock:
        calls = dict(_calls)
        errors = dict(_errors)
        latency_sum = dict(_latency_ms_sum)
        latency_max = dict(_latency_ms_max)
        upstream = dict(_upstream_failures)
    lines: list[str] = [
        "# HELP tool_calls_total Total MCP tool calls per tool.",
        "# TYPE tool_calls_total counter",
    ]
    for tool in sorted(calls):
        lines.append(f'tool_calls_total{{tool="{_escape(tool)}"}} {calls[tool]}')
    lines += [
        "# HELP tool_errors_total Failed MCP tool calls per tool and error.",
        "# TYPE tool_errors_total counter",
    ]
    for tool, error in sorted(errors):
        count = errors[(tool, error)]
        lines.append(
            f'tool_errors_total{{tool="{_escape(tool)}",error="{_escape(error)}"}} {count}'
        )
    lines += [
        "# HELP tool_latency_ms_sum Total tool latency in milliseconds.",
        "# TYPE tool_latency_ms_sum counter",
        "# HELP tool_latency_ms_max Max observed tool latency in milliseconds.",
        "# TYPE tool_latency_ms_max gauge",
    ]
    for tool in sorted(latency_sum):
        lines.append(f'tool_latency_ms_sum{{tool="{_escape(tool)}"}} {latency_sum[tool]:.1f}')
        lines.append(f'tool_latency_ms_max{{tool="{_escape(tool)}"}} {latency_max[tool]:.1f}')
    lines += [
        "# HELP upstream_failures_total Upstream failures per provider.",
        "# TYPE upstream_failures_total counter",
    ]
    for name in sorted(upstream):
        lines.append(f'upstream_failures_total{{upstream="{_escape(name)}"}} {upstream[name]}')
    return "\n".join(lines) + "\n"


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "calls": dict(_calls),
            "errors": {f"{t}:{e}": c for (t, e), c in _errors.items()},
            "upstream_failures": dict(_upstream_failures),
        }
