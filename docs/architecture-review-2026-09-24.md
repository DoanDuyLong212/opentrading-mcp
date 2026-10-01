# Architecture Review — opentrading-mcp (post-upgrade, 2026-09-28)

Tài liệu kiến trúc + luồng hoạt động sau đợt nâng cấp Phase 0–2
(ổn định nội bộ → public an toàn, tải nhỏ). Ghi đè bản review 2026-09-24.

## 1. Big picture (as-built)

**Opentrading MCP-server**: MCP server phục vụ nghiên cứu thị trường VN,
stateless-first, tự lấy data trực tiếp từ upstream (không qua API layer khác).

- **Stack**: Python 3.12 + FastMCP (`mcp>=1.9,<2`, lock `uv.lock` commit),
  httpx, psycopg (PG 16, sync + asyncio), redis, vnstock, yfinance, pandas,
  uvicorn, markdownify/bs4, PyJWT + cryptography (OAuth), Starlette (middleware).
- **126 tools unique** · preset caps (`market` 70, còn lại 50) · **6 presets**
  (`market/scan/quant/brief/intel/all`).
- **2 transports**: stdio (default, mọi client, open khi không token) +
  Streamable HTTP stateless `POST /mcp` + legacy `/sse` (giữ cho client cũ).
- **Deploy**: Docker (`python:3.12-slim`, user `appuser` non-root, `uv sync
  --frozen`, HEALTHCHECK `/healthz`) — web + worker + Postgres (Render
  Blueprint, Singapore, auto-deploy main). Redis external qua `REDIS_URL`.
- **Tầng tin cậy mới**: middleware chain (rate-limit → auth → observability),
  circuit breaker per-upstream, JSON logging, `/metrics`, healthcheck thật,
  OAuth 2.1 resource-server + quota PG theo user/ngày.

## 2. Client giao tiếp như nào

### stdio (team LAN, local dev)

Client spawn subprocess, JSON-RPC 2.0 qua stdin/stdout (`cli.py: main()` →
`server.run(transport="stdio")`). Không auth, không rate-limit, không quota
(máy local tin cậy).

### Streamable HTTP (Render public) — middleware chain

```
POST /mcp
 → RateLimiter (120 req/phút/IP, X-Forwarded-For; exempt /healthz, /.well-known/*)
 → AuthMiddleware (401/429, \S4)
 → McpObservabilityMiddleware (1 dòng JSON log + metrics; exempt non-/mcp)
 → FastMCP tools/call → SSE stream (json_response=False)
```

- `GET /healthz` → 200/503 + breakdown components (`?deep=1` probe live DNSE/Vietstock/yfinance).
- `GET /.well-known/mcp.json` → server card cho "add MCP by URL".
- `GET /metrics` → Prometheus text; **bắt auth như `/mcp`** (counters lộ tên tool).
- `MCP_ALLOWED_HOSTS` (DNS-rebinding protection): bắt buộc khi `--http`
  trừ khi `--allow-all-hosts` (local/LAN). Tool `verify` hỗ trợ stdio + remote.

## 3. Luồng đi một call (5 tầng)

```
Client tools/call{name, arguments}
 → middleware: rate-limit → auth (user_id) → quota (non-team) → log-start
 → server.py: preset đã register lúc boot (import module, check duplicate + cap)
 → tools/<mod>.py THIN: validate → run_blocking(fn, 30-120s thread+timeout)
      → providers.<guarded(upstream)>: circuit breaker check → I/O thật
 → make_envelope(data, source, warnings, availability) — fail = unavailable, KHÔNG raise
 → middleware: log 1 dòng {tool, duration_ms, ok} + metrics → SSE response
```

- **`run_blocking`** (`tools/shared.py`): `asyncio.to_thread` + `wait_for`; timeout → `ProviderUnavailable`.
- **Circuit breaker** (`providers/circuit.py`): closed/open(60s recovery)/half-open-trial;
  chỉ đếm `ProviderUnavailable` (auth/data-shape không trip);
  `CircuitOpenError` là subclass của `ProviderUnavailable` nên tool cũ vẫn
  degrade về envelope thay vì crash (bug đã bắt bằng verify matrix).
  Gắn tại choke points: `dnse._get`, `vietstock._post/_post_json`, 8 hàm batch yfinance.
- **Cache** (`providers/store.py`): Redis setex TTL → fallback memory dict; key `mcp:{preset}:{tool}:{fingerprint}`.
- **Worker decoupling** (`loops.py`, Docker riêng): `dnse_ws_loop` (WS HMAC → pump
  Redis snapshots TTL 30s, backoff 5→120s), `yf_loop` 60s, `heartbeat` 30s.
  Web process chỉ ĐỌC Redis.

