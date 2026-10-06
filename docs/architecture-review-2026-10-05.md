# Kiến trúc MCP-server — báo cáo mới 2026-10-05 (sau nâng cấp)

> Verify bằng code + chạy live ngày 2026-10-05. Thay thế số liệu preset cũ trong
> `architecture-review-2026-09-30.md`. Quy ước: user-visible text tiếng Việt.

## 0. TL;DR số liệu mới

| Hạng mục | Trước | Sau nâng cấp | Verify |
|---|---|---|---|
| Tool surface | 138, chia 6 preset (`market 66/scan 47/...`) | **139 matrix (138 unique + alias `vn_crypto_ohlv`)**; +1 gated `web_search` → 140 entries live | `register_all()` + `list_tools()` live (140) |
| CLI | `serve --preset X` bắt buộc | `serve` thuần; `--preset` còn như deprecated alias (warn) | `cli.py`, `Dockerfile`, `configs/*`, `docker-compose` đã gỡ |
| `tools/list` shape | 6 hình dạng theo flag | 1 hình dạng ổn định | chuẩn MCP, single surface cả 2 phía (`OpenTrading/presets.ts` + gating đã xóa 06-10) |
| Envelope | `{data, provenance, warnings, availability}` | + optional `page{total,offset,limit,next}` + `error` | `schemas.py`, `test_server_boot` pass |
| Annotations | 1 `READ_WRITE` chung + `alert_check: READ_ONLY` sai | `READ_ONLY/CREATE/DELETE/STATE`, `alert_check: STATE`, deletes destructive | `shared.py`, `scan.py`, `watchlist.py` |
| Log | `obs.log_tool_call` → stdout (vỡ stdio) | → stderr | `obs.py:56`, `test_obs/middleware` pass |
| Timeout contract | `TIMEOUT_MATRIX` 11 entries (stale) | Xóa; per-tool `run_blocking(secs=)` + client `toolTimeoutMs` | `server.py` |
| Correctness | movers hardcode 6 mã, `source_status.vnstock=ok` hardcode, brief hardcode vietstock-unavailable, valuation docstring DCF, ratios không fallback, `ohlv` typo, PG trùng tên | Tất cả đã fix (chi tiết §5) | 285 passed (`pytest tests/contract --ignore=test_verify_matrix`; test_verify_matrix fail chỉ do sandbox chặn `api.vnstock.vn` — Render pass) |
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
- Timeouts phía client: opencode `timeout: 120000` trong `configs/opencode.jsonc` (đã nâng từ 30s vì tool upstream chậm — kết luận từ live run trong `docs/skills-design-for-harness.md §0.1`); Codex `startup_timeout_sec: 20, tool_timeout_sec: 60` (`configs/codex.toml`).

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
`tools/list` (140 entries live: 139 matrix + `web_search` gated, 1 shape) → `resources/list` (4 URIs) → `prompts/list` (6 workflows).
`notifications/tools/list_changed` được OpenTrading `manager.ts:210` lắng nghe để sync lại (khớp chuẩn Claude `list_changed`).

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
| Tools THIN | `tools/*.py` (21 modules + `shared.py` + `quant_shared.py`) | validate → `run_blocking` → provider → envelope | Tách `compute→3`, `quant→2`; annotations CREATE/DELETE/STATE; descriptors 10-06 (coerce + ví dụ + phủ định) |
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
- **Single surface + catalog resource:** hết drift preset, `opentrading://catalog/tools` là nguồn duy nhất cho harness/skills.
- [10-06] Model từng tin presets còn gating tools (eval 8/43 runs gọi `switch_preset`) — **đã xóa tận gốc 06-10 đợt 1**: xóa `switch_preset`, `presets.ts`, narrow-by-preset (`registry.activePreset`/`prepareStep`), preset UI/dialogs/tests/configs. Model luôn thấy toàn bộ tools.

## 3. Còn lại (ngoài scope đợt này, đã cố ý không làm)

