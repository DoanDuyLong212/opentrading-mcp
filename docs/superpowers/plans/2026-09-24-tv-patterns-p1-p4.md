# TV-patterns P1-P4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port 4 patterns TradingView MCP vào opentrading-mcp không phụ thuộc TV.

**Architecture:** Giữ envelope `make_envelope` + provenance Asia/Ho_Chi_Minh; tính local từ candles/quotes có sẵn; cache Redis/memory via providers/store.py; PG cho P4; preset scan 29/50.

**Tech Stack:** Python 3.12, FastMCP mcp>=1.9,<2, vnstock>=3.0, pandas>=2.0, Postgres 16 + Redis 7, pytest.

## Global Constraints

- Tool names snake_case prefix vs_|vn_|yf_|dnse_|world_|signals_|quant_|brief_|intel_.
- Timezone Asia/Ho_Chi_Minh tz-aware everywhere.
- Transports stdio + Streamable HTTP stateless POST /mcp + legacy /sse.
- Presets each <50 tools trừ all; PRESET_CAPS market:70 scan:50 quant:50 brief:50.
- Backend Postgres 16 + Redis 7 only. No MongoDB.
- TIMEOUT_MATRIX là contract (server.py:33).
- 1 tool = 1 endpoint family.
- P4 persist: PG (quyết định user). P3: pandas (quyết định user).

---

### Task 1: P1 summary+columns+missing

**Files:**
- Modify: src/opentrading_mcp/tools/vn.py, src/opentrading_mcp/tools/vn_ext.py, src/opentrading_mcp/tools/dnse_tools.py, src/opentrading_mcp/tools/market.py
- Test: tests/contract/test_p1_summary_columns.py

**Interfaces:**
- Consumes: providers/vnstock.py quote_history, index_ohlcv, equity_ohlcv; providers/dnse.py ohlc_history
- Produces: vn_quote_history(symbol,days=365,summary=False,columns=None), market_candles_batch(symbols,days=30,summary=False)->{series,missing}

- [ ] Step 1: Write failing test for summary shape + missing[].
- [ ] Step 2: Thêm summary/columns vào 5 tools đơn.
- [ ] Step 3: Chuẩn hóa batch với cap 50 + availability partial.
- [ ] Step 4: Run pytest P1 + verify_matrix.
- [ ] Step 5: Commit.

### Task 2: P2 screener catalog + filters

**Files:**
- Create: src/opentrading_mcp/providers/screener.py
- Modify: src/opentrading_mcp/tools/scan.py, src/opentrading_mcp/tools/compute.py, src/opentrading_mcp/providers/vnstock.py (fix reference_equity)
- Test: tests/contract/test_p2_screener.py

**Interfaces:**
- Consumes: listing_symbols, vn_reference, vn_fundamentals
- Produces: signals_screener_columns(group=None,search=None), stock_screener(filters=None,max_pe,min_roe,limit=20)

- [ ] Step 1: Write failing test catalog pe/roe.
- [ ] Step 2: Tạo COLUMNS + apply_filters local.
- [ ] Step 3: Wire stock_screener enrich top candidates, fix reference filter.
- [ ] Step 4: Run pytest, check scan cap <=50.
- [ ] Step 5: Commit.

### Task 3: P3 full technicals pandas

**Files:**
- Create: src/opentrading_mcp/providers/technicals.py
- Modify: src/opentrading_mcp/tools/scan.py (signals_technical)
- Test: tests/contract/test_p3_technicals.py

**Interfaces:**
- Consumes: vn_p.quote_history(symbol,120)
- Produces: signals_technical(symbol,interval="1D")->rsi14,stoch,cci20,adx14,macd,momentum10,ao,ema/sma,vwma,hull9,bb,atr14,recommend

- [ ] Step 1: Write failing test RSI Wilder + MACD shape.
- [ ] Step 2: Implement pandas indicators, clamp RSI, gate len<30 empty.
- [ ] Step 3: Wire giữ tương thích signature cũ.
- [ ] Step 4: Run pytest.
- [ ] Step 5: Commit.

### Task 4: P4 watchlist/alert PG

**Files:**
- Create: src/opentrading_mcp/tools/watchlist.py
- Modify: docker/postgres/init.sql, src/opentrading_mcp/providers/store.py, src/opentrading_mcp/tools/scan.py (alert_check), src/opentrading_mcp/server.py (preset scan)
- Test: tests/contract/test_p4_watchlist_alert.py

**Interfaces:**
- Consumes: store.cache_get/set, PG watchlists/watchlist_items/alert_rules
- Produces: watchlist_create/list/get/add/remove/delete/update + alert_create/list/delete/pause/resume; alert_check mở rộng metric price|rsi14, op >,>=,<,<=,cross_up,cross_down

- [ ] Step 1: Write failing test CRUD shape.
- [ ] Step 2: SQL 3 bảng + cache keys mcp:scan:watchlist, fallback memory/file data/watchlist.json.
- [ ] Step 3: Implement 8 tools + nâng alert_check, đăng ký preset scan (giữ <=50).
- [ ] Step 4: Run pytest + presets cap.
- [ ] Step 5: Commit.
