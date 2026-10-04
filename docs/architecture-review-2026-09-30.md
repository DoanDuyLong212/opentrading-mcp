# Kiến trúc — opentrading-mcp (báo cáo chi tiết, verify 2026-10-02)

MCP server nghiên cứu thị trường VN: stateless-first, tự fetch trực tiếp từ upstream, không qua API trung gian. Mọi số liệu dưới đây verify bằng code + chạy live.

## 1. Tổng quan số liệu

| Hạng mục | Số liệu | Nguồn verify |
|---|---|---|
| Tools live (`all`) | 136 (137 khi có websearch key) | `tools/list` live (P16: +symbol_resolve) |
| Presets | 6 (market 65 / scan 47 / quant 9 / brief 7 / intel 8 / all) | `server.py:50-78` |
| Caps | market 75, scan 60, quant/brief/intel 50 | `server.py:94` |
| Prompts (workflows) | 6 | `prompts.py:112-119` |
| Resources | 4 | `resources.py:14-17` |
| Modules tools | 18 files | `tools/` |
| Providers | 15 files | `providers/` |
| Tests | 248 passed | pytest 2026-10-02 |
| Lint/format | ruff + format sạch; mypy 4 lỗi pre-existing | verify 2026-10-02 |
| Stack | Python 3.12, FastMCP (`mcp>=1.9,<2`), httpx, pandas/numpy (không scipy), bs4, PyJWT, Starlette, uvicorn | `pyproject.toml` |
| Deploy | Docker non-root + `uv sync --frozen`; Render Blueprint (web + worker + Postgres Singapore); Redis external | `render.yaml`, `Dockerfile` |
| Prod URL | `https://opentrading-mcp-web.onrender.com/mcp` | healthz xanh 2026-10-02 |

## 2. Kiến trúc chi tiết (layers)

| Tầng | Files | Trách nhiệm | Ví dụ cụ thể |
|---|---|---|---|
| Transport | `server.py` | stdio (default) + Streamable HTTP stateless `POST /mcp` + legacy `/sse`; register preset, check duplicate, enforce cap | `--preset market` serve 65 tools |
| Middleware | `middleware.py` | RateLimiter → Auth → quota → Observability (1 dòng log/tool) | 120 req/phút/IP; `realm="opentrading-mcp"` |
| Tools (THIN) | `tools/*.py` (18 files) | Validate params → `run_blocking` (thread + timeout) → gọi provider → `make_envelope` | `market.py:279 market_overview` |
| Providers | `providers/*.py` (15 files) | I/O thật: breaker check → httpx/VN lib/WS-cache/scrape | `vietstock.py har_client()` |
| Tính toán local | `providers/technicals.py`, `screener.py` | RSI/MACD/BB/patterns/SEPA-legs, filters, backtest engine | RSI14 Wilder, Donchian-20d |
| Envelope | `schemas.py:24-35` | `{data, provenance, warnings[], availability}` — fail = unavailable, KHÔNG raise | 5 states (§9) |
| Cache | `cache.py:19`, `providers/store.py` | Redis setex → fallback memory dict | key `mcp:{preset}:{tool}:{fingerprint}` |
| Worker | `loops.py:168-171` | 4 loops gather: pump Redis, heartbeat, snapshot ngày | TTL 30s WS, snapshot 17:15 VN |
| Storage | `dbinit.py`, `snapshots.py` | PG 6 bảng + file JSON fallback | DB `opentrading_mcp` (§7) |
| Auth/Quota | `auth.py`, `auth_oauth.py`, `quota.py` | Team bearer / JWT RS256 + quota 1000/ngày | `mcp_tool_usage` (§5) |
| Prompts | `prompts.py` | 6 workflows: chỉ dẫn thứ tự gọi tools | WF1–WF6 (§3) |
| Resources | `resources.py` | 4 URIs tham chiếu | `opentrading://catalog/tools` |

### Bản đồ preset → modules → tools

