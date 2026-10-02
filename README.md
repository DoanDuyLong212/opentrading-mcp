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

## Kết nối tới MCP-server (dành cho team harness) — 3 bước là chạy

### Bước 0 — Admin cấp token (làm 1 lần duy nhất)

Team bearer là mật khẩu chung để gọi remote. Server không tự phát hành — admin tạo
rồi gán vào env (code đọc `MCP_BEARER_TEAM`, so bằng `hmac.compare_digest`):

```bash
# 1. Tạo secret (đã tạo sẵn 1 cái, xem cuối mục này)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Gán lên Render: Dashboard → service srv-dapvgk942hec73eb3khg
#    → Environment → thêm MCP_BEARER_TEAM=<secret> → Save (tự redeploy ~3 phút)
```

Token hiện tại do admin cấp (hỏi admin qua kênh nội bộ, **không commit vào git**).
Xoay token mỗi tháng: đổi env là xong, không đụng code.

### Bước 1 — Harness/opencode trỏ tới server (copy-paste)

Đúng 100% schema opencode remote (`type: "remote"`, xem
`packages/opencode/src/config/v2-compat.ts:45-53`). File mẫu: `configs/opencode-remote.jsonc`:

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

4 điểm bắt buộc (sai 1 là không kết nối được):
- `"type": "remote"` — không phải `"streamable-http"`, sai key fail validation.
- `"oauth": false` — server là resource-server thuần, không có OAuth endpoints;
  bỏ trống thì opencode tự thử OAuth discovery và fail.
- `headers.Authorization` — thay `<TEAM_TOKEN>` bằng token Bước 0.
- `url` đúng `/mcp`. Opencode tự thử StreamableHTTP trước, SSE fallback sau —
  server hỗ trợ cả hai (`POST /mcp` + legacy `/sse`).

Xong bước này thì restart opencode/harness → server `opentrading` hiện 135 tools là thành công.
Clients khác (Claude/Cursor/generic) dùng cùng URL + 3 headers dưới đây.

### Bước 2 — Verify kết nối (3 lệnh, kỳ vọng rõ ràng)

```bash
BASE=https://opentrading-mcp-web.onrender.com
HDR=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer $TEAM_TOKEN")

# 1. Liệt kê tools → kỳ vọng: 135 tools (đếm "name": 135 lần).
#    Lưu ý: response là SSE (dòng "data: {json}"), opencode parse tự động;
#    curl thì grep trên text thô như dưới. Nếu chỉ đếm được 66 → prod đang
#    chạy preset market cũ (thiếu scan/quant/brief/intel) → redeploy bản mới nhất.
curl -s -X POST "$BASE/mcp" "${HDR[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | grep -o '"name":' | wc -l

# 2. Gọi 1 tool → kỳ vọng: "availability":"available", VCB ~57,400
curl -s -X POST "$BASE/mcp" "${HDR[@]}" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"stock_overview","arguments":{"symbol":"VCB"}}}' | head -c 300

# 3. Đọc 1 prompt (workflow phân tích mã) → kỳ vọng: 7 bước analyze VCB
curl -s -X POST "$BASE/mcp" "${HDR[@]}" \
  -d '{"jsonrpc":"2.0","id":3,"method":"prompts/get","params":{"name":"ticker_analysis","arguments":{"symbol":"VCB"}}}' | head -c 300
```

Headers bắt buộc mỗi request: `Content-Type: application/json`,
`Accept: application/json, text/event-stream`, `Authorization: Bearer <TEAM_TOKEN>`.

### Thông tin server

| Thông tin | Giá trị |
|---|---|
| MCP endpoint | `https://opentrading-mcp-web.onrender.com/mcp` |
| Transport | Streamable HTTP (stateless), JSON-RPC 2.0 |
| Server card (public) | `https://opentrading-mcp-web.onrender.com/.well-known/mcp.json` |
| Health (public) | `https://opentrading-mcp-web.onrender.com/healthz` |
| Tools | 135 (`all`), presets `market` 65 / `scan` 47 / `quant` 9 / `brief` 7 / `intel` 8 |
| Preset remote | `all` — Render chạy `serve --preset all` (xem `Dockerfile` CMD). Nếu `tools/list` chỉ trả 66 tools = đang chạy preset `market` cũ, cần redeploy bản mới |
| Prompts | 6 workflows: `morning_briefing`, `ticker_analysis`, `pre_earnings`, `sector_rotation`, `ai_detect`, `risk_check` |
| Quy tắc dùng | Rate-limit 120 req/phút/IP; quota 1000 calls/ngày/user (team token bypass quota) |
| Timezone | `Asia/Ho_Chi_Minh` tz-aware — parse theo giờ VN |

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
