# Kiến trúc MCP-server — báo cáo mới 2026-10-05 (sau nâng cấp)

> Verify bằng code + chạy live ngày 2026-10-05. Thay thế số liệu preset cũ trong
> `architecture-review-2026-09-30.md`. Quy ước: user-visible text tiếng Việt.

## 0. TL;DR số liệu mới

| Hạng mục | Trước | Sau nâng cấp | Verify |
|---|---|---|---|
| Tool surface | 138, chia 6 preset (`market 66/scan 47/...`) | **139 full duy nhất** (140 khi có websearch key; +1 alias `vn_crypto_ohlv`) | `register_all()` + `list_tools()` live |
| CLI | `serve --preset X` bắt buộc | `serve` thuần; `--preset` còn như deprecated alias (warn) | `cli.py`, `Dockerfile`, `configs/*`, `docker-compose` đã gỡ |
| `tools/list` shape | 6 hình dạng theo flag | 1 hình dạng ổn định | chuẩn MCP, hết drift với `OpenTrading/presets.ts` |
| Envelope | `{data, provenance, warnings, availability}` | + optional `page{total,offset,limit,next}` + `error` | `schemas.py`, `test_server_boot` pass |
| Annotations | 1 `READ_WRITE` chung + `alert_check: READ_ONLY` sai | `READ_ONLY/CREATE/DELETE/STATE`, `alert_check: STATE`, deletes destructive | `shared.py`, `scan.py`, `watchlist.py` |
| Log | `obs.log_tool_call` → stdout (vỡ stdio) | → stderr | `obs.py:56`, `test_obs/middleware` pass |
| Timeout contract | `TIMEOUT_MATRIX` 11 entries (stale) | Xóa; per-tool `run_blocking(secs=)` + client `toolTimeoutMs` | `server.py` |
| Correctness | movers hardcode 6 mã, `source_status.vnstock=ok` hardcode, brief hardcode vietstock-unavailable, valuation docstring DCF, ratios không fallback, `ohlv` typo, PG trùng tên | Tất cả đã fix (chi tiết §5) | 284 passed (`pytest tests/contract --ignore=test_verify_matrix`) |
| Lint/type | ruff sạch; mypy 4 lỗi pre-existing | ruff sạch; mypy còn đúng 4 pre-existing (pandas-stubs, markdownify) | `ruff check`, `mypy --strict` |

## 1. End-to-end: từ client connect tới answer

### 1.1 Client kết nối — thông số từng loại

**A. stdio local (dev, opencode/Cursor/Claude/Codex/Antigravity):**
```jsonc
// configs/claude.mcp.json (tương tự cursor/antigravity)
{ "mcpServers": { "opentrading": {
  "command": "uvx", "args": ["opentrading-mcp", "serve"], "env": {} } } }
```
- Process: client spawn `uvx opentrading-mcp serve` → nói JSON-RPC qua stdin/stdout, log qua stderr.
- Quy tắc sống còn: **không in gì ra stdout** ngoài protocol (`obs.py` đã fix; `market.py:_log_stderr` mẫu đúng). 3 dòng stderr cuối hiện trong OpenTrading `/mcp` khi fail.
- Timeouts phía client: opencode `timeout: 30000` trong `configs/opencode.jsonc` (phải nâng ≥120s vì tool upstream chậm — kết luận từ live run trong `docs/skills-design-for-harness.md §0.1`); Codex `startup_timeout_sec: 20, tool_timeout_sec: 60` (`configs/codex.toml`).

**B. Streamable HTTP remote (team/Render):**
```
POST https://opentrading-mcp-web.onrender.com/mcp
Headers bắt buộc: Content-Type: application/json,
  Accept: application/json, text/event-stream,
  Authorization: Bearer <TEAM_TOKEN>
```
- Server: `cli.py --http` → `server.streamable_http_app()` + 3 middleware theo thứ tự
  `RateLimiter → Auth → Observability` (`middleware.py`). Legacy `/sse` fallback giữ cho opencode remote (nó thử StreamableHTTP trước, SSE sau).
- Auth: `MCP_BEARER_TEAM` so bằng `hmac.compare_digest` (team bypass quota) hoặc JWT RS256 (`auth_oauth.py`); thiếu/sai → 401 `authentication_failed`. Quota 1000 calls/ngày/user (`quota.py`), rate-limit 120 req/phút/IP + `Retry-After` (`middleware.py:23-58`).
- Discovery: `GET /.well-known/mcp.json` (public card), `GET /healthz` (warm-up Render free-tier 20–40s), `GET /metrics` (auth như `/mcp`).

