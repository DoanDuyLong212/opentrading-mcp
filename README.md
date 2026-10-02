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

## Kết nối tới MCP-server (dành cho team harness)

### Cách 1 — Remote HTTP (khuyến nghị, không cần cài gì)

| Thông tin | Giá trị |
|---|---|
| MCP endpoint | `https://opentrading-mcp-web.onrender.com/mcp` |
| Transport | Streamable HTTP (stateless), JSON-RPC 2.0 |
| Auth | `Authorization: Bearer <TEAM_TOKEN>` (xin token từ admin) |
| Server card | `https://opentrading-mcp-web.onrender.com/.well-known/mcp.json` (public) |
| Health | `https://opentrading-mcp-web.onrender.com/healthz` (public) |
| Tools | 135 (`all`), presets `market` 65 / `scan` 47 / `quant` 9 / `brief` 7 / `intel` 8 |
| Prompts | 6 workflows: `morning_briefing`, `ticker_analysis`, `pre_earnings`, `sector_rotation`, `ai_detect`, `risk_check` |
| Quy tắc dùng | Rate-limit 120 req/phút/IP; quota 1000 calls/ngày/user (team token bypass quota) |

Headers bắt buộc mỗi request:

```
Content-Type: application/json
Accept: application/json, text/event-stream
Authorization: Bearer <TEAM_TOKEN>
```

Ví dụ gọi thử bằng curl (3 bước):

```bash
BASE=https://opentrading-mcp-web.onrender.com
HDR=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer $TEAM_TOKEN")

# 1. Liệt kê tools (kỳ vọng: 135 tools)
curl -s -X POST "$BASE/mcp" "${HDR[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 300

# 2. Gọi 1 tool (giá VCB)
curl -s -X POST "$BASE/mcp" "${HDR[@]}" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"stock_overview","arguments":{"symbol":"VCB"}}}'

# 3. Đọc 1 prompt (quy trình phân tích mã)
curl -s -X POST "$BASE/mcp" "${HDR[@]}" \
  -d '{"jsonrpc":"2.0","id":3,"method":"prompts/get","params":{"name":"ticker_analysis","arguments":{"symbol":"VCB"}}}'
```

Config cho opencode / harness giống-opencode 100% (remote):

```json
{
  "mcp": {
    "servers": {
      "opentrading": {
        "type": "remote",
        "url": "https://opentrading-mcp-web.onrender.com/mcp",
        "headers": { "Authorization": "Bearer <TEAM_TOKEN>" },
        "oauth": false,
        "timeout": 30000
      }
    }
  }
}
```

Bắt buộc đúng 4 điểm theo schema opencode (`type: "remote"`, `url`, `headers`, xem
`packages/opencode/src/config/v2-compat.ts:45-53`):
- `"type": "remote"` (không phải `"streamable-http"` — sai key sẽ fail validation).
- `"oauth": false` — server này là resource-server thuần (team bearer tĩnh, không có
  OAuth metadata endpoints); bỏ trống `oauth` thì opencode tự thử OAuth discovery và fail.
- `headers.Authorization` — Bearer team token, pass-through tới `POST /mcp`.
- `url` trỏ đúng `/mcp`. Opencode tự thử StreamableHTTP trước, SSE fallback sau —
  server hỗ trợ cả hai (`POST /mcp` + legacy `/sse`).

File mẫu copy-paste: `configs/opencode-remote.jsonc`. Clients khác (Claude/Cursor/generic)
dùng block generic `streamable-http` + cùng 3 headers ở trên.

### Cách 2 — stdio local (dev, không cần token)

```bash
uvx opentrading-mcp serve --preset market   # 65 tools thị trường
uvx opentrading-mcp serve --preset all      # 135 tools full
```

File config mẫu local trong `configs/`: `opencode.jsonc`, `claude.mcp.json`,
`cursor.mcp.json`, `antigravity.mcp.json`, `codex.toml`.

### Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `authentication_failed` / 401 | Thiếu/sai Bearer token | Thêm header `Authorization: Bearer <TEAM_TOKEN>` |
| 429 + `Retry-After` | Vượt rate-limit hoặc hết quota ngày | Chờ theo header, giảm tần suất |
| `availability: "unavailable"` + warnings | Upstream chết/thiếu worker (vd WS trio cần worker local) | Đọc `warnings`, dùng tool fallback được gợi ý |
| `availability: "empty"` | Query hợp lệ nhưng không có rows (vd IPO rỗng) | Đúng bản chất, không phải lỗi |
| Cold start 20–40s | Render free-tier sleep | Gọi `/healthz` trước để warm-up |
| Timezone | Mọi timestamp `Asia/Ho_Chi_Minh` tz-aware | Parse theo VN, không UTC |
| Chi tiết đầy đủ | Kiến trúc, bảo mật, DB, clients | `docs/architecture-review-2026-09-30.md` |
| Bảng 135 tools + 6 workflows | Params, mô tả TV, sample live, verdicts | `docs/tools-review-2026-09-24.md` |
