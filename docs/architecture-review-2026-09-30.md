# Architecture Review — opentrading-mcp (as-built 2026-09-30)

Review toàn diện sau P5 (params) → P6 (descriptors) → P7 (17 tools mới + prompts/resources).
Thay thế bản 2026-09-24/28. Mọi số liệu dưới đây đã verify bằng code + chạy live ngày 2026-09-30.

## 1. Big picture

**opentrading-mcp**: MCP server nghiên cứu thị trường VN, stateless-first, tự fetch trực tiếp
từ upstream (Vietstock / vnstock VCI-KBS-MSN / DNSE REST+WS / yfinance / Binance public /
HNX-NSO-SBV scrape / GDELT / FRED / WorldBank). Không qua API layer trung gian.

- **Stack**: Python 3.12 + FastMCP (`mcp>=1.9,<2`, lock `uv.lock`), httpx, pandas/numpy
  (không scipy, không pypdf — quyết định có chủ ý, xem §8), bs4, PyJWT, Starlette, uvicorn.
- **139 tools live** (`all`; market 66 / scan 49 / quant 9 / brief 7 / intel 7) · caps
  (`server.py:94`: market 75, scan 60, còn lại 50) · **6 presets** + **6 prompts**
  (morning_briefing, ticker_analysis, pre_earnings v2, sector_rotation, ai_detect,
  risk_check) + **4 resources**
  (`opentrading://catalog/tools` live, `reference/{term-types,exchanges,gics}`).
- **Transports**: stdio (default) + Streamable HTTP stateless `POST /mcp` + legacy `/sse`.
- **Deploy**: Docker non-root + `uv sync --frozen` + HEALTHCHECK `/healthz`; Render Blueprint
  (web + worker + Postgres, Singapore); Redis external qua `REDIS_URL`.
  ✅ **Prod đã deploy bản mới 2026-09-30 ~23:15** (`main = 2ca4a67`, gồm P5→P8 + stack
  Phase 0-2; local từng ahead origin 16 commits). Verify live: `/healthz` format breakdown
  mới (redis pong/postgres select 1/worker heartbeat 21s đều OK); `/mcp` không token → 401
  đúng middleware mới (`realm="opentrading-mcp"`); `/metrics` bắt auth; `/.well-known/mcp.json`
  public. Chưa verify `tools/list` = 142 + smoke call (cần team bearer, không lưu local).
  Rollback: Render Dashboard → Deploys → Rollback về deploy trước (baseline cũ
  `origin/main = 3ef5530`, serve 69 tools).
- ✅ **Deploy P9 2026-10-01 ~00:30** (`main = 17e1155`): honest-availability fixes.
  Verify live: `/healthz` xanh (redis/pg/worker heartbeat 2s); auto-deploy quan sát
  cycling rỗng → healthy. Chưa đếm `tools/list` tay (thiếu team bearer).
- ✅ **Deploy P10 2026-10-01 ~01:30** (`main = 1027287`): required POST fields —
  nn_flow/selftrading/gics/market_info sống lại live; macro trả permission message thật.
- ✅ **Deploy P11 2026-10-01** (`main = 4c91136`): breadth case-count, reference KBS,
  vàng BTMC https, financial_detail chain. Verify: pytest **258 passed**, health xanh.
- ✅ **Deploy P12 2026-10-01** (`main = ac99396`): xóa 3 tools chết
  (reports_search 404, stock_industry hết mapping, top_liquidity body rỗng);
  `macro_reports` hồi sinh qua consensus scrape (live: MSN MUA 89,200).
- ✅ **Deploy P12b 2026-10-01** (`main = 716bcba`): futures_basis ohlc-fallback
  (live basis +4.68), money_flow dùng nn_chart path (live), sentiment chịu body list.
  Health xanh sau cycling. Rollback: Dashboard → Deploys → Rollback (baseline 3ef5530).
- **Tầng tin cậy**: middleware chain (rate-limit → auth → observability), circuit breaker
  per-upstream (`providers/circuit.py`), JSON logging, `/metrics`, healthcheck thật + `?deep=1`,
  OAuth 2.1 resource-server + quota PG theo user/ngày.

## 2. Client kết nối trông như nào

5 clients đều dùng chung 1 pattern, khác nhau ở tên key config (`configs/`):

| Client | File | Local (stdio) | Remote (HTTP) |
|---|---|---|---|
| opencode | `configs/opencode.jsonc` | `command: [uvx, opentrading-mcp, serve, --preset, market]` | — |
| Claude/Cursor/Antigravity | `configs/{claude,cursor,antigravity}.mcp.json` | `command: uvx + args serve` | Antigravity thêm `serverUrl + Authorization: Bearer` |
| Codex | `configs/codex.toml` | `[mcp_servers.opentrading]` command + `tool_timeout_sec = 60` | — |