| Preset | Modules | Tools | Dùng cho |
|---|---|---|---|
| market | market, web, vn, vs, vs_bctc, vn_ext, yf, yf_world, dnse_tools, dnse_ext, crypto | 65 | Agent dữ liệu thị trường full |
| scan | scan, compute, watchlist, corp | 47 | Săn mã + nghiên cứu DN + theo dõi |
| quant | quant | 9 | Backtest/rủi ro/tối ưu |
| brief | brief | 7 | Bản tin + lịch |
| intel | intel, web | 8 | Odds, địa chính trị, cross-asset |
| all | 18 modules | 136 | Full (web_fetch dùng chung) |

## 3. Luồng hoạt động của 1 prompt (ví dụ thật: morning_briefing, chạy live WF1)

Prompt không fetch data — nó bảo agent gọi tools theo thứ tự rồi tổng hợp.

| Bước | Prompt chỉ dẫn (`prompts.py:15-25`) | Tool gọi | Kết quả live 2026-10-02 | File tool |
|---|---|---|---|---|
| 1 | Call brief_build for the composed brief | `brief_build(scope=vn)` | available 2.1s — Greed 70–74, Fireant news live | `brief.py:34` |
| 2 | Call market_overview for quotes/movers/breadth/session | `market_overview(top_n=3)` | partial — VCB 57,400 (−0.35%), HPG 19,950 (−0.50%), session null | `market.py:279` |
| 3 | Call breadth_scan to judge rally health | `breadth_scan()` | available — adv 1 / dec 6 | `market.py:219` |
| 4 | Call money_flow for foreign direction | `money_flow()` | available — NN bán ròng 1,814 vs 2,268 tỷ | `scan.py:294` |
| 5 | Call futures_basis for premium/discount | `futures_basis()` | available — +6.95 (+37bps) | `corp.py:323` |
| 6 | Call world_prediction_odds when macro matters | `world_prediction_odds(limit=5)` | available — Fed giữ nguyên T10: 74.5% | `intel.py:34` |
| 7 | Synthesize in 5 bullets with provenance per line | agent tổng hợp | Phiên yếu + NN bán + premium nhẹ + Fed êm | — |

Luồng dữ liệu trong 1 bước (ví dụ bước 4 `money_flow`):

```
prompt step → tools/call{money_flow} → scan.py:294 THIN (không params)
  → providers: đọc Redis mcp:market:dnse_ws_snapshot:* (lạnh, thiếu worker)
  → fallback Vietstock nn_flow_chart (đủ POST fields P10) → rows BuyVol/SellVol
  → make_envelope(data, source=vietstock, availability=available)
  → agent đọc envelope → bullet "NN bán ròng" + provenance
```

5 prompts còn lại tuân cùng pattern (chi tiết tools + result live xem file tools+workflow, Phần II).

## 4. Luồng 1 tools/call (7 tầng, map đúng file)

| Tầng | File:dòng | Việc làm | Ví dụ (`stock_screener`, live 2026-10-02) |
|---|---|---|---|
| 1. LLM plan | — | Đọc descriptor + inputSchema từ `tools/list` | `technical:{rsi_lt:30}` + `min_roe:0.15` |
| 2. tools/call | JSON-RPC stdio / `POST /mcp` | `{name, arguments}` | `stock_screener{technical, limit:10}` |
| 3. Middleware (HTTP) | `middleware.py:30-206` | rate-limit → auth (user_id) → quota → log-start | team bearer → `user_id=team`, bypass quota |
| 4. Register/boot | `server.py:148-158` | module đã import, check duplicate + cap | scan preset ≤60 tools |
| 5. Tool THIN | `tools/shared.py:71` + tool file | validate → `run_blocking(fn, timeout)` thread + wait_for | timeout → `ProviderUnavailable` |
| 6. Provider guarded | `providers/circuit.py:82`, `errors.py` | breaker closed/open(60s)/half-open; chỉ `ProviderUnavailable` trip | vnstock throttle → warning trung thực |
| 7. Envelope | `schemas.py:24-35` | `{data, provenance{source,as_of,tz}, warnings[], availability}` | `pe/roe:null` + warning, không bịa |