**C. Handshake MCP chuẩn:**
`initialize` → server trả `instructions` (`SERVER_INSTRUCTIONS` mới <40 từ) + capabilities →
`tools/list` (139 entries, 1 shape) → `resources/list` (4 URIs) → `prompts/list` (6 workflows).
`notifications/tools/list_changed` được OpenTrading `manager.ts:225` lắng nghe để sync lại (khớp chuẩn Claude `list_changed`).

### 1.2 Một tools/call đi qua 7 tầng

```
LLM (đọc descriptor+inputSchema từ tools/list)
 → client tools/call{name, arguments}
 → [HTTP] RateLimiter/quota/Auth → MCP SDK validate input
 → FastMCP dispatch đúng @server.tool fn trong tools/*.py (THIN)
 → validate params → run_blocking(thread + timeout secs=) → provider.* (breaker→httpx/VN lib/WS-cache/scrape)
 → make_envelope(data, source, warnings, availability, page?, error?)
 → text JSON về client → harness truncate/head+tail (12k OpenTrading) → model tổng hợp + trích provenance
```

Ví dụ thật `brief_build(scope=vn)` (WF1 morning_briefing):
`prompts.py` chỉ dẫn thứ tự → `brief.py:34` fan-out `intel.fireant_posts` → fallback `gdelt_events`
→ `vs.indicator_categories` → `pub.sbv_rates/nso/hnx` (khi `calendars=true`) → envelope
`{sections, sources:[vietstock,gdelt,alternative.me,vs_categories]}` + warnings live
(`vietstock: {auth_status}` khi JWT hết) → agent bullet kèm provenance từng dòng.

### 1.3 Các lớp kiến trúc (map file)

| Tầng | File | Trách nhiệm | Điểm mới 10-05 |
|---|---|---|---|
| Transport | `server.py`, `cli.py` | stdio + StreamableHTTP stateless + `/sse`; `register_all()` | Xóa preset, `TIMEOUT_MATRIX={}`, instructions gọn |
| Middleware | `middleware.py` | RateLimiter → Auth/quota → Observability (1 dòng log/tool, không log args/result) | Không đổi, đã đúng |
| Tools THIN | `tools/*.py` (18 files) | validate → `run_blocking` → provider → envelope | Annotations CREATE/DELETE/STATE, paginate `limit/offset`, movers/status/brief/valuation/ratios/ohlcv fix |
| Providers | `providers/*.py` (15) | I/O thật + breaker + `cache_key(tool,fp)` | Key bỏ `{preset}` |
| Tính toán local | `technicals.py`, `screener.py` | RSI/MACD/BB/patterns, filters, backtest | Không đổi |
| Envelope | `schemas.py` | `{data, provenance{source,as_of,TZ}, warnings, availability}` + `page/error` optional | Thêm `paginate_list()` |
| Cache | `cache.py`, `providers/store.py` | Redis setex → fallback memory | Key mới `mcp:{tool}:{fp}` |
| Worker | `loops.py` | pump yfinance/WS snapshot, heartbeat | Key mới |
| Storage | `dbinit.py`, `snapshots.py`, `tools/watchlist.py` | PG 6 bảng + file JSON fallback | PG guard trùng tên |
| Auth/quota | `auth.py`, `auth_oauth.py`, `quota.py` | bearer/JWT + quota | Không đổi |
| Prompts/resources | `prompts.py` (6 WF), `resources.py` (4 URIs) | workflow order + catalog/reference | Catalog bỏ preset |

### 1.4 Availability — hợp đồng trung thực

`available` (dùng số + provenance) / `partial` (leg chết → warnings) / `empty` (kết quả hợp lệ, không retry)
 / `stale` (snapshot + timestamp) / `unavailable` (đọc warnings lấy fallback, thử 1 lần).
Skill/harness **không được** fill số bịa (quy tắc vàng `skills-design-for-harness §0.2`).

## 2. So sánh với MCP-server của opencode / Claude Code / Cursor

> Lưu ý: ba cái tên này chủ yếu là **harness/client** + hệ sinh thái server mẫu,
> không phải một server đơn để so dòng-dòng. So ở tầng triết lý server.

