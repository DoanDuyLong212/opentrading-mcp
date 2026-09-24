# Architecture Review — opentrading-mcp (main @ 5010d07, 2026-09-24)

Tài liệu để trình bày/nghiên cứu: client giao tiếp như nào, luồng đi, data shape, kiến trúc, ops.

## 1. Big picture

**Opentrading MCP-server**: MCP server phục vụ nghiên cứu thị trường VN, tự lấy data trực tiếp từ upstream (không qua một API layer khác).

- **Stack**: Python 3.12 + FastMCP (`mcp>=1.9,<2`), httpx, psycopg (PG 16), redis, vnstock, yfinance, pandas, uvicorn, markdownify/bs4.
- **126 tools unique** · 117 READ_ONLY / 9 READ_WRITE · **6 presets** (`market` 69/70, `scan` 42/50, `quant` 4, `brief` 5, `intel` 8/50, `all` 126).
- **2 transports**: stdio (default, mọi client) + Streamable HTTP stateless `POST /mcp` + legacy `/sse`.
- **Deploy**: Docker web + worker + Postgres (Render Blueprint, region singapore, healthcheck `/healthz`, auto-deploy khi push main). Redis external qua `REDIS_URL`.

## 2. Client giao tiếp như nào

### stdio (team LAN, local dev)

Client (opencode/Claude/Cursor/Codex) spawn subprocess và nói JSON-RPC 2.0 qua stdin/stdout:

```
configs/*.json →
"command": "uvx", "args": ["opentrading-mcp", "serve", "--preset", "market"]
```

1. Client spawn process → server chạy `server.run(transport="stdio")`.
2. `initialize` handshake: client gửi protocolVersion/capabilities → server trả `serverInfo {name:"opentrading", version:"1.30.0"}`, `capabilities {tools, prompts, resources}`, `instructions` (SERVER_INSTRUCTIONS: quy ước snake_case, btype, TTL...).
3. `tools/list` → client nhận 126/69 tools với `inputSchema` sinh tự động từ signature (FastMCP tự bỏ `ctx`).
4. `tools/call {name, arguments}` → chạy → trả `{content:[{type:"text", text:"<JSON envelope>"}]}`.

Auth stdio: không cần token (máy local tin cậy).

### Streamable HTTP (Render public)

- Endpoint `POST https://opentrading-mcp-web.onrender.com/mcp` — **stateless**: mỗi POST độc lập, không session cookie.
- `initialize` và `tools/call` trả về **SSE stream** (`event: message\ndata: {jsonrpc...}`) vì `json_response=False`; client MCP chuẩn (streamablehttp_client) tự parse.
- Fallback `/sse` (legacy transport) cho client cũ.
- **Discovery routes**: `GET /healthz` → `{"ok":true}` (Render healthcheck), `GET /.well-known/mcp.json` → server card (name, endpoint, transports) cho client dùng "add MCP by URL".
- **Auth**: `auth.py` có `get_bearer()`/`is_authorized()` đọc `MCP_BEARER_TEAM`/`MCP_TOKEN`, `redact()` che secret — nhưng **CHƯA được wire vào HTTP app** (không middleware nào gọi `is_authorized`). Hiện remote **không bắt Bearer**. `configs/antigravity.mcp.json` ghi header Bearer nhưng server không kiểm tra → finding cần fix trước khi public.

### Connect flow client thật (opencode)

`opencode.json` khai `mcp.opentrading` → client spawn/POST → `tools/list` → tool key sanitize `/[^a-zA-Z0-9_-]/→_` → LLM chọn tool theo descriptor → `tools/call` → envelope JSON.

## 3. Luồng đi một call (kiến trúc 4 tầng)