- Tách `compute.py` 767 dòng, gộp `compare_assets/company_profile`, chuẩn hóa `tickers/assets/pair`, controlled-source-vocabulary: đúng hướng nhưng breaking/đụng constraint giữ granular → để đợt riêng.
- Gateway `?tags=`/`?toolsets=` kiểu Datadog/Speakeasy, `_meta/maxResultSizeChars`, FastMCP `list_page_size`: nên làm khi opencode/Cursor kêu nặng.
- Harness OpenTrading: eval 06-10 từng thấy `switch_preset` gây nhiễu — **đã xóa 06-10 đợt 1** (tool + `presets.ts` + gating + UI + tests). Xem §5–§8 (skills/tools harness + eval live).

## 4. Đợt fix 10-2026 (P0+P1+P2 + harness mới, branch MCP-server)

### MCP-server: đã sửa
- P0: `breadth_scan` crash board bẩn (helper `_bchg` try), `geo_intel` bỏ `sleep(10)` chặn loop (trả unavailable + warning retry-after-gdelt), `watchlist_remove` → `READ_WRITE_DELETE`.
- P1: 4 constants shared đủ 4 hints + thêm `READ_ONLY_OPEN` (web/yf/yf_world/crypto + 3 tools intel); `source="v"` → `vietstock`; `to_date` truyền xuống provider; `vn_fundamentals` trả structured (duck-typing, không thêm mypy nợ); `@guarded` cho 15 fn `vnstock` + 9 fn `intel`; verify_matrix đủ 139 tools (thêm 37 entries, test assert `==139`); `stock_screener` partial khi enrich thiếu; `quant_backtest` doc deprecate; `brief_build` bỏ chữ odds; `market_movers`/`symbol_lookup`/`source_status`/`valuation`/`ratios`/`ohlcv`/`watchlist PG guard` (đợt trước, giữ nguyên).
- P2: tách `compute.py`→3 file, `quant.py`→2 file + `quant_shared.py` (giữ 100% behavior, 139 tools); mount `/sse` thật (docs hết nói dối); instructions `page{total,offset,limit,next}`; timeout opencode configs 30s→120s; `as_of` tz-aware `Asia/Ho_Chi_Minh`; `ALLOWED_SOURCES` + alias (`v`→vietstock...); ruff sạch, mypy còn đúng 4 lỗi pre-existing.
- Cố ý KHÔNG làm: gộp cặp trùng (vỡ clients), xóa preset-compat shims (giữ tương thích), đổi hardcoded Trading_Agents session path (team flow).

### Đợt 06-10 (P19/P20/P21, branch MCP-server)
- P19/P20: tách `compute.py`→`compute_financial/intel/infra.py`, `quant.py`→`quant_backtest/stats.py` + `quant_shared.py`; `@guarded` 15 fn vnstock + 9 fn intel; `ALLOWED_SOURCES` vocab; mount `/sse` thật; crypto caps 10/5; eval live 43 câu (§8).
- P21: xóa preset-gating harness (switch_preset/presets.ts/filters/UI/tests); descriptors coerce + ví dụ + phủ định; 7 skills source-guard; headless `/cmd` parity; verify round2 (§8.3).

### Chia tools MCP-server vs harness (theo opencode: local = tương tác/tính toán/session, remote = data/services)
- Harness-local mới: `spawn_subagent` (child runAgent, allowlist readOnly mặc định, cấm đệ quy, maxSteps ≤15), `web_fetch` (2MB cap, timeout 120s), `web_search` (Exa→Parallel→DuckDuckGo fallback).
- Giữ remote: toàn bộ 139 data tools + `runs_list/run_get/doctor` server (phục vụ clients khác; harness đã có `session_list/session_get/doctor_local` tương đương và được ưu tiên).
- Trùng lắp có chủ ý: `web_search/web_fetch` tồn tại cả 2 nơi — harness dùng bản local (không cần key), remote giữ cho CI/clients khác.

## 5. Harness skills — 26 skills (OpenTrading, nhánh MCP-server @da10329)

> Nguồn sự thật: `OpenTrading/skills/<slug>/SKILL.md`; bản gộp duyệt: MCP-server `SKILLS.md`.
> Cấu trúc chuẩn skill-creator: description pushy + When to Use / Workflow checklist / Template / Examples.
> Cơ chế runtime: system prompt chỉ list tên (`renderCatalog`), body fetch qua `load_skill` khi trigger khớp;
> `requires_tools` gate theo tool hiện có; `tool_budget` mirror trong body.