## 4. Data shape (envelope chuẩn — không đổi)

```json
{
  "data": { ... per-tool shape ... },
  "provenance": {"source": "vnstock|dnse-rest|vietstock|...", "as_of": "ISO8601", "timezone": "Asia/Ho_Chi_Minh"},
  "warnings": ["..."],
  "availability": "available | empty | stale | partial | unavailable"
}
```

## 5. Auth model (Phase 2)

| Caller | Cách nhận diện | Quota |
|---|---|---|
| Local dev (không cấu hình gì) | open, `user_id` unset | không |
| Team nội bộ | `Authorization: Bearer $MCP_BEARER_TEAM` (so sánh constant-time) → `user_id="team"` | **không giới hạn** |
| Public user | JWT RS256: verify signature qua JWKS (cache 10p) + `iss`/`aud`/`exp` + scope (`MCP_JWT_REQUIRED_SCOPE`) → `user_id=sub` | `mcp_auth_tokens.quota_day` (default 1000/ngày), đếm trong `mcp_tool_usage`; hết → **429 + Retry-After** tới nửa đêm |
| Thiếu/sai credentials | **401** + header `WWW-Authenticate: Bearer realm="opentrading-mcp"...` chỉ chỗ lấy token | — |

- Server **không phát hành token** (đúng vai resource-server): dùng IdP ngoài
  (`MCP_JWT_ISSUER/AUDIENCE/JWKS_URL`). Không `DATABASE_URL` → quota skip (fail-open, local dev).
- Env mới: `MCP_RATE_LIMIT_PER_MIN` (default 120), `MCP_JWT_*` (4 biến), `--allow-all-hosts` (flag).

## 6. Observability (Phase 1)

- **Logs**: 1 dòng JSON/call `{ts, event:"tool_call", tool, duration_ms, ok, error_code}` ra stdout — **không args/results/headers** (PII rule, có test assert).
- **Metrics** (`/metrics`, Prometheus): `tool_calls_total`, `tool_errors_total{tool,error}`,
  `tool_latency_ms_{sum,max}`, `upstream_failures_total{upstream}`. Lưu ý trung thực:
  `ok` ở tầng HTTP (status<500); lỗi logic trong envelope không lật cờ này.
- **Health** (`/healthz`): Redis ping, PG `SELECT 1`, worker heartbeat age; unset env → `skipped`
  (không fail); `?deep=1` probe live từng upstream (8s timeout mỗi cái).
- **Alert gợi ý** (chưa tự động — Render starter không có Grafana): error-rate >5%/5p,
  p95 >10s, 3 healthcheck fail liên tiếp, container restart. Nguồn số liệu: log stream + `/metrics`.

## 7. Ops & verify (evidence đợt này)

- **Tests**: 110 passed (`tests/contract/`: boot/presets/infra/matrix + health/middleware/obs/auth mới);
  full matrix stdio ~6 phút **pass** (1 lần fail đã điều tra: flaky upstream + bug breaker-đã-fix, có regression test).
- **TDD**: test đỏ trước cho health/middleware/obs/auth (12+7+4+11 cases), smoke test live bắt 2 bug thật
  (metrics lọt auth; close-error nuốt kết quả verify client).
- **Live smoke** (server thật, team bearer): `/mcp` không token→401, có token→200 tool chạy thật;
  `/metrics` không token→401, có token→200 counters đúng; `/healthz`→200 mở.
- **Docker verify**: build OK, chạy user `appuser`, `/healthz` trả breakdown components thật.
- **ruff + mypy strict**: sạch trên mọi file mới/sửa (4 lỗi mypy + 9 file format drift là **có sẵn ở HEAD**, không đụng tới).

## 8. Findings còn lại (trung thực)

1. `/sse` legacy vẫn bật — tắt khi hết client cũ.
2. Quota fail-open khi PG down (chủ ý cho availability; đảo lại khi cần strict).
3. Metrics `ok` là HTTP-level, không phản ánh envelope `unavailable` (ghi rõ để khỏi hiểu lầm khi alert).
4. Render free/starter sleep + cold start: request đầu sau idle chậm (đã thấy 20-40s ở verify); muốn hết hẳn cần plan cao hơn, ngoài scope tải nhỏ.
5. DNSE từ Singapore vẫn timeout (geo-block) — worker VN + proxy là đường chính, đã ghi trong skill docs.
6. Chưa làm (đúng plan, tải nhỏ không cần): tách server theo capability, K8s/gateway riêng, sticky session (spec đã bỏ), Grafana tự host.