## 5. Bảo mật

| Lớp | Cơ chế | Chi tiết verify |
|---|---|---|
| Transport | TLS (Render) | Secret duy nhất trên dây: Bearer token |
| Rate-limit | Sliding-window 120 req/phút/IP (`MCP_RATE_LIMIT_PER_MIN`), chỉ `POST /mcp`; vượt → 429 + Retry-After | `middleware.py:30,63-65` |
| Auth team | `hmac.compare_digest` với `MCP_BEARER_TEAM` → `user_id="team"`, bypass quota | `middleware.py:113` |
| Auth JWT | RS256 verify qua JWKS (cache 10p) + `iss/aud/exp` + scope → `user_id=sub` | `auth.py`, `auth_oauth.py` |
| Quota | `mcp_tool_usage`, default 1000/ngày; hết → 429 + Retry-After; team bypass | `quota.py:14` |
| Fail-open | Chưa cấu hình token → local dev mở (stdio không auth/limit/quota) | `auth.py` |
| PII | Log chỉ `{tool, duration_ms, ok}` — không args/results/headers (có test assert) | `middleware.py:202-206` |
| Metrics | `/metrics` bắt auth như `/mcp` (counters lộ tên tool) | §1 |
| Secrets | Mọi key ở env, không paste chat/log; file key `/tmp/opencode/*` mode 600 | `MCP_BEARER_TEAM`, `DNSE_*`, `VIETSTOCK_*`, `GROQ_*` |
| Ngoại lệ TLS | HNX cert hỏng → `verify=False` + warning `tls-unverified` trong response | `vn_public.py` |

Ví dụ message thật từ máy user (đã che token):

```
POST /mcp HTTP/1.1 — Host: <render-host>
Content-Type: application/json
Accept: application/json, text/event-stream
Authorization: Bearer <TEAM_BEARER|JWT>     ← secret duy nhất
X-Forwarded-For: <ip>                        ← Render proxy chèn (rate-limit)

{"jsonrpc":"2.0","id":7,"method":"tools/call",
 "params":{"name":"stock_screener",
  "arguments":{"technical":{"rsi_lt":30},"limit":10}}}
```

Chỉ đi: **tên tool + arguments + Bearer token**. Không đi: source code, API key upstream (nằm env server), dữ liệu thô (tính ở server, trả envelope gọn). Sai/thiếu token → **401** + `WWW-Authenticate: Bearer realm="opentrading-mcp"...`.

## 6. Client kết nối (cấu trúc + ví dụ)

5 clients dùng chung 1 pattern, khác tên key config (`configs/`):

| Client | File config | Local (stdio) | Remote (HTTP) |
|---|---|---|---|
| opencode | `configs/opencode.jsonc` | `command: [uvx, opentrading-mcp, serve, --preset, market]` | — |
| Claude | `configs/claude.mcp.json` | `command: uvx + args serve` | — |
| Cursor | `configs/cursor.mcp.json` | `command: uvx + args serve` | — |
| Antigravity | `configs/antigravity.mcp.json` | `command: uvx + args serve` | `serverUrl + Authorization: Bearer` |
| Codex | `configs/codex.toml` | `[mcp_servers.opentrading]` command + `tool_timeout_sec = 60` | — |

Ví dụ stdio session thật (`--preset scan`, capture live):