```
Client (JSON-RPC tools/call)
  → cli.py main() [chọn preset, tạo server 1 lần]
  → server.py: create_server(preset) → FastMCP(name, instructions, stateless_http=True,
        streamable_http_path="/mcp", sse_path="/sse", transport_security=MCP_ALLOWED_HOSTS)
    register_preset() → import module theo PRESET_MODULES, gọi register_<mod>_tools(server)
        → kiểm tra duplicate name + preset cap (raise nếu vượt)
  → tools/<mod>.py: async def tool(params, ctx) — THIN LAYER:
        validate nhẹ → run_blocking(fn, timeout) → projection/summary → make_envelope
        (long tools: ctx.report_progress + ctx.log, không print stdout)
  → providers/<nguồn>.py: I/O thật — httpx (Vietstock/DNSE/FRED/GDELT/Fireant/Groq),
        vnstock lib, yfinance lib, psycopg (watchlist/alert), Redis store, websearch JSON-RPC
  → trả make_envelope(data, source, warnings, availability)
```

- **`run_blocking`** (`tools/shared.py`): bọc sync provider call bằng `asyncio.to_thread` + `asyncio.wait_for(timeout)`; timeout → `ProviderUnavailable "timed out"`. Timeout từng tool hard-cap 30-120s; `TIMEOUT_MATRIX` ở `server.py` là contract cho client-side config.
- **Envelope `make_envelope`** (`schemas.py`): mỗi tool fail → envelope `availability="unavailable"` + warnings, KHÔNG raise — `tools/list` không bao giờ vỡ.
- **Cache**: `providers/store.py` tiered Redis (`REDIS_URL`, setex TTL, socket 2-3s) → fallback `_memory` dict in-process. Key `mcp:{preset}:{tool}:{fingerprint}`.
- **Worker decoupling** (`loops.py`, chạy riêng trong Docker): `dnse_ws_loop` (WS DNSE msgpack/json HMAC → pump Redis `mcp:market:dnse_ws_snapshot:{sym}` TTL 30s, backoff 5→120s), `yf_loop` (60s pump global/commo TTL 300s), `heartbeat` (30s TTL 60s). Web process chỉ ĐỌC Redis → không giữ WS trong web process.
- **Preset filter**: `PRESET_MODULES` map preset→modules; `PRESET_CAPS` giữ `tools/list` nhanh (market 70, scan/quant/brief/intel 50); tool "all" không cap.

## 4. Data shape (envelope chuẩn)

Mọi tool trả đúng 1 shape:

```json
{
  "data": { ... per-tool shape ... },
  "provenance": {
    "source": "vnstock|dnse-rest|vietstock|yfinance|postgres|file|computed-local|aggregator|cache|unavailable",
    "as_of": "2026-09-24T09:15:00+00:00",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "warnings": ["(fallback: vs_nn_flow)", "capped 50 symbols, 5 dropped", "daily-only: interval '1W' ignored"],
  "availability": "available | empty | stale | partial | unavailable"
}
```

Shape per family:
- **Candles**: `{t (unix sec UTC), o, h, l, c, v}` hoặc khi `summary=true` → `{count, last, high, low}` (không kèm raw bars — tiết kiệm context, pattern TradingView).
- **Batch**: `{series: [{symbol, candles|summary}], missing: [{symbol, error}]}` + availability `partial` khi lẻ lỗi.
- **Quotes**: rows từ `Market.equity.quote()` (`close_price, volume_accumulated, percent_change`...).
- **Screener**: `{candidates: rows}`, filters `{field:[min,max]}` (null = unbounded) + equality cho sector/industry/index.
- **Technicals**: `{rsi14, stoch_k/d, cci20, adx14, macd{line,signal,hist}, momentum10, ao, ema10/20/50, sma10/20/50/200, vwma, hull9, boll{upper,lower}, atr14, recommend}`.
- **Watchlist/alert**: rows PG (id int, name, symbols[]) hoặc file JSON fallback cùng shape.
- **Sai/không resolve** → báo `missing[]` thay vì bịa số 0.

## 5. Providers (upstream I/O) — ai gọi ai