### 2a. stdio (máy user/dev/LAN) — sample thật

Client spawn subprocess, JSON-RPC 2.0 qua stdin/stdout. Capture live (`--preset scan`):

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

Không auth / không rate-limit / không quota trên stdio (máy local tin cậy — `auth.py:18-19`
fail-open khi chưa cấu hình token).

### 2b. Streamable HTTP (public Render) — middleware chain

```
POST https://<host>/mcp
Headers: Content-Type: application/json
         Accept: application/json, text/event-stream
         Authorization: Bearer <team-token|JWT>        ← duy nhất secret trên dây
Body:    {"jsonrpc":"2.0","id":7,"method":"tools/call",
          "params":{"name":"stock_screener","arguments":{...}}}
  → RateLimiter (120 req/phút/IP, X-Forwarded-For; exempt /healthz, /.well-known/*)
  → AuthMiddleware (§5) → quota (non-team) → McpObservabilityMiddleware (1 dòng log)
  → FastMCP tools/call → SSE stream (json_response=False, stateless: không session id)
```

Kèm theo: `GET /healthz` (200/503 + breakdown, `?deep=1` probe live từng upstream),
`GET /.well-known/mcp.json` (server card cho "add MCP by URL"),
`GET /metrics` (Prometheus, **bắt auth như /mcp** vì counters lộ tên tool).
`MCP_ALLOWED_HOSTS` bắt buộc khi `--http` trừ `--allow-all-hosts` (chống DNS-rebinding).
CLI `verify` hỗ trợ stdio + remote (`cli.py: run_verify`).

## 3. Luồng 1 query từ LLM vào MCP (7 tầng, map đúng file)

```
LLM plan tool (đọc descriptor + inputSchema từ tools/list)
  → tools/call{name, arguments} (JSON-RPC, stdio hoặc POST /mcp)
  → [HTTP] middleware: rate-limit → auth (user_id) → quota → log-start
  → server.py: module đã register lúc boot (import + check duplicate + cap)
  → tools/<mod>.py THIN: validate → run_blocking(fn, 10-120s, asyncio.to_thread + wait_for)
       → providers/<fn> [@guarded(upstream)]: breaker check → I/O thật (httpx/VN lib/WS cache/scrape)
  → make_envelope(data, source, warnings, availability) — fail = unavailable, KHÔNG raise
  → [HTTP] log 1 dòng {tool, duration_ms, ok} + metrics → SSE response → LLM đọc envelope
```

- **Timeout**: `run_blocking` (`tools/shared.py:71`) — timeout → `ProviderUnavailable`.
- **Breaker** (`providers/circuit.py:82`): closed/open(60s recovery)/half-open; chỉ
  `ProviderUnavailable` mới trip; `CircuitOpenError ⊂ ProviderUnavailable` nên tool cũ vẫn
  degrade về envelope. Gắn tại `dnse._get`, `vietstock._post/_post_json`, batch yfinance,
  `binance`, `vn_public`.
- **Cache** (`providers/store.py`): Redis setex TTL → fallback memory dict;
  key `mcp:{preset}:{tool}:{fingerprint}`.
- **Worker decoupling**: `dnse_ws_loop` (WS HMAC → pump Redis snapshots TTL 30s),
  `yf_loop` 60s, `heartbeat` 30s — web process chỉ ĐỌC Redis.
- **Envelope chuẩn** (`schemas.py`): `{data, provenance{source, as_of, timezone:
  Asia/Ho_Chi_Minh}, warnings[], availability: available|empty|stale|partial|unavailable}`.

## 4. Sample query end-to-end (chạy live 2026-09-30)

> **"Tìm kiếm các cổ phiếu rsi dưới 30 và có báo cáo tài chính tốt."**

**LLM plan** (từ descriptors): `rsi dưới 30` → `technical: {rsi_lt: 30}` (stage-3 của
`stock_screener`, preset scan); `BCTC tốt` → `min_roe` + `max_pe` (stage-2, fundamentals
qua `vnstock Fundamental.ratio`). Một call duy nhất:

```json
{"method": "tools/call", "params": {"name": "stock_screener", "arguments": {
  "filters": {"exchange": "HOSE"}, "min_roe": 0.15, "max_pe": 20,
  "technical": {"rsi_lt": 30}, "limit": 10 }}}
```

**Luồng thật trong `scan.py: stock_screener`:**
- Stage 1 — universe: `vn_p.listing_symbols` → **1522 mã**.
- Stage 2 — enrich fundamentals (semaphore 5, 10s/symbol) + `apply_filters`. Hôm nay
  upstream vnstock throttle → `0/20 enriched`, warning trung thực, min_roe không lọc được.
