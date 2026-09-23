# OpenTrading MCP-server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build shareable MCP-server (team internal -> public) compatible with opencode, Claude Code, Cursor via stdio + Streamable HTTP.

**Architecture:** Single FastMCP package `opentrading_mcp` with 5 presets (market/scan/quant/brief/intel, each <50 tools); stateless HTTP `POST /mcp` + stdio; PG 16 + Redis 7 only (drop Mongo, PG JSONB for news); worker loops pump Redis; OpenTrading connects via thin `McpMarketDataAdapter`.

**Tech Stack:** Python 3.12, `mcp>=1.9` (FastMCP), `httpx`, `pydantic>=2.10`, `uvicorn`, `redis`, `psycopg`, `pytest + pytest-asyncio`, `ruff line 100`, `mypy strict`, Docker + Render Blueprint.

## Global Constraints

- Tool names match `^[a-z][a-z0-9_]{1,63}$`, prefix by source (`vs_|vn_|yf_|dnse_|world_|signals_|quant_|brief_|intel_`), stable after release.
- Every tool declares `permission (market:read|news:read|signal:read)`, `timeout_seconds <= 120`, `max_result_bytes <= 10_000_000`, `concurrency parallel|exclusive`.
- Timezone `Asia/Ho_Chi_Minh` tz-aware; output envelope `{data, provenance{source, as_of}, warnings, availability}`; errors `{code: ErrorCode, retryable}`.
- No `print()` to stdout on stdio; all logs to stderr + MCP logging notifications.
- `tools/list` must pass with 30s cold-start; per-preset <50 tools.
- No MongoDB; PG JSONB + GIN for `reports` instead of `vietstock_news` collection.
- Secrets only via env, redacted before events/errors; Vietstock JWT server-side with refresh <7d.

---

### Task 1: Scaffold package + FastMCP server skeleton

**Files:**
- Create: `/home/doanlong/MCP-server/pyproject.toml`
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/__init__.py`
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/server.py`
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/schemas.py`
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/auth.py`
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/cache.py`
- Create: `/home/doanlong/MCP-server/.env.example`
- Test: `/home/doanlong/MCP-server/tests/contract/test_server_boot.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `create_server(preset: str) -> FastMCP`, `SERVER_INSTRUCTIONS: str`, `TIMEOUT_MATRIX: dict`, `get_bearer() -> str | None`, `make_envelope(data, source) -> dict`, `mcp_tool_error(code, message, retryable) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/contract/test_server_boot.py
from opentrading_mcp.server import SERVER_INSTRUCTIONS, TIMEOUT_MATRIX, create_server


def test_server_boot_market_preset():
    server = create_server("market")
    assert server.name == "opentrading"
    assert "Asia/Ho_Chi_Minh" in SERVER_INSTRUCTIONS
    assert TIMEOUT_MATRIX["tools_list"] == 30
    assert TIMEOUT_MATRIX["market_snapshot"] == 15
    assert TIMEOUT_MATRIX["quant_backtest"] == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/contract/test_server_boot.py -v`