| Tiêu chí | opencode + servers mẫu (70–80 tools) | Claude Code + servers mẫu (4–79 tools) | Cursor + marketplace servers | OpenTrading MCP-server (bản này, 139 tools) |
|---|---|---|---|---|
| Triết lý surface | Layered: workflow composite (`ask/run/fire/check`) + low-level 1:1 API. Registry `registerTool()`, thêm tool = thêm file | Minimal lifecycle (start/continue/check) + `allowedTools/disallowedTools`, `advanced.tools` preset, `alwaysLoad` | Mỗi server 5–10 tools là chuẩn; megaserver 30+ là anti-pattern; toggle tay từng tool | **Giữ 139 granular** theo yêu cầu user; bù bằng descriptor gọn + paginate + client filter (không facade) |
| Chống tràn context | Cảnh báo "adds to context, be careful"; per-agent glob `mcp_*`, timeout 5s | **Tool search mặc định** (defer schema, `ENABLE_TOOL_SEARCH`, `alwaysLoad`), output >25k tokens → persist file, `_meta/maxResultSize` tới 500k | Legacy limit ~40 tools; bản mới Dynamic Discovery −46.9% token nhưng vẫn toggle tay | Single full `tools/list` + instructions gọn + `limit/offset/page` + `maxOutputChars` phía client |
| Annotations | `readOnly/destructive` → permission dialog | Map `readOnly→concurrencySafe`, `destructive→permission`, `openWorld→scope` | Auto-review vs Allowlist, enterprise allowlist per-tool | Đã chuẩn hóa CREATE/DELETE/STATE; OpenTrading `RwLock` 5 readers dùng đúng hint |
| Transport/auth | stdio + remote (`type:remote/url/headers/oauth:false/timeout`) | stdio/http/ws + cached tool list + nonblocking connect + OAuth | stdio/http/SSE + OAuth + team marketplace distribute | stdio + StreamableHTTP + SSE fallback + bearer/JWT + quota/rate-limit (đầy đủ nhất cho team VN) |
| Observability | truncate `MAX_OUTPUT`, structured errors, timeouts | init `system` message báo `pending/failed/needs-auth`, connection error vào `ToolSearch` | MCP Logs panel, per-tool toggle, red/green dot | JSON 1 dòng/tool + Prometheus `/metrics` + `source_status` probe thật |

### Ưu/nhược điểm

- **opencode servers:** + layered workflow giảm 3–4x số call, registry sạch; − vẫn load full schema lúc startup, dễ tràn khi >50 tools.
- **Claude servers:** + tool search + persist output là chuẩn vàng cho server lớn; − phụ thuộc beta header/proxy, `alwaysLoad` chặn startup 5s.
- **Cursor servers:** + marketplace + per-tool toggle + policy enterprise; − limit lịch sử 40, re-enable sau restart gây friction, validation schema khắt khe (tránh `$ref/oneOf`).
- **Bản này:** + domain VN sâu nhất (Vietstock/VNStock/DNSE/yfinance/Binance/FRED/WorldBank/GDELT...), envelope trung thực 5 states, prompts 6 WF + resources, deploy team sẵn (Docker/Render/PG16/Redis7); − 139 tools vẫn nặng với opencode/Cursor không có search (chấp nhận theo yêu cầu giữ granular; đường dài nên thêm gateway `tags=` kiểu Datadog/Speakeasy hoặc 3–5 workflow tools mà không xóa granular).

### Điểm yếu chung của MCP-server hiện tại (cả 4 bên)

1. Spec chưa có filtering/grouping chuẩn — mỗi bên tự chế (preset custom, tags query, toolsets) → client phải học riêng.
2. JSON Schema validation khác nhau (Cursor khắt nhất) → tool chạy bên này, silent-fail bên kia.
3. Output lớn không có chuẩn phân trang dữ liệu (MCP pagination mới chỉ cho `tools/list`, chưa cho rows) → mỗi server tự `limit/offset`.
4. Annotations sai/tin tưởng mù (`readOnly` giả) → permission/song song sai.
5. stdout/stderr lẫn lộn vẫn phổ biến → corrupt stdio.

### Điểm đột phá của bản này cho bài toán dữ liệu tài chính VN