- Stage 3 — technical trên candidates đầu: `quote_history(sym, 80)` → `technicals.compute`
  (RSI14 Wilder) → giữ `rsi14 < 30`.

**Kết quả live** (`technical={rsi_lt:30}, limit=20`, 11.4s, `available`):

| Mã | Tên | RSI14 live | Ghi chú |
|---|---|---|---|
| TMB | Than Miền Bắc – Vinacomin | **20.53** | last 42.0 < sma20 45.56, oversold thật |
| PNJ | Vàng bạc Đá quý Phú Nhuận | **19.08** | last 26.6 < sma20 35.68, oversold thật |
| NWT | Vận tải Newway | 0.0 | thanh khoản mỏng — RSI biên, cần check thêm |

`pe/roe: null` kèm warning (không bịa số). Muốn thêm "BCTC tốt" khi upstream hết throttle:
gọi lại với `min_roe: 0.15`, hoặc `valuation_run` / `financial_statements` từng mã.

## 5. Cơ chế bảo mật + mẫu message từ máy user

**Cái gì rời khỏi máy user trên dây** (mẫu đã che token):

```
POST /mcp HTTP/1.1
Host: <render-host>
Content-Type: application/json
Accept: application/json, text/event-stream
Authorization: Bearer <TEAM_BEARER|JWT>     ← secret duy nhất
X-Forwarded-For: <ip>                        ← Render proxy chèn (dùng cho rate-limit)

{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{
  "name":"stock_screener",
  "arguments":{"technical":{"rsi_lt":30},"limit":10}}}
```

- Chỉ đi: **tên tool + arguments + Bearer token**, qua **TLS**. Không đi: source code,
  API key của upstream (DNSE/Vietstock/Groq nằm ở env server), dữ liệu thô upstream
  (tính ở server, trả envelope gọn).
- **Auth** (`middleware.py:90`): team bearer so `hmac.compare_digest` → `user_id="team"`,
  bypass quota; hoặc JWT RS256 verify qua JWKS (cache 10p) + `iss/aud/exp` + scope →
  `user_id=sub`, quota `mcp_tool_usage` (default **1000/ngày**, hết → **429 + Retry-After**).
  Server không phát hành token (resource-server thuần). Sai/thiếu → **401** +
  `WWW-Authenticate: Bearer realm="opentrading-mcp"...`. Chưa cấu hình gì → fail-open
  (local dev).
- **Rate-limit**: sliding-window 120 req/phút/IP, chỉ `POST /mcp`; vượt → 429 + Retry-After.
- **PII rule**: observability chỉ log `{tool, duration_ms, ok}` — **không args/results/headers**
  (có test assert). `/metrics` bắt auth vì counters lộ tên tool.
- **Secrets**: mọi key ở env (`MCP_BEARER_TEAM`, `DNSE_API_KEY`, `VIETSTOCK_*`, `GROQ_*`),
  không paste vào chat, không vào log; file key `/tmp/opencode/*` mode 600.
- **Upstream direction**: server → Vietstock/DNSE/Binance/HNX/NSO/SBV qua HTTPS (ngoại lệ duy
  nhất: HNX cert chain hỏng → `verify=False` + warning `tls-unverified` trong response).

## 6. Data flow upstream (tóm tắt)

`tools/*` (142: market 71/scan 49/quant 9/brief 7/intel 7 + prompts/resources ngoài preset)
→ `providers/`: `vietstock` (cookie+CSRF session, JWT paid), `vnstock` (VCI→KBS fallback),
`dnse` (HMAC WS+REST, WS cache qua worker), `yfinance`, `binance` (public, không key),
`vn_public` (HNX/NSO/SBV/Vietstock-titles scrape, bs4), `intel` (GDELT/FRED/WorldBank/Groq),
`technicals`/`screener` (tính local, numpy/pandas) → envelope.

## 8. P8: AI-detect prompts + SEPA legs (2026-09-30 chiều)

- **8010 tham khảo-only** (không tools nối 8010, không copy pickle): SEPA = Breakout Model 2
  (gate `is_breakout` → proba ≥ 0.85); BCD = Model 1 (gate `breakdown` → điểm B/C);
  ranking = super_stock LightGBM (`/api/super-stock/scores`, prob_x2). Không port được
  (cần pickle + Redis feature store + PG 8010) → prompt mô phỏng heuristic.
- **`ai_detect(symbol?)`** mới: 5 legs (trend template / contraction / breakout confirm /
  fundamentals / flow) → STRONG(≥4)/WATCH/REJECT; descriptor ghi rõ no-ML-proba.
  Không symbol → `signals_scan` rồi validate từng hit.
- **`risk_check(symbols, side, size_vnd)`** mới: quant_risk → scenario scale size →
  correlation → forensic → events blackout → valuation → GO/HALF/NO-GO.