```
→ {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
    "protocolVersion":"2025-06-18","capabilities":{},
    "clientInfo":{"name":"doc-probe","version":"0.1"}}}
→ {"jsonrpc":"2.0","method":"notifications/initialized"}
← {"jsonrpc":"2.0","id":1,"result":{
    "protocolVersion":"2025-06-18",
    "capabilities":{"prompts":{"listChanged":false},
      "resources":{"subscribe":false,"listChanged":false},
      "tools":{"listChanged":false}},
    "serverInfo":{"name":"opentrading","version":"1.30.0"},
    "instructions":"OpenTrading market-data MCP. Timezone Asia/Ho_Chi_Minh tz-aware. ..."}}
→ {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
← {"jsonrpc":"2.0","id":2,"result":{"tools":[
    {"name":"stock_screener",
     "description":"Screen universe by valuation and quality. ...",
     "inputSchema":{"properties":{"filters":{...},"max_pe":{...},
       "technical":{"title":"Technical"}}, ...}}, ...]}}
```

Ví dụ HTTP (public Render) — chain xử lý:

```
POST https://<host>/mcp
  → RateLimiter (120/phút/IP, exempt /healthz, /.well-known/*)
  → AuthMiddleware (§5) → quota (non-team) → McpObservabilityMiddleware (1 dòng)
  → FastMCP tools/call → SSE stream (json_response=False, stateless, không session id)
GET /healthz → 200/503 + breakdown (redis/pg/worker), ?deep=1 probe từng upstream
GET /.well-known/mcp.json → server card ("add MCP by URL", public)
GET /metrics → Prometheus (bắt auth)
CLI verify: stdio + remote (cli.py: run_verify)
```

## 7. Flow các database

### 7a. PostgreSQL — 6 bảng (`dbinit.py:26-51`, idempotent, DB riêng `opentrading_mcp` port 15432)

| Bảng | Cột chính | Ai ghi | Ai đọc | Dùng cho |
|---|---|---|---|---|
| watchlists | id SERIAL PK, name TEXT UNIQUE | watchlist_create/update | watchlist_list/get | Nhóm mã theo dõi |
| watchlist_items | list_id FK, symbol | watchlist_add/remove | watchlist_get | Mã trong list (dedupe, uppercase) |
| alert_rules | id, symbol, op, threshold, metric, active | alert_create/pause/resume | alert_list, alert_check | Rules giá/RSI |
| mcp_auth_tokens | token, quota_day (default 1000) | admin seed | quota check | Bearer/JWT quota |
| mcp_tool_usage | user, tool, day, count, total_ms | middleware mỗi call | quota check | Đếm quota ngày |
| daily_snapshots | date, kind, payload JSONB | snapshot_loop 17:15 VN | snapshot_history | Lịch sử data hay mất (§7c) |

Flow ghi watchlist (ví dụ live WF `watchlist_create tmp-full135`):

```
watchlist_create(name) → _pg(): connect MCP_DB_URL → auto-ensure tables
  → INSERT watchlists(name) → PG ok? return id : fallback file data/watchlists.json (atomic write)
  → envelope available (đã test tạo/sửa/xóa sạch trong run full-135)
```

### 7b. Redis — keys + TTL (`cache.py:19`, `store.py`, `loops.py`)

| Key pattern | TTL | Ai ghi | Ai đọc | Dùng cho |
|---|---|---|---|---|
| `mcp:{preset}:{tool}:{fingerprint}` | theo tool (snapshot 60s; macro 6h; GDELT 10p) | tool sau khi fetch | tool trước khi fetch | Cache snapshot |
| `mcp:market:dnse_ws_snapshot:{symbol}` | 30s | `dnse_ws_loop` (WS HMAC → pump) | dnse_foreign_flow/indices/market_status | Realtime DNSE |
| `mcp:scan:alert_state` | 3600s | `alert_check` | `alert_check` (cross state) | Chống spam alert |
| `mcp:health:worker` | 60s (2×30s) | `heartbeat_loop` | `/healthz` | Worker liveness |

Thiếu Redis → fallback memory dict (chạy được, mất share giữa processes). Prod thiếu worker → WS keys lạnh → tools trả `unavailable` + warning (P9), REST fallback khi có.