- **Honest availability + provenance/TZ:** `Asia/Ho_Chi_Minh` tz-aware mọi nơi, 5 states thay vì raise — agent tài chính không bịa số khi upstream chết/off-hours (khác biệt lớn nhất với server CRUD thông thường).
- **Multi-upstream degrade độc lập:** `market_overview` 3 legs (quotes/breadth/session) chết leg nào warning leg đó; `brief_build` Fireant→GDELT; `breadth_scan` live→snapshot `stale`.
- **Batch-first:** `market_candles_batch`, `vn_equity_quote_batch`, `compare_equities` thay bắn lẻ (khớp ngân sách OpenTrading ≤5/wave, vs ≤4, yf ≤3).
- **Pre-flight 2 calls** (`source_status` + `vs_auth_status`) trong mọi skill → JWT/throttle/WS-cold lộ ngay, không tốn 10 calls mới biết.
- **Single surface + catalog resource:** hết drift preset, `opentrading://catalog/tools` là nguồn duy nhất cho harness/skills (22 skills trong `skills-design-for-harness.md` không cần sửa).

## 3. Còn lại (ngoài scope đợt này, đã cố ý không làm)

- Tách `compute.py` 767 dòng, gộp `compare_assets/company_profile`, chuẩn hóa `tickers/assets/pair`, controlled-source-vocabulary: đúng hướng nhưng breaking/đụng constraint giữ granular → để đợt riêng.
- Gateway `?tags=`/`?toolsets=` kiểu Datadog/Speakeasy, `_meta/maxResultSizeChars`, FastMCP `list_page_size`: nên làm khi opencode/Cursor kêu nặng.
- Harness OpenTrading: không can thiệp theo yêu cầu (nó đã đủ `activeTools/budget/doom-loop/RwLock`).

## 4. Đợt fix 10-2026 (P0+P1+P2 + harness mới, branch MCP-server)

### MCP-server: đã sửa
- P0: `breadth_scan` crash board bẩn (helper `_bchg` try), `geo_intel` bỏ `sleep(10)` chặn loop (trả unavailable + warning retry-after-gdelt), `watchlist_remove` → `READ_WRITE_DELETE`.
- P1: 4 constants shared đủ 4 hints + thêm `READ_ONLY_OPEN` (web/yf/yf_world/crypto + 3 tools intel); `source="v"` → `vietstock`; `to_date` truyền xuống provider; `vn_fundamentals` trả structured (duck-typing, không thêm mypy nợ); `@guarded` cho 15 fn `vnstock` + 9 fn `intel`; verify_matrix đủ 139 tools (thêm 37 entries, test assert `==139`); `stock_screener` partial khi enrich thiếu; `quant_backtest` doc deprecate; `brief_build` bỏ chữ odds; `market_movers`/`symbol_lookup`/`source_status`/`valuation`/`ratios`/`ohlcv`/`watchlist PG guard` (đợt trước, giữ nguyên).
- P2: tách `compute.py`→3 file, `quant.py`→2 file + `quant_shared.py` (giữ 100% behavior, 139 tools); mount `/sse` thật (docs hết nói dối); instructions `page{total,offset,limit,next}`; timeout opencode configs 30s→120s; `as_of` tz-aware `Asia/Ho_Chi_Minh`; `ALLOWED_SOURCES` + alias (`v`→vietstock...); ruff sạch, mypy còn đúng 4 lỗi pre-existing.
- Cố ý KHÔNG làm: gộp cặp trùng (vỡ clients), xóa preset-compat shims (giữ tương thích), đổi hardcoded Trading_Agents session path (team flow).

### Chia tools MCP-server vs harness (theo opencode: local = tương tác/tính toán/session, remote = data/services)
- Harness-local mới: `spawn_subagent` (child runAgent, allowlist readOnly mặc định, cấm đệ quy, maxSteps ≤15), `web_fetch` (2MB cap, timeout 120s), `web_search` (Exa→Parallel→DuckDuckGo fallback).
- Giữ remote: toàn bộ 139 data tools + `runs_list/run_get/doctor` server (phục vụ clients khác; harness đã có `session_list/session_get/doctor_local` tương đương và được ưu tiên).
- Trùng lắp có chủ ý: `web_search/web_fetch` tồn tại cả 2 nơi — harness dùng bản local (không cần key), remote giữ cho CI/clients khác.