| # | Skill | requires_tools | Budget | Ver | Routing eval 06-10 (r1 → r2 sau fix) |
|---|---|---|---|---|---|
| 1 | bat-on-quoc-gia | geo_intel | 6 | 1.1.1 | r1: load đúng nhưng chỉ gọi web → FAIL; guard 1.1.1 (chưa rerun) |
| 2 | co-ban-chuyen-sau | financial_detail | 9 | 1.1.0 | ✓ + fallback mirror trung thực khi Vietstock-detail chặn |
| 3 | danh-gia-tinh-hinh-chinh-tri-toan-cau | — | 8 | 1.1.0 | ✓ |
| 4 | danh-gia-tinh-hinh-xung-dot | event_stats | 9 | 1.1.0 | ✓ (+kéo phan-tich-vang-ty-gia hợp lý) |
| 5 | danh-gia-truoc-bctc | company_events | 10 | 1.1.0 | ✓ (+co-ban sub); trừ load trùng 2 lần |
| 6 | danh-gia-vi-mo-quoc-te | fred_series | 10 | 1.1.1 | r1: không gọi fred_series (đi web) → FAIL; guard 1.1.1 (chưa rerun) |
| 7 | danh-gia-vi-mo-viet-nam | vs_indicator_data | 12 | 1.2.0 | r1: validation ×3; r2: 0 validation-fail (coerce server) → ✓ |
| 8 | devil-advocate | — | — | 1.2.0 | ✓; spawn_subagent ×3 timeout (vấn đề #4) |
| 9 | dinh-gia-chuyen-sau | valuation_run | 7 | 1.1.0 | r1: 4 tools bịa → PARTIAL; r2: 0 hallucination → ✓ |
| 10 | du-doan-fed | world_prediction_odds | 8 | 1.1.0 | ✓ |
| 11 | du-doan-polymarket | world_prediction_odds | 6 | 1.1.0 | ✓ (odds ×4 + polymarket_event đúng bài) |
| 12 | explain-term | — | — | 1.2.0 | ✓ hoàn hảo (0 tool, 92s; r2 same) |
| 13 | kiem-chien-luoc-backtest | quant_backtest | 12 | 1.2.2 | r1: spawn fail + sai nguồn; r2: backtest_strategies ×6 đúng → ✓ |
| 14 | kiem-tra-nguon-du-lieu | doctor (manual) | 12 | 1.1.0 | manual nên không load là đúng; model tự doctor_local + source-check → PASS direct-use |
| 15 | ky-thuat-chuyen-sau | signals_technical | 8 | 1.2.0 | ✓ tốt nhất (3 tools, có verdict phân tích thật) |
| 16 | nhip-dap-crypto | crypto_spot | 6 | 1.2.1 | r1: crypto VND ×6 → FAIL; r2: crypto_spot/derivs trước → ✓ |
| 17 | phan-tich-chuyen-sau-1-ma | stock_overview | 8 | 1.2.2 | ✓ + 2 sub-skills; nhưng 12 tools (>budget 8), miss chart Step 2b |
| 18 | phan-tich-sentiment | sentiment_score | 6 | 1.1.0 | ✓ |
| 19 | phan-tich-vang-ty-gia | vn_retail_gold | 10 | 1.2.0 | ✓; r1 preset-confusion (đã xóa preset — hết nguyên nhân) |
| 20 | so-sanh-cung-nganh | compare_equities | 8 | 1.2.0 | ✓ (+co-ban); 12 tools lặp dư (mỗi loại ×3) |
| 21 | tim-co-hoi-bao-cao-ctck | analyst_consensus | 8 | 1.2.0 | ✓; r1 preset-confusion (đã xóa preset) |
| 22 | tim-kiem-tin-tuc | news_symbol | 10 | 1.2.1 | r1: không gọi news_symbol → FAIL; guard 1.2.1 (chưa rerun) |
| 23 | tin-tuc-nong-quoc-te | news_market | 8 | 1.1.0 | ✓ tool mix hợp lý |
| 24 | tin-tuc-nong-viet-nam | news_market | 9 | 1.1.0 | ✓ + note heuristic trung thực |
| 25 | ve-bieu-do-ky-thuat | chart_render (local) | 8 | 1.2.1 | ✓; r1 detour sai nguồn; r2: đúng nguồn ngay → ✓ |
| 26 | vn-market-basics | — | — | 1.2.0 | ✓ hoàn hảo (0 tool, 87s) |

Routing tổng r1: 24/26 load đúng ngay (S19 miss sang skill tin-tức, S14 manual-by-design).
Round2 sau fix: 11/12 đạt (S07/S09/S13/S16/S24/W1 + F08/F09/F11/S12/W4); W5 cải thiện (0 preset/hallucination) nhưng vẫn miss `quant_risk`.
Vấn đề còn mở: **timeout 300s** (câu phức tạp không ra verdict — đợt 2), `spawn_subagent` (60s + allowlist), `quant_risk` leg trong W5.

| 6. Harness tools — sau merge upstream 06-10: **21 local** (16 của mình + 5 upstream: `ask_user`, `todo_write`, `tool_search`, `list/read_mcp_resource`); turn-guards (doom-loop/budget 20) bị upstream thay bằng `PermissionGate` (ask trước tool side-effect). Chi tiết bảng trước merge:

| Tool | Vai | Ranh giới với remote | Eval fallback 06-10 |
|---|---|---|---|
| current_time | đồng hồ VN | không remote tương đương | ✓ F01 hoàn hảo |
| load_skill | nạp body skill | — | ✓ 24/26 đúng; trừ load trùng (S05) + đoán file (baokao) |
| ~~switch_preset~~ (đã xóa 06-10) | — | server single surface → xóa gating tận gốc | — |
| chart_render/compare/depth | vẽ TUI (@crafter/charts) | không remote tương đương | ✓ S24/F07/F08 (đúng kind + màu) |
| session_list/get | phiên của user | thay runs_list/get server-share (team) | ✓ F04 (không nhầm runs_list) |
| doctor_local | sức khỏe harness | phân biệt doctor server | ✓ F05 (local trước, server sau) |
| watchlist_local_* (5) | watchlist cá nhân | thay watchlist_* remote (share team) | ✓ F06 (không dùng remote) |
| web_fetch | đọc URL (browser→readability) | khác remote (server-side, PDF) | ✓ F02/F03 |
| web_search | tìm web (Exa→Parallel→DuckDuckGo) | remote chỉ có web_search gated-key | ✓ F02; nhưng bị lạm dụng thay tools chuyên (S06/S21/S26) |
| spawn_subagent | worker opencode con | không remote tương đương | ✕ timeout 60s ×7 (F10/S08/S10/W6); allowlist từ chối tên tool MCP (W6) |

Tổng registry live sau merge upstream: **160 tools** (139 MCP deferred sau `tool_search` +
21 local), verify qua `mcp.start()` headless [trước merge: 156; trước khi xóa switch_preset: 157].

## 7. Ma trận phủ tools ↔ skills (trả lời: tools có được phủ hết trong skills không?)

> Phương pháp: static (requires_tools + tên tool trong body skill) ∪ observed (89 tools được gọi trong 55 runs live: 43 round1 + 12 round2)
> ∪ prompts (29 tools trong 6 prompt texts). Chi tiết: `docs/eval-2026-10-06/` (questions/report/runs/round2+round3).
> Sau merge upstream 06-10: tool-search deferral — 139 MCP tools vẫn callable, model thấy
> tên trong catalog + nạp qua `tool_search`; ma trận phủ skills bên dưới không đổi.

- **KHÔNG — 118/153 phủ (77%), 35 tools mồ côi (23%)** [06-10: trước fix là 114/154 (74%), 40 mồ côi; sau round2 + xóa switch_preset: signals_scan/market_snapshot/ipo_calendar_vn/... đã được gọi], không skill nào nhắc tên, live không gọi, prompts không dùng:
  - `alert_*` (6) + `watchlist_*` remote (7): mồ côi từ rev.3 (xóa `theo-doi-va-bao-thuc`) — GAP cần skill mới hoặc xóa tools.
  - `runs_list/run_get` (2): bị `session_*` thay thế ở harness nhưng tools còn cho clients khác — giữ có chủ ý, ghi rõ.
  - `session_get`, `watchlist_local_delete/remove`: direct-use by design (không cần skill), F04/F06 chứng minh model tự dùng đúng.
  - Data tools mồ côi thật: `quant_factors`, `vn_listing`, `vn_forex_ohlcv`, `vn_global_index`, `vs_currency/market_info/market_price/selftrading`, `yf_oracle_markets`, `yf_world_indices`, `dnse_*` (4: market_status/indices/working_dates/ws_snapshot), `exchange_calendar`, `oracle_meta`, `signals_screener_columns`, alias `vn_crypto_ohlv` (phủ qua ohlcv).
- Khuyến nghị: (a) skill theo-dõi/cảnh-báo mới HOẶC xóa `alert_*` + `watchlist_*` remote; (b) điểm tên các data tools mồ côi vào skills liên quan (vd `signals_scan`→ky-thuat, `quant_factors`→backtest, `dnse_market_status`→ky-thuat/vang); (c) giữ direct-use cho session/watchlist-local/web (đã chứng minh ăn khớp).

## 8. Kết quả eval live 06-10-2026 (43 câu: 26 skills + 6 WF + 11 fallback)

### 8.1 Verdict tổng: r1 PASS 24 / PARTIAL 11 / FAIL 8; r2 (sau fix): 11/12 đạt, W5 cải thiện

### 8.2 Vấn đề hệ thống (xếp theo độ nặng)

1. **Timeout 35/43 runs (300s abort trước verdict).** Mỗi tool call qua Render + upstream VN ~10–30s, model reasoning chậm (deepseek-v4.1-flash), maxSteps 10 → câu phức tạp không bao giờ xong verdict. Đây là nút thắt lớn nhất: eval đo được routing/tool-fit nhưng hiếm khi đo được chất lượng verdict cuối.
2. **Preset-confusion 8/43 — ĐÃ FIX 06-10 đợt 1.** Nguyên nhân harness: tool + `presets.ts` + narrow-by-preset dù server single surface. Fix: xóa toàn bộ (tool, `presets.ts`, `activePreset`/`prepareStep` filter, preset UI/dialogs/tests/config keys, docs `mcp.md`/`samples.md`). Verify: rerun F08/F09/W1/W5 (mục Verify đợt 1).
3. **Model bịa tên tools (7 cái) — ĐÃ SIẾT DESCRIPTOR 06-10 đợt 1:** thêm dòng phủ định vào `valuation_run`/`analyst_consensus`/`vn_quote_history`/`quant_risk`/`vs_trading_info`. Verify: rerun S09/W5 (0 'unavailable tool').
4. **spawn_subagent timeout 60s ×7** (F10/S08/S10/W6) + allowlist từ chối tên MCP (W6: "tool names không accept" — cần prefix `mcp__` trong allowlist). Đường subagent hiện không dùng được với model này.
5. **Validation friction — ĐÃ FIX 06-10 đợt 1:** `vs_indicator_data` nhận int|str + coerce (kèm test), descriptors thêm JSON example (`quant_risk`, `dnse_latest_trade`). Verify: unit test + rerun S07/F11/W5.
6. **Chọn sai nguồn — ĐÃ THÊM GUARD 06-10 đợt 1:** 7 skills (phan-tich 1.2.2, backtest 1.2.2, ve-bieu-do/nhip-dap/tim-kiem-tin-tuc 1.2.1, vi-mo-quoc-te/bat-on 1.1.1) có matrix nguồn + CẤM web trước tool chuyên. Verify: rerun S13/S16/S24/W5.
7. **Prompt workflows — ĐÃ PARITY HEADLESS 06-10 đợt 1:** `chat.ts` tự resolve `/cmd` → `prompts/get` như TUI (W1–W4 PASS tool-fit khi resolved; W5/W6 FAIL do preset/hallucination — xem #2/#3).
8. **Trung thực là điểm sáng** (giữ nguyên) + **đã thêm rule style 06-10**: không tuyên bố nhớ phiên trước trừ khi session/memory trả về (fix ca confabulation W6).

### 8.3 Verify đợt 1 — round2 (12 câu, chiều 06-10)

Chi tiết: `docs/eval-2026-10-06/round2.md` (transcripts `runs/round2/`).
Kết quả: `switch_preset` 8/43→**0/12**, hallucination 7→**0**, validation-fail→**0**;
F09 (FAIL trắng) nay ra đáp án đầy đủ; S07/S09/S13/S16/W1/W4 đạt; W5 cải thiện nhưng
vẫn miss `quant_risk`. Timeouts 300s còn (sang đợt 2, vấn đề #1). Registry còn **156 tools**.

### 8.4 Round 3 — verify feedback review (06-10 tối)

Chi tiết: `docs/eval-2026-10-06/round3.md` (transcripts `runs/round3/`).
**P22 đã verify live local (Render lúc chạy vẫn bản cũ):** `geo_intel` lọc chính trị +
aggregate + military mode (adsb.lol live: 138 máy bay, by_country US 43/Japan 19/UK 16,
nearest-zone gaza 82km, signal-loss diff); `event_stats` aggregate tách vai;
`valuation_run` btype→method + warning btype lạ. Round3: T-questions ky-thuat 6/6 đạt
(verdict thật 1344–4007 ch); S03/S04/S09 0 fails; S05 bỏ Step 1 BCTC ✓ + fix thêm
skill 1.1.2 (load_skill chỉ với tên, không aspect-file); S18 còn spawn timeout (đợt 2 #4).

### 8.5 Merge upstream harness (06-10, PR pending)

Merge `origin/main` (tool-search #19, mcp-instructions #20, prompt-tuning #21, todo #22-24,
compact #23) vào nhánh `MCP-server` OpenTrading (`baf7a2c` + follow-ups `da10329`).
- **Theirs** (pipeline rework): `agent.ts` (`requestFor/activeFor/nudge`), `mcp/config.ts`
  (`enabledTools/disabledTools/alwaysLoad` thay preset), `mcp/manager.ts`, `session/store.ts`
  (one-clock), `tools/registry.ts` (cap 128 + image handling + `deferrable`), `tools/wrap.ts`,
  `tui/state.ts`/`app.tsx` (flash/exitArmed/question/liveTodos/compact), `/tools` rich detail,
  `/mcp` dialog được upstream thay mới (xóa file cũ), `docs/mcp.md`, `prompts/tools.md`.
- **Ours giữ lại**: `runtime.ts` combine — upstream tools (`ask_user/todo_write/tool_search` +
  `loadSkillTool` signature mới) + local tools (chart/session/watchlist/web/subagent/doctor_local).
- **Turn-guards bị upstream thay thế**: doom-loop + budget 20/lượt + `approvals.ts` →
  `PermissionGate` mới (queued, once/session/always/deny, không silent-allow headless).
  Skill `tool_budget` vẫn là hướng dẫn model đọc trong body.
- **Registry sau merge: 160 tools** (21 local + 139 MCP deferred sau `tool_search` — model
  thấy tên trong catalog, nạp schema khi gọi `tool_search`/gọi trực tiếp).
- Verify: **238 tests pass · tsc clean**. session.test fail lúc full-run là cross-file
  pollution của bun (pass riêng).

## 9. Skills tiếng Anh (06-10, tối ưu token)

Toàn bộ 26 skills chuyển body + `description` sang English — tiktoken cl100k_base:
**36,131 → 27,736 tokens (−23%)**. GIỮ nguyên: slug tên skill, `triggers.keywords`
tiếng Việt (match input user), câu user mẫu tiếng Việt trong description, verdict labels
user-visible (ỔN ĐỊNH/CẢNH BÁO/BẤT ỔN/NGHIÊM TRỌNG, Tích cực/Tiêu cực/Động lực, kVND,
CHƯA XÁC NHẬN), tool names/budgets/live evidence. Mỗi skill thêm dòng disclaimer
("Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer
in the user's language"). Version bump minor (1.2.0/1.3.0).
Verify: routing TV→English **6/6 câu** (T01 verdict thật 3897 ch + chart_render pipeline;
S07/S16 đúng skill + đúng nguồn; F01/S09/F10 đúng workflow); 238 tests pass · tsc clean.
Nguồn sự thật: `OpenTrading/skills/<slug>/SKILL.md`; bản gộp: `SKILLS.md` (26/26 IN SYNC).