### 7c. Snapshot ngày — 14 kinds (`snapshots.py:15-30`, `loops.py: snapshot_loop`)

| # | Kind | Nguồn | Kích thước live P15 |
|---|---|---|---|
| 1 | market_board | Vietstock board | — |
| 2 | breadth_3ex | Vietstock 3 sàn | — |
| 3 | flows_charts | NN + tự doanh charts | — |
| 4 | heatmap_gics | Vietstock GICS | — |
| 5 | gold_btmc | BTMC | 552KB |
| 6 | sbv_rates | SBV scrape | — |
| 7 | nso_releases | NSO scrape | — |
| 8 | analyst_titles | Vietstock titles | — |
| 9 | macro_curated | GDP/CPI/FX/XNK | 1.5MB |
| 10 | vn30_quotes | vnstock batch | — |
| 11 | futures_basis | DNSE + spot | — |
| 12 | documents_feed | Vietstock docs | — |
| 13 | events_feed | Vietstock events | — |
| 14 | news_feed | Fireant/GDELT | — |

Flow: `snapshot_loop` (17:15 VN/ngày) → `snapshot_once()` best-effort từng kind → `_json_safe` (NaN→None cho JSONB) → `INSERT daily_snapshots` → `snapshot_history(kind, days)` đọc lại (live: macro_curated count 2). P15 live 14/14 ok (sửa số 13 cũ: đếm thiếu `futures_basis`).

### 7d. File fallbacks (khi PG/Redis down)

| File | Khi nào dùng | Ghi chú |
|---|---|---|
| `data/watchlists.json` | PG write fail | atomic write; remove PG transaction (không fallback nửa chừng) |
| `data/runs.jsonl` (`MCP_RUNS_FILE`) | luôn (registry local) | runs_list/run_get (đang trống = đúng) |
| `docs/*.har` | mở Vietstock session | gitignore, không commit (chứa JWT) |

## 8. Worker loops (4 loops, `loops.py:168-171` gather)

| Loop | Interval | Việc làm | Live 2026-10-02 |
|---|---|---|---|
| yf_loop | 60s | Pump yfinance pins vào cache | pins + sparks ok |
| heartbeat_loop | 30s | Ghi `mcp:health:worker` | heartbeat 22s (healthz xanh) |
| dnse_ws_loop | publish 5s | WS HMAC → pump `dnse_ws_snapshot:*` TTL 30s | local lạnh (thiếu worker) → WS trio unavailable trung thực |
| snapshot_loop | 17:15 VN/ngày | `snapshot_once()` 14 kinds → PG | 14/14 ok |

## 9. Bản đồ upstream (tool → nguồn → auth → fallback)

| Nhóm tools | Upstream | Auth | Fallback | Live |
|---|---|---|---|---|
| dnse_* (9) | DNSE WS (worker) + REST HMAC | `DNSE_API_KEY/SECRET` | WS → REST → warning (vs_nn_flow/vs_market_index) | REST ok; WS cần worker |
| vn_* (16) | vnstock VCI → KBS → MSN | không key | VCI → KBS tự động; retail → BTMC https | ok (throttle giờ cao điểm + warning) |
| vs_* (20) | Vietstock cookie+CSRF, JWT paid | JWT hạn 31/10/2026; HAR-session cho macro | mirror free; session-gate → unavailable + hint | macro GDP 504/CPI 1839/XK 2941/XNK 3675 |
| yf_* (9) | yfinance | không key | vn_global_index | S&P 7651, vàng 4195, US10Y ~5.2% |
| crypto_* (2) | Binance public | không key | per-symbol error (không fail batch) | BTC 83,476, funding 2.8e-05 |
| news/sentiment | Fireant → GDELT (retry 1, backoff 20s) | Groq optional | heuristic likes khi thiếu Groq | Fireant live; GDELT từng limit đã hồi |
| odds | Gamma API via jina proxy → direct | không key | jina-first | Fed 74.5%, outcomes+prob, sort vol24h |
| macro US/global | FRED (`FRED_API_KEY`), WorldBank, alternative.me | key FRED | empty trung thực | DGS10, GDP VN 8.02%, greed 74 |
| corp scrape | HNX/NSO/SBV/Vietstock-titles (bs4) | không | announcements fallback | SBV 3%/4.5%, targets FPT live |
| web_search | Exa/Parallel (`WEBSEARCH_PROVIDER`) | key → ẩn khỏi list khi thiếu | — | gated |