- **`pre_earnings` thay v1** bằng reliability grading A/B/C + unknowns (không surprise level).
- **SEPA legs trong `technicals.compute`**: `rs_vs_bench` (spread 63d vs VNINDEX, None khi
  <20 điểm), `pos_52w` (biên 250d), `sma150`; `signals_technical` fetch VNINDEX best-effort.
- Live VCB: dưới sma50/150/200, adx 11.81, RS −1.89, pos_52w 0.21 → REJECT đúng rubric.
- Verify: pytest **229 passed**, ruff + format sạch, mypy chỉ 4 lỗi pre-existing.

## 7. Findings trung thực (mới, từ trace live)

1. **Listing rows chỉ có `{symbol, name}`** — không field exchange → filter `exchange:` rỗng
   live (test mock không bắt được). Descriptor nói "symbol/exchange equality" gây hiểu lầm;
   cần bổ sung venue từ nguồn khác hoặc sửa descriptor.
2. **`vs_reports_search` chết upstream** (`CompanyReportSearch` 404) — tool trả unavailable
   trung thực; đã thay bằng `analyst_consensus` scrape titles.
3. **Fundamentals bị throttle theo giờ** (0/20 enriched hôm nay) — design best-effort +
   warning đúng, nhưng query phụ thuộc ROE/PE sẽ rỗng vào giờ cao điểm.
4. **`t` của vnstock v4 chỉ là ngày-trong-tháng** — tools quant dùng ISO khi có, fallback
   business-day walkback + `date_note` trong output.
5. `gso.gov.vn` đã chết → dùng `nso.gov.vn`; NWT RSI 0.0 là edge mã mỏng, không phải bug tính.
6. Còn lại từ bản cũ (vẫn đúng): `/sse` legacy chờ tắt; quota fail-open khi PG down (chủ ý);
   metrics `ok` là HTTP-level; cold start Render 20-40s; DNSE geo-block từ Singapore.
7. **Doc này mô tả WORKTREE local** (đã verify: 142 tools, 6 prompts, flows, số liệu).
   Từ deploy 2026-09-30 ~23:15, prod ≈ worktree (trừ `tools/list` 142 chưa đếm tay vì
   thiếu team bearer). Muốn kiểm tra: gọi `/mcp` kèm `Authorization: Bearer $MCP_BEARER_TEAM`.
8. **P9 honest-availability (2026-10-01, đã deploy 17e1155)**: news error-payload,
   foreign errorCode, BCTC package-limit, industry empty đều → unavailable/empty thay vì
   available-giả; lookup không dấu (NFD+Đ→D); DNSE REST 7/7 sống lại với key thật
   (foreign-trading endpoint từ chối mọi range 10m→30d); orderbook rỗng lúc 00:05 là
   đúng (ngoài giờ). pytest 239 passed.

## 8. P14–P15: storage theo ngày + macro thật + tối ưu catalog

- **DB riêng `opentrading_mcp`** (PG 15432, không đụng db 8010): `dbinit` idempotent
  6 bảng (watchlists/items, alert_rules, mcp_auth_tokens, mcp_tool_usage đúng schema
  quota, **daily_snapshots(date,kind,payload)**); watchlist `_pg()` auto-ensure +
  write-fallback file khi SQL lỗi; `MCP_DB_URL`/`DATABASE_URL` trỏ db mới.
- **Worker `snapshot_loop`** 17:15 VN/ngày: 13 kinds best-effort (market_board,
  breadth_3ex, flows_charts NN/prop, heatmap_gics, gold_btmc, sbv_rates, nso_releases,
  analyst_titles, macro_curated GDP/CPI/FX/XNK, vn30_quotes, news_feed, documents/events
  feeds) — live 13/13 ok (vàng 552KB, macro 1.5MB). Tool mới **`snapshot_history`**.
  Fix kèm: `_json_safe` (NaN→None cho PG JSONB), load() chịu dict/list/str.
- **Vietstock HAR-session replay**: env `VIETSTOCK_COOKIE_HEADER`+`VIETSTOCK_PAGE_TOKEN`
  hoặc parse `docs/*.har` (gitignore, không commit). Standard pack LẤY ĐƯỢC macro đầy đủ
  (bằng chứng replay cookie trình duyệt + termType đúng). Redis cache TTL 6h cho macro,
  10p cho GDELT (retry backoff 20s ×1).
- **Catalog 136**: xóa macro_reports + 3 alias + vs_financial_values + signals_trade_log
  (P12–P15, có thay thế documented); thêm polymarket_event + planned_targets +
  snapshot_history + financial_detail(revive); market_snapshot VN30-30;
  signals_scan HOSE ≤300; OHLCV interval 1D/1W/1M; news Fireant primary.
- Verify P15: pytest, ruff + format, mypy (trừ pre-existing) — xem báo cáo commit.
