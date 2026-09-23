# OpenTrading MCP-server

Shareable MCP-server for Vietnamese market research. Team internal first, public later.

- Transports: `stdio` (default, all 5 clients) + Streamable HTTP stateless `POST /mcp` + legacy `/sse` fallback.
- Presets (each <50 tools): `market`, `scan`, `quant`, `brief`, `intel`, `all`.
- Backend: Postgres 16 + Redis 7 only. No MongoDB (`reports` PG JSONB replaces `vietstock_news`).
- Timezone `Asia/Ho_Chi_Minh` tz-aware everywhere.

## Quickstart (local, no deploy)

```bash
pip install -e ".[dev]"
PYTHONPATH=src python -m pytest tests/ -v
opentrading-mcp serve --preset market        # stdio for opencode/claude/cursor
opentrading-mcp serve --preset market --http --port 8102  # LAN share
```

## Team LAN / Render

```bash
docker compose -f docker-compose.mcp.yml up -d
OPENTRADING_MCP_TRANSPORT=http OPENTRADING_MCP_URL=http://localhost:8102/mcp ...
```

See `configs/` for opencode / Claude / Cursor / Codex / Antigravity snippets,
`render.yaml` for public deploy, `.opencode/skills/render-deploy/SKILL.md` for deploy steps.
