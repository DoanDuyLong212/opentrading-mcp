---
name: render-deploy
description: Use when deploying the OpenTrading MCP-server to Render via Blueprint, checking rollout health, or rotating team bearer tokens.
---

# Render Deploy

## Overview
Blueprint deploy for `opentrading-mcp`: Docker web (Streamable HTTP) + worker (loops) + managed Postgres. Redis via external Key Value URL.

## When to Use
- `render.yaml` changed, new image, `POST /mcp` failing, healthcheck red
- Need to share team LAN build to public URL, rotate `MCP_BEARER_TEAM`
- When NOT to use: local stdio-only dev (`uvx`, `docker compose`)

## Quick Reference
| Task | Command |
|---|---|
| Validate blueprint | `render blueprint validate -f render.yaml` |
| Deploy | `render deploy --blueprint render.yaml` or Dashboard Blueprints → New |
| Tail logs | `render logs -s opentrading-mcp-web --tail 200` |
| Health | `curl https://<svc>.onrender.com/healthz` |
| MCP probe | `curl -X POST https://<svc>.onrender.com/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'` |

## Implementation
1. Set env in Dashboard: `REDIS_URL` (Render Key Value), `MCP_BEARER_TEAM`, `DATABASE_URL` auto from `opentrading-mcp-pg`, plus `VIETSTOCK_*`, `DNSE_*`, `GROQ_*`.
2. Region `singapore`, `healthCheckPath: /healthz`. Web plan `starter` minimum (free sleeps and kills worker loops).
3. Deploy, then verify: `/healthz` 200 → `/mcp` initialize 200 → `tools/list` contains `market_snapshot, source_status` → Cursor green dot / `codex mcp get`.
4. Rotate bearer: Dashboard Env → new value → redeploy → update `configs/*remote*` + `OPENTRADING_MCP_TOKEN`.

## Common Mistakes
- Free web alone without worker → realtime `dash:*` stale; always deploy worker.
- Missing `REDIS_URL` → HTTP works but every call hits upstream (slow, rate-limited).
- Wrong `healthCheckPath /` → deploy never goes live; must be `/healthz`.
- Committing `.env` with `MCP_BEARER_TEAM` → rotate immediately, use `sync: false`.