| Provider | Giao thức | Ghi chú |
|---|---|---|
| `vietstock.py` | httpx: mirror free `/data/*` + BCTC JWT (`/FinancialStatement/*`) + GICS + Macro + `dc.vietstock.vn` news | Auth chain: env JWT → seed session.json → login Email/Password + CSRF; HTML-shell → reset + retry 1; Permission/Limit → `ProviderAuthMissing` |
| `vnstock.py` | vnstock lib (VCI/KBS/MSN/Retail) | `quote_history`/`insider_trading` tự fallback VCI→KBS; `reference_equity` fail-closed |
| `dnse.py` | httpx REST HMAC (date + nonce, `x-api-key`, `version: 2026-05-07`) | signature `(request-target): get <path>\ndate\nnonce` base64+URL-quote; 2-path orderbook |
| `yfinance.py` | yfinance lib | batch download 2d/1mo/2y/5y |
| `webfetch.py` | httpx direct | cap 5MB, CF retry, ảnh → base64 |
| `websearch.py` | POST JSON-RPC `tools/call` tới Exa/Parallel MCP | chọn provider env/hash; parse JSON + SSE `data:` |
| `intel.py` | GDELT, jina→Gamma, FRED, WorldBank, Fireant, Groq, alternative.me | retry pattern cho GDELT |
| `screener.py`, `technicals.py` | pandas/numpy local | không network |
| `store.py` | redis + memory | TTL từng key |

## 6. Invariants (điều bất biến cần nói khi trình bày)

1. Mọi tool qua `make_envelope` — timezone Asia/Ho_Chi_Minh tường minh, provenance source/as_of bắt buộc.
2. Graceful degradation: upstream chết → `unavailable` envelope, không crash, tools/list vẫn OK.
3. Tool name snake_case, prefix nguồn (`vs_|vn_|yf_|dnse_|world_|signals_|quant_|brief_|intel_|watchlist_|alert_`), 1 tool = 1 endpoint family, duplicate → raise khi register.
4. Preset cap mỗi preset <50 (trừ market 70, all uncapped) — bảo vệ context LLM.
5. Thêm params mới luôn **additive + default giữ cũ** (backward-compat: `summary/columns/bar_type/interval`).
6. Web process stateless (scale ngang được); state thật nằm Redis/PG/file.

## 7. Ops & verify

- **Local run**: `opentrading-mcp serve --preset market` (stdio) | `--http --port 8102` (LAN).
- **Deploy**: push main → Render auto-deploy Blueprint (`render.yaml`: web starter + worker + pg 16, singapore, `/healthz`). Verify: `/healthz` 200 → `/mcp` initialize → `tools/list` → `tools/call source_status`.
- **`opentrading-mcp verify`** (`verify.py`): client MCP giả lập opencode — stdio subprocess hoặc remote StreamableHTTP→SSE fallback, connect timeout, per-call timeout, tool key sanitize; `verify_matrix.py` = contract: mỗi preset chạy bộ calls thật, assert envelope (`data/provenance/warnings/availability`, timezone).
- **Tests**: `tests/contract/` 78 test — presets/boot/infra/matrix + P1-P4 (TDD). Full matrix cần network ~5 phút.
- **Docker compose**: mcp-web (`serve --preset market --http`), mcp-worker (`python -m opentrading_mcp.loops`), postgres:16; Redis external.

## 8. Findings (cần lưu ý khi public)

1. **Bearer auth chưa wire** — `auth.py` có sẵn nhưng HTTP server không middleware check. Remote hiện public không token. Fix: add ASGI middleware `is_authorized` trước khi public.
2. `web_search` ẩn khi thiếu key (thiết kế đúng, nhớ nói khi demo).
3. TTL cache chỉ có thật ở `market_snapshot` + worker loops; phần lớn tools live-fetch (không cache) → Render free tier sẽ hit upstream mỗi call.
4. Bảng 3 trong skills_check.md mô tả một số fallback chưa implement (Kalshi/Manifold, RSS, OpenBB, PG/8010 read-only).
5. Preset `market` 69/70 — gần cap, thêm tool mới vào market sẽ vỡ.
6. `MCP_ALLOWED_HOSTS` (DNS rebinding protection) chỉ bật khi set env.