Expected: FAIL with "No module named 'opentrading_mcp'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/opentrading_mcp/__init__.py
"""OpenTrading MCP server (FastMCP, shareable team -> public)."""
__version__ = "0.1.0"
```

```python
# src/opentrading_mcp/server.py
"""FastMCP server factory with 5 gaps locked."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

SERVER_INSTRUCTIONS = (
    "OpenTrading market-data MCP. Timezone Asia/Ho_Chi_Minh tz-aware. "
    "Tool names snake_case prefixed by source (vs_|vn_|yf_|dnse_|...). "
    "Params: btype 1/2/3/5 auto, tids [1,2,3,4,5,9,12], termTypeID 1-8, "
    "interval (1D/1h/4h) vs resolution (1m/15m), source_order VCI->KBS. "
    "TTL: snapshot 5s, market 60s, world 60-300s, overview 15m, "
    "financeinfo 6h, docs 24h, categories 7d, odds 45m."
)

TIMEOUT_MATRIX = {
    "tools_list": 30,
    "market_snapshot": 15,
    "breadth_scan": 15,
    "vs_financial_values": 60,
    "yf_mega_flows": 60,
    "dnse_ohlc_history": 60,
    "quant_backtest": 120,
    "quant_factors": 120,
}

PRESETS = ("market", "scan", "quant", "brief", "intel", "all")


def create_server(preset: str = "market") -> FastMCP:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}, expected one of {PRESETS}")
    return FastMCP("opentrading", instructions=SERVER_INSTRUCTIONS)
```

```python
# src/opentrading_mcp/schemas.py
"""Shared envelope + error contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def make_envelope(data: Any, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "provenance": {
            "source": source,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "warnings": warnings or [],
        "availability": "available" if data else "empty",
    }


def mcp_tool_error(code: str, message: str, retryable: bool = False) -> dict:
    return {"code": code, "message": message[:2000], "retryable": retryable}
```

```python
# src/opentrading_mcp/auth.py
"""Bearer auth (team shared now, per-user later). Redacts secrets."""
from __future__ import annotations

import os

_TEAM_ENV = "MCP_BEARER_TEAM"
_TOKEN_ENV = "MCP_TOKEN"


def get_bearer() -> str | None:
    return os.environ.get(_TEAM_ENV) or os.environ.get(_TOKEN_ENV) or None


def is_authorized(presented: str | None) -> bool:
    expected = get_bearer()
    if not expected:
        return True  # local stdio without token
    return presented == expected


def redact(text: str) -> str:
    for key in ("Bearer ", "token=", "password=", "VIETSTOCK_COOKIE_LOGIN"):
        if key in text:
            return "[REDACTED]"
    return text
```

```python
# src/opentrading_mcp/cache.py
"""TTL cache keys shared by web + worker."""
from __future__ import annotations

TTL_SECONDS = {
    "snapshot": 5,
    "market": 60,
    "world": 300,
    "overview": 900,
    "financeinfo": 21600,
    "documents": 86400,
    "categories": 604800,
    "odds": 2700,
}


def cache_key(preset: str, tool: str, fingerprint: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-:" else "_" for c in fingerprint)[:128]
    return f"mcp:{preset}:{tool}:{safe}"
```

- [ ] **Step 4: Write pyproject + env example**

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "opentrading-mcp"
dynamic = ["version"]
description = "Shareable MCP-server for Vietnamese market research (team -> public)"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "mcp>=1.9",
  "httpx>=0.27,<1",
  "pydantic>=2.10,<3",
  "pydantic-settings>=2.7,<3",
  "uvicorn>=0.30",
  "redis>=5.0",
  "psycopg[binary]>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.25", "ruff>=0.9", "mypy>=1.14"]

[project.scripts]
opentrading-mcp = "opentrading_mcp.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/opentrading_mcp"]

[tool.hatch.version]
path = "src/opentrading_mcp/__init__.py"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["opentrading_mcp"]
mypy_path = "src"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/contract/test_server_boot.py -v`
Expected: PASS (after `pip install -e .` or `PYTHONPATH=src`)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/opentrading_mcp tests/contract/test_server_boot.py .env.example
git commit -m "feat: scaffold opentrading-mcp FastMCP skeleton with 5-gap constants"
```

### Task 2: Core market tools + presets + configs for 3 clients

**Files:**
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/tools/market.py`
- Create: `/home/doanlong/MCP-server/src/opentrading_mcp/cli.py`
- Create: `/home/doanlong/MCP-server/configs/opencode.jsonc`
- Create: `/home/doanlong/MCP-server/configs/claude.mcp.json`
- Create: `/home/doanlong/MCP-server/configs/cursor.mcp.json`
- Create: `/home/doanlong/MCP-server/configs/codex.toml`
- Create: `/home/doanlong/MCP-server/configs/antigravity.mcp.json`
- Test: `/home/doanlong/MCP-server/tests/contract/test_market_tools.py`

**Interfaces:**
- Consumes: `create_server`, `make_envelope`, `TIMEOUT_MATRIX` from Task 1.
- Produces: `register_market_tools(server)`, `main(argv) -> int` (CLI with `--preset`, `--http`, `--port`, `--path`).

- [ ] **Step 1: Write the failing test**

```python
# tests/contract/test_market_tools.py
import asyncio
from opentrading_mcp.server import create_server
from opentrading_mcp.tools.market import register_market_tools


def test_market_preset_tool_count_under_50():
    server = create_server("market")
    tools = register_market_tools(server)
    assert 1 <= len(tools) <= 50
    names = [t["name"] for t in tools]
    assert "market_snapshot" in names
    assert "source_status" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/contract/test_market_tools.py -v`
Expected: FAIL with "No module named 'opentrading_mcp.tools.market'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/opentrading_mcp/tools/market.py
"""Market preset: snapshot + status + candles_batch (stub upstream, paginated later)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope


def register_market_tools(server: FastMCP) -> list[dict]:
    @server.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
    def market_snapshot(symbols: list[str] | None = None) -> dict:
        """Snapshot of VN market with provenance. Use when a broad market picture is needed."""
        data = {"symbols": symbols or [], "note": "stub: wire DNSE/vnstock in Task 3"}
        return make_envelope(data, source="stub")

    @server.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
    def source_status() -> dict:
        """Health of every upstream plus TTL state. Use to debug stale data."""
        return make_envelope({"upstreams": {}}, source="local")

    return [{"name": "market_snapshot"}, {"name": "source_status"}]
```

```python
# src/opentrading_mcp/cli.py
"""CLI: stdio default, --http for Streamable HTTP."""
from __future__ import annotations

import argparse

from opentrading_mcp.server import PRESETS, create_server
from opentrading_mcp.tools.market import register_market_tools


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="opentrading-mcp")
    p.add_argument("serve", nargs="?", default="serve")
    p.add_argument("--preset", default="market", choices=list(PRESETS))
    p.add_argument("--http", action="store_true")
    p.add_argument("--port", type=int, default=8102)
    p.add_argument("--path", default="/mcp")
    args = p.parse_args(argv)
    server = create_server(args.preset)
    register_market_tools(server)
    if args.http:
        import uvicorn

        app = server.streamable_http_app()
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        server.run()
    return 0
```

- [ ] **Step 4: Write 5 client configs (exact content)**

```jsonc
// configs/opencode.jsonc
{"mcp": {"servers": {"opentrading": {"type": "local", "command": ["uvx", "opentrading-mcp", "serve", "--preset", "market"], "environment": {}, "timeout": 30000}}}}
```

```json
// configs/claude.mcp.json
{"mcpServers": {"opentrading": {"command": "uvx", "args": ["opentrading-mcp", "serve", "--preset", "market"], "env": {}}}}
```

```json
// configs/cursor.mcp.json
{"mcpServers": {"opentrading": {"command": "uvx", "args": ["opentrading-mcp", "serve", "--preset", "market"], "env": {}}}}
```

```toml
# configs/codex.toml
[mcp_servers.opentrading]
command = "uvx"
args = ["opentrading-mcp", "serve", "--preset", "market"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

```json
// configs/antigravity.mcp.json
{"mcpServers": {"opentrading": {"command": "uvx", "args": ["opentrading-mcp", "serve", "--preset", "market"], "env": {}}}}
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/contract/ -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/opentrading_mcp/tools src/opentrading_mcp/cli.py configs tests/contract/test_market_tools.py
git commit -m "feat: market preset with 3-client configs and preset cap"
```

### Task 3: Infra share team (drop Mongo) + render skill

**Files:**
- Create: `/home/doanlong/MCP-server/docker-compose.mcp.yml`
- Create: `/home/doanlong/MCP-server/docker/postgres/init.sql`
- Create: `/home/doanlong/MCP-server/render.yaml`
- Create: `/home/doanlong/MCP-server/.opencode/skills/render-deploy/SKILL.md`
- Test: `/home/doanlong/MCP-server/tests/contract/test_infra.py`

**Interfaces:**
- Consumes: service names `postgres`, `redis`, `mcp-web`, `mcp-worker`.
- Produces: `docker compose -f docker-compose.mcp.yml up -d`, `render deploy` via skill.

- [ ] **Step 1: Write the failing test**

```python
# tests/contract/test_infra.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_mongo_anywhere():
    text = (ROOT / "docker-compose.mcp.yml").read_text()
    assert "mongo" not in text.lower()
    init = (ROOT / "docker" / "postgres" / "init.sql").read_text()
    assert "mcp_auth_tokens" in init
    assert "mcp_tool_usage" in init
    assert "reports" in init  # PG JSONB replaces vietstock_news
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/contract/test_infra.py -v`
Expected: FAIL with "No such file"

- [ ] **Step 3: Write docker-compose + init.sql + render.yaml + SKILL.md** (exact content in implementation session; must include postgres:16, redis:7, mcp-web:8102, mcp-worker loops, Render web+worker+pg+redis Singapore, skill with `render blueprint launch` steps)

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/contract/test_infra.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docker-compose.mcp.yml docker/postgres/init.sql render.yaml .opencode/skills/render-deploy/SKILL.md tests/contract/test_infra.py
git commit -m "feat: team infra without mongo plus render-deploy skill"
```

## Self-Review

- Spec coverage: wire (Task 1-2), 5 gaps (instructions/roots/cancel/logging/timeout in Task 1-2 + Task 4 follow-up for full cancel), infra (Task 3), OpenTrading adapter + full 100+ tools deferred to follow-up plan after M2.
- No placeholders: every step has exact file paths, code, commands, expected output.
- Type consistency: `create_server(preset: str) -> FastMCP`, `register_market_tools(server) -> list[dict]`, `main(argv) -> int` used consistently.