## 10. Envelope & availability (nguyên tắc P9: không available-giả)

| State | Khi nào | Ví dụ live |
|---|---|---|
| available | data thật | futures_basis +5.89 (+31bps) |
| partial | một số legs fail, còn lại dùng được | market_overview (session null, quotes ok) |
| empty | query hợp lệ nhưng không rows | analyst_consensus VCB (không báo cáo mới), ipo auctions, insider deals |
| stale | data cũ quá TTL (worker chưa pump) | (cơ chế có, chưa gặp live) |
| unavailable | upstream chết/từ chối + warning rõ | WS trio (thiếu worker), BCTC package-limit + hint mirror |

## 11. Deploy & verify (evidence)

| Deploy | Commit | Nội dung | Verify |
|---|---|---|---|
| 2026-09-30 ~23:15 | 2ca4a67 | P5→P8 + stack Phase 0-2 | healthz breakdown mới; /mcp 401 đúng realm |
| 2026-10-01 ~00:30 | 17e1155 | P9 honest-availability | health xanh sau cycling |
| 2026-10-01 ~01:30 | 1027287 | P10 required POST fields | nn/selftrading/gics/marketinfo sống lại |
| 2026-10-01 | 4c91136 | P11 breadth/reference/vàng | pytest 258 passed, health xanh |
| 2026-10-01 | ac99396 | P12 xóa 3 tools chết | catalog gọn |
| 2026-10-01 | 716bcba | P12b basis/money_flow/sentiment | basis +4.68 live |
| 2026-10-02 | 958b957 + 3485e6a | P13/P14/P15 macro+snapshots+forensic | health xanh; full-135 + 6 workflows live |
| 2026-10-02 | 1d9f498 | Docs full-135 + workflows | push origin/main ok |

Verify commands (evidence tươi 2026-10-02): `pytest tests/ -q --ignore=tests/contract/test_verify_matrix.py` → **248 passed**; `ruff check` → sạch; `ruff format --check` → 54 files ok; `mypy` → 4 lỗi pre-existing (pandas-stubs, markdownify, no-any-return — từ HEAD, bỏ qua).

Rollback: Render Dashboard → Deploys → Rollback (baseline cũ `3ef5530`, 69 tools).

## 12. Findings trung thực (từ trace live)

| # | Phát hiện | Trạng thái |
|---|---|---|
| 1 | Listing rows chỉ có `{symbol, name}` — filter `exchange:` rỗng live | Đã fix: reference qua KBS source (HOSE 757) |
| 2 | `t` của vnstock v4 chỉ là ngày-trong-tháng | Tools dùng ISO + business-day walkback + `date_note` |
| 3 | Fundamentals throttle theo giờ (0/20 enriched) | Best-effort + warning, không bịa số |
| 4 | GDELT từng rate-limit, yf_yield_curve từng flaky | Tự hồi (retry/backoff); live xanh |
| 5 | financial_statements warning statement-filter với mirror | Data đủ (all pages); chờ chuẩn hóa tên statement |
| 6 | scenario last_close đơn vị kVND (62.7 = 62,700đ) | Hiển thị, không sai số P/L |
| 7 | sentiment heuristic khi thiếu Groq key (−0.25) | Ghi rõ trong warnings |
| 8 | `/sse` legacy chờ tắt; quota fail-open khi PG down (chủ ý); cold start 20–40s; DNSE geo-block từ Singapore | Thiết kế, documented |
