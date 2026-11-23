# Tools + Workflow — opentrading-mcp (cập nhật 2026-11-23)

**174 tools remote (173 unique + alias `vn_crypto_ohlv`) · +1 gated `web_search` → 175 entries live khi có key · 28 module · 6 prompts · 5 resources · single full surface, không preset**

(Rev 2026-11-23: đồng bộ trực tiếp từ `create_server()` + `register_all()` / `tools/list`.
So với bản 2026-10-06 thêm **35 tool / 7 module**: `cycle_stats` 9, `asset_cycle` 11,
`market_timing` 1 (`distribution_count`), `vn_predictions` 3, `vn_screener` 3,
`vnindex_scenarios` 4, `vn_reversal` 4. Descriptor toàn bộ tool đã đổi sang chuẩn
"Dùng khi / Không dùng khi" từ 2026-10-14; params mới: `vs_indicator_data.indicator`,
`signals_technical.ichimoku_convention`, `analyst_consensus.days`,
`web_fetch.format` / `timeout_seconds`. Runtime hiện tại: vnstock 6.0.0 (gen 6) cùng
các nguồn Yahoo/Vietstock mirror; `web_search` chỉ xuất hiện khi có key provider.)
(Rev 2026-10-06: tách `compute.py` → `compute_financial/intel/infra.py`, `quant.py` → `quant_backtest/stats.py` + `quant_shared.py`;
`@guarded` 15 fn vnstock + 9 fn intel; vocab `source` chuẩn `ALLOWED_SOURCES` (`v`→`vietstock`);
`verify_matrix.py`; mount `/sse` thật; `as_of` tz-aware; crypto caps 10/5.)
(Rev 2026-10-05: bỏ preset custom `market/scan/quant/brief/intel/all` → 1 hình dạng `tools/list`
chuẩn MCP; CLI `--preset` deprecated; annotations `READ_ONLY/CREATE/DELETE/STATE`;
envelope thêm `page{total,offset,limit,next}` + `error`; `symbol_lookup` thêm `offset`.)

**Mốc live gần nhất:** full matrix 2026-10-02 (135/135: 129 available · 1 partial · 2 empty · 3 unavailable);
các dòng `[10-05]`/`[10-06]` giữ nguyên lịch sử. 35 tool mới (2026-10-10 → 10-31) chưa nằm trong lần chạy đó:
`distribution_count` đã verify live 2026-11-23 (`available`); nhóm PG (`cycle_*`, `vn_asset_*`,
`g_asset_*`, `vn_predictions_*`, `vn_screener_*`, `vnindex_*`, `vn_reversal_*`) cần `DATABASE_URL`
+ pipeline `mcp-opentrading-sub` ghi schema `predictions` — cột Avail ghi `chưa verify (PG)`.

## 0. Surface duy nhất (bỏ preset từ 2026-10-05)

| Module | Tools | Ghi chú |
|---|---|---|
| market | 9 | `market_movers` trả `{gainers, losers, volume_leaders, universe}`; `symbol_lookup` thêm `offset` + `page`; `source_status` probe vnstock thật + release verdict |
| web | 1 (+1 gated `web_search` khi có key) | không đổi |
| vn | 6 | không đổi |
| vs | 8 | không đổi |
| vs_bctc | 12 | không đổi |
| vn_ext | 11 (10 + alias `vn_crypto_ohlv`) | rename `vn_crypto_ohlv` → `vn_crypto_ohlcv`, giữ alias cũ |
| yf | 3 | không đổi |
| yf_world | 6 | không đổi |
| dnse_tools | 4 | không đổi |
| dnse_ext | 5 | không đổi |
| crypto | 2 | không đổi |
| scan | 6 | `alert_check` annotation `READ_WRITE_STATE` (ghi cross-state); `stock_screener` partial khi enrich thiếu |
| compute_financial | 7 | tách từ `compute.py`: forensic/valuation/statements/ratios/peers/overview/events (behavior giữ nguyên) |
| compute_intel | 7 | tách từ `compute.py`: fred/worldbank/fear-greed/sentiment/events/assets/insider |
| compute_infra | 6 | tách từ `compute.py`: scan/pattern/snapshot/runs/doctor |
| corp | 9 | không đổi |
| watchlist | 12 | annotations CREATE/DELETE (`watchlist_remove` → DELETE); `watchlist_create` PG guard trùng tên |
| quant_backtest | 4 | tách từ `quant.py`: backtest/scenario/strategies/sweep (+`quant_shared.py` engine chung); `quant_backtest` doc deprecate |
| quant_stats | 6 | tách từ `quant.py`: risk/factors/correlation/seasonality/optimize/event_study |
| brief | 8 | `brief_build` bỏ hardcode vietstock-unavailable, warnings live từ `auth_status` |
| intel | 7 | không đổi |
| cycle_stats | 9 | PG `cycle_*`: seasonality/chains/turning/tet/yearly/trough_events + refresh/finalize (2026-10-10) |
| asset_cycle | 11 | PG `vn_asset_*` + `g_*`: 9 read + 2 refresh (`vn_asset_refresh`, `g_asset_refresh`) |
| market_timing | 1 | `distribution_count` — O'Neil distribution days + follow-through (2026-10-14) |
| vn_predictions | 3 | PG `predictions.predictions_daily`: 43 tài sản, dự báo 12 tháng (2026-10-28) |
| vn_screener | 3 | PG `predictions.screener_signals_daily`: P(touch +20%/20 phiên) (2026-10-29) |
| vnindex_scenarios | 4 | PG `predictions.vnindex_scenarios_daily`: kịch bản + risk heads (2026-10-29) |
| vn_reversal | 4 | PG `predictions.reversal_signals_daily` + `reversal_sector_daily` (2026-10-31) |
| **Tổng** | **174 remote (173 unique + alias `vn_crypto_ohlv`); + `web_search` gated → 175 live** | `register_all()` 1 shape; `--preset` deprecated; 28 module |

> Cột **Nơi chạy** trong mọi bảng tool bên dưới: `remote` = thực thi trên MCP-server
> (Python/FastMCP, qua `tools/call`); `local` = tools của harness OpenTrading (xem
> section riêng cuối Phần I — sau merge upstream 06-10: **21 local** = 16 của mình
> (chart/render, session, doctor, watchlist cá nhân, web_fetch/web_search, spawn_subagent)
> + 5 upstream (`ask_user`, `todo_write`, `tool_search`, `list/read_mcp_resource`).

| Kênh avail (live 2026-10-02, giữ nguyên) | Số tools | Ghi chú |
|---|---|---|
| available | 132 | 129 từ run full-135 (gồm 3 tools re-run: signals_scan, valuation_run, financial_statements) + 3 tools P16–P17 (`symbol_resolve`, `event_study`, `fireant_thread` — verify live riêng, đều xanh) |
| partial | 1 | market_overview (session leg null, thiếu WS worker) |
| empty (đúng) | 2 | runs_list, run_get (chưa có runs local) |
| unavailable | 3 | dnse_foreign_flow, dnse_ws_snapshot, dnse_indices (cần worker local; prod có) |

Timeout contract [10-05]: `TIMEOUT_MATRIX` đã xóa (stale 11 entries). Per-tool `run_blocking(secs=)` + client `toolTimeoutMs`
(opencode `timeout`, Codex `tool_timeout_sec`, OpenTrading `toolTimeoutMs` 60s + wrapper +5s).

Env chạy lại: `set -a; source ~/Trading_Agents/.env; set +a; export MCP_DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:15432/opentrading_mcp" VIETSTOCK_HAR_FILE="docs/finance.vietstock.vn_Archive [26-10-01 18-35-43].har"`.

---
## market.py — 9 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| market_snapshot | ['symbols', 'as_of'] | Toàn cảnh thị trường VN: bảng giá VN30 kèm nguồn gốc dữ liệu. Dùng khi cần bức tranh thị trường rộng trong một lần gọi. | Báo giá VN30 (hoặc `symbols` truyền vào) kèm trần/sàn/tham chiếu/vol + nguồn. `as_of` chỉ là nhãn. | DNSE board rows + VN30 live basket (cache 60s) | `{"quotes": [{"symbol": "ACB", "time": 1790910967815.0, "exchange": "HOSE", "ceiling_price": 22550.0, "floor_price": 19650.0, "reference_price": 21100.0, "open_p` | available | remote |
| source_status | [] | Sức khỏe từng nguồn dữ liệu + trạng thái TTL. Dùng khi nghi ngờ dữ liệu cũ hoặc tool báo lỗi nguồn. | Sức khỏe từng upstream (JWT, vnstock probe thật + quota tier + release verdict, WS, TTL). Gọi đầu tiên khi nghi data cũ. [10-05] [10-06: vnstock_quota + API key 60 req/min] [11-23: release verdict + canary 6h] | local + probe `quote_history(VCB,1)` 5s | `{"upstreams": {"vietstock": {"authenticated": true, "jwt_expires_at": 1790943335}, "vnstock": "ok", "dnse_ws": "cold"}, "stateless": true, "ttl": {"snapshot": 5` | available | remote |
| market_candles_batch | ['symbols', 'days', 'summary', 'columns'] | Nến OHLCV theo ngày cho NHIỀU mã, mỗi mã một request. Dùng khi cần dữ liệu vẽ nhiều đồ thị cùng lúc. | Nến hàng loạt; mã lỗi vào `missing`, không fail cả batch. | vnstock VCI→KBS per symbol | `{"series": [{"symbol": "VCB", "count": 5, "last": 57.3, "high": 58.5, "low": 57.2}, {"symbol": "HPG", "count": 5, "last": 19.95, "high": 20.8, "low": 19.9}], "m` | available | remote |
| symbol_resolve | ['query', 'limit'] | Giải mã BẤT KỲ mã tài sản nào ra symbol + loại tài sản + tool tiếp theo. Dùng ĐẦU TIÊN khi không chắc mã thuộc loại nào. | Phân giải mọi mã (CK VN, crypto, forex, index TG, futures, vàng/dầu) thành symbol chuẩn + loại tài sản + tool tiếp theo, xếp hạng + cờ ambiguous để fallback. | local tables + vnstock Listing | `{"resolved": {"symbol": "GC=F", "asset_class": "commodity"}}` (live: vàng→GC=F, BTC→BTCUSDT, VN30F1M→futures) | available | remote |
| symbol_lookup | ['query', 'limit', 'offset'] | Tra tên công ty ra mã, sàn và ngành. Dùng TRƯỚC mọi lệnh theo mã khi chưa chắc mã chính xác. | Tra mã từ tên công ty không dấu (`hoa phat` → HPG). | vnstock Listing + Reference | `{"hits": [{"symbol": "HPG", "name": "CTCP Tập đoàn Hòa Phát"}, {"symbol": "HPA", "name": "CTCP Phát triển Nông nghiệp Hòa Phát"}, {"symbol": "HTP", "name": "CTC` | available | remote |
| market_movers | ['top_n', 'universe'] | Top tăng/giảm mạnh và dẫn đầu thanh khoản. Dùng khi kiểm tra nhịp phiên (mã nào đang chạy, dòng tiền ở đâu). | Top tăng/giảm/volume từ bảng DNSE; `universe=vn30` (mặc định, nhanh) hoặc `hose` (≤60 mã, chậm, có thể partial). | DNSE board rows + live VN30 basket | `{"gainers": [...], "losers": [...], "volume_leaders": [...], "universe": N} [10-05; cũ: {"movers": [{"symbol": "VCB", "time": 1790910971687, "exchange": "HOSE", "ceiling_price": 61600, "floor_price": 53600, "reference_price": 57600, "open_price": 5` | available | remote |
| breadth_scan | ['exchange'] | Đếm mã tăng/giảm/đứng/trần/sàn theo từng sàn. Dùng khi đánh giá sức khỏe đợt tăng (tăng có lan tỏa hay chỉ vài trụ kéo). | Đếm mã tăng/giảm/trần/sàn toàn sàn (đếm case-insensitive). | Vietstock getmarketprice + marketinfo | `{"advancers": 1, "decliners": 6, "rows": 7}` | available | remote |
| market_overview | ['top_n'] | Context thị trường một lần gọi: giá bluechip, movers, độ rộng, phiên. Dùng cho bản tin và câu hỏi tổng quan. | Gộp quotes+movers+breadth+session một call; legs degrade độc lập (partial khi thiếu worker). | vnstock batch + DNSE WS (session) | `{"quotes": [{"symbol": "VCB", "time": 1790910974093, "exchange": "HOSE", "ceiling_price": 61600, "floor_price": 53600, "reference_price": 57600, "open_price": 5` | partial | remote |
| dnse_market_status | [] | Trạng thái phiên DNSE kèm snapshot chỉ số mới nhất. Dùng khi kiểm tra phiên đang mở hay đóng. | Trạng thái phiên DNSE + snapshot chỉ số (REST fallback khi WS lạnh). | DNSE WS cache → DNSE REST → unavailable | `{"rest": [{"symbol": "VN30F1M", "trades": []}]}` | available | remote |

## web.py — 1 tool (+1 gated)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| web_fetch | ['url', 'format', 'timeout_seconds'] | Đọc một URL và chuyển thành markdown, text, html hoặc text PDF. Dùng khi đọc nội dung trang web cụ thể. | Đọc URL → markdown/text/html/**pdf** (stdlib-only, scan báo trung thực), cap 5MB, retry CF-403; `format` mặc định markdown, `timeout_seconds` mặc định 30 (cap 120). | httpx trực tiếp (browser-UA, cap 5MB) | `{"title": "https://example.com (text/html; charset=utf-8)", "output": "Example DomainThis domain is for use in documentation examples without needing permission` | available | remote |

## vn.py — 6 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vn_quote_history | ['symbol', 'days', 'summary', 'columns', 'interval'] | Nến 1 mã VN (1D/1W/1M), VCI trước KBS dự phòng. Dùng cho MỌI lịch sử giá của một mã. Dùng khi: "lịch sử giá FPT", "HPG có vượt đỉnh 20 phiên không", mọi tính toán cần chuỗi giá 1 mã. | Nến ngày/tuần/tháng 1 mã VN, VCI→KBS tự fallback. | vnstock VCI→KBS tự fallback | `{"symbol": "VCB", "count": 5, "last": 57.3, "high": 58.5, "low": 57.2}` | available | remote |
| vn_equity_quote_batch | ['symbols', 'summary', 'columns'] | Bảng giá một lần cho NHIỀU mã. Dùng khi chụp nhanh giá khớp nhiều mã hoặc làm movers thủ công. | Bảng giá N mã trong 1 request từ DNSE; giữ ghi chú ngoài giờ. | DNSE project client (board rows) | `{"count": 2, "symbols": ["VCB", "HPG"]}` | available | remote |
| vn_listing | ['limit'] | Full symbol list with company names. Use for universe and lookup. limit: max symbols returned (universe ~1500). | Universe 1522 mã toàn thị trường kèm tên công ty. | vnstock Listing().all_symbols() | `{"count": 1523, "symbols": [{"symbol": "DPP", "name": "CTCP Dược Đồng Nai"}, {"symbol": "SDA", "name": "CTCP Simco Sông Đà"}, {"symbol": "CLH", "name": "CTCP Xi` | available | remote |
| vn_fundamentals | ['symbol', 'period', 'report_type'] | Chỉ số tài chính tính bằng vnstock_quant.fa từ ba BCTC (gen 6). Định giá nhanh 1 mã. Dùng khi: "PE/PB/ROE của FPT", snapshot định giá nhanh. | PE/ROE/EPS/BVPS từ `vnstock_quant.fa` (gen 6) trên 3 BCTC; quý = TTM. | vnstock_quant.fa + 3 BCTC (Vietstock financeinfo) | `{"symbol": "VCB", "ratios": "                                                 item  ...      2022\n0   Thu nhập trên mỗi cổ phần của 4 quý gần nhất (...  ...   ` | available | remote |
| vn_retail_gold | ['source'] | SJC and ring gold buy/sell from BTMC retail. Use for local gold premium. | Giá vàng SJC/nhẫn BTMC trực tiếp qua https (timeout 15s). | BTMC JSON https trực tiếp → vnstock fallback | `{"rows": [{"name": "VÀNG MIẾNG SJC (Vàng SJC)", "karat": "24k", "gold_content": "999.9", "buy_price": "13950000", "sell_price": "14350000", "world_price": "4150` | available | remote |
| vn_retail_fx | [] | Tỷ giá Vietcombank mua/bán hôm nay. Dùng khi cần giá ngân hàng mua vào/bán ra ngoại tệ. | Tỷ giá mua/bán của VCB (đa ngoại tệ). | Vietcombank public board (cache 1h, ≤1 req/5 phút) | `{"rows": [{"currency_code": "AUD", "currency_name": "AUSTRALIAN DOLLAR", "buy_cash": "17,507.78", "buy_transfer": "17,684.63", "sell": "18,251.32", "date": "202` | available | remote |

## vs.py — 8 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vs_auth_status | [] | Vietstock JWT state and expiry. Use before any paid BCTC call. | Trạng thái JWT Vietstock + hạn dùng. | Vietstock session (env JWT → session.json) | `{"authenticated": true, "jwt_expires_at": 1790943335}` | available | remote |
| vs_financeinfo | ['symbol', 'period'] | BCTC mirror miễn phí, 12 quý hoặc năm. Dùng khi KHÔNG có JWT Vietstock. Dùng khi: đọc BCTC mà chưa đăng nhập Vietstock. | BCTC mirror miễn phí 12 quý/năm — nguồn BCTC chính khi không cần detail. | Vietstock /data/financeinfo (mirror free) | `{"symbol": "VCB", "period": "quarter", "pages": [[[{"ID": 5, "Row": 5, "CompanyID": 1167, "YearPeriod": 2025, "TermCode": "Q2", "TermName": "Quý 2", "TermNameEN` | available | remote |
| vs_market_price | ['type'] | Live board snapshot from Vietstock. Use as secondary quote source. type: board id (2 = main board). | Board giá live Vietstock (dự phòng cho bảng giá). | Vietstock /data/getmarketprice | `{"rows": [{"Code": "VNIndex", "Name": "VN-Index", "Price": 1740.46, "Change": -8.84, "PerChange": -0.51, "Color": "#F00", "TradingDate": "/Date(1790874000000)/"` | available | remote |
| vs_market_index | [] | Index closes with 1M and YTD change. Use for index context. | Chỉ số + biến động 1M/YTD. | Vietstock GetMarketIndexVNData | `{"indices": {"data": [{"IndexID": "1", "IndexTitle": "VN-Index", "MarketType": 0, "IndexType": 1, "BasicIndex": 1749.3, "CloseIndex": 1740.41, "PerChange": -0.5` | available | remote |
| vs_nn_flow | ['days'] | Biểu đồ mua/bán khối ngoại. Dùng khi đối chiếu chéo dòng tiền với DNSE WS. Dùng khi: kiểm tra lại số liệu money_flow/dnse_foreign_flow bằng nguồn thứ hai. | Chart mua/bán khối ngoại (bắt buộc đủ POST fields). | Vietstock KQGDGiaoDichNDTNNChart | `{"flow": [["/Date(1790910869700)/"], [{"TradingDate": "/Date(1790528400000)/", "BuyVol": 51180300, "BuyVal": 1461.532125, "SellVol": 58399100, "SellVal": 1682.1` | available | remote |
| vs_categories | [] | Macro indicator catalogue (~60 categories). Use before indicator queries. | Danh mục ~60 chỉ tiêu macro để tra cứu trước khi query. | Vietstock Macro GetIndicatorCategoryData | `{"categories": [{"CategoryID": 7, "ParentID": 0, "CategoryName": "1. Tài khoản quốc gia (GDP)", "Level": 1, "DisplayOrder": 1, "HasData": false, "ListTermType":` | available | remote |
| vs_indicator_data | ['category_id', 'term_type_id', 'sub_term_type_id', 'from_date', 'to_date', 'indicator'] | Macro series (GDP/CPI/FX/trade) via browser-session replay. Use for macro reads. indicator: 'GDP' (quarterly), 'CPI' (YoY) or 'XK' (exports, monthly) — the server fills the id pair, so prefer it for these. | Số macro thật (GDP/CPI/XK) qua HAR-session replay + termType đúng; `indicator` tự điền cặp id cho GDP/CPI/XK. | Vietstock Macro (HAR-session replay, cache 6h) | `{"category": 73, "term_type": 3, "rows": [{"name": "TỔNG SỐ", "group": "", "period": "Quý 1/2022", "year": "2022", "value": 2137413.0, "unit": "Tỷ VNĐ", "timeor` | available | remote |
| vs_trading_info | ['symbol'] | Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot. There is no tool named vs_prices or vs_financial_ratios — use this tool (snapshot) or financial_ratios (sets) instead. | Trần/sàn/room/EPS/BVPS/PE/PB nhanh theo mã. | Vietstock /company/tradinginfo | `{"symbol": "VCB", "info": {"StockCode": "VCB", "TradingDate": "/Date(1790910986000)/", "KLCPLH": 8355675094, "KLCPNY": 8355675094, "PriorClosePrice": 57600, "Ce` | available | remote |

## vs_bctc.py — 12 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vs_financial_terms | [] | Report term catalogue (annual, Q1-Q4, H1, 9M). Use before BCTC value queries. | Danh mục kỳ báo cáo (năm, Q1–Q4, H1, 9M). | Vietstock GetListReportTerm | `{"terms": {"data": [{"ReportTermID": 1, "ReportTermTypeID": 1, "Description": "Năm", "DescriptionEn": "Year", "DisplayOrdering": 1, "ExportName": "NAM", "FromMo` | available | remote |
| vs_financial_norms | ['btype'] | 190+ BCTC line items for a business type. Use to resolve norm ids. btype: 1 CTCP (general), 2 securities, 3 bank, 5 insurance. | Tra 190+ chỉ tiêu BCTC theo loại hình DN (256 norms). | Vietstock BCTC_GetChiTieuForTable | `{"btype": 1, "count": 256, "norms": [{"ReportNormID": -1111, "Name": "Báo cáo tình hình tài chính", "PublishNormCode": null, "NormCode": null, "CssStyle": null}` | available | remote |
| vs_company_info | ['symbol'] | Tên công ty, sàn và mô tả. Dùng khi cần hồ sơ ngắn gọn. Dùng khi: "FPT là công ty gì, niêm yết ở đâu". | Hồ sơ DN: tên, sàn, mô tả. | Vietstock BCTC_CompanyByCodes | `{"info": {"data": [{"StockCode": "VCB", "CompanyID": 1167, "CatID": 1, "CompanyName": "Ngân hàng TMCP Ngoại thương Việt Nam", "CompanyNameEN": "Joint Stock Comm` | available | remote |
| vs_overview_trading | ['symbol'] | Giao dịch theo ngày gần đây của 1 mã từ Vietstock: giá đóng cửa, khối lượng, giá trị, mua/bán của khối ngoại và tự doanh. | Giao dịch vài phiên gần nhất: close/volume/value + NN + tự doanh (KHÔNG có P/E, P/B). | Vietstock GetStockDeal_OverviewTrading | `{"overview": {"data": [{"StockCode": "VCB", "TradingDate": "/Date(1790874000000)/", "ClosePrice": 57300, "ColorID": -1, "Change": -300, "PerChange": -0.52, "Tot` | available | remote |
| vs_documents | ['symbol', 'page_size'] | Filings and disclosures with links. Use for corporate actions. page_size: max documents returned (default 60). | Công bố thông tin + link PDF tải trực tiếp. | Vietstock /data/GetDocument | `{"docs": [{"FileExt": ".pdf ", "UpdateTime": null, "TotalRow": 487, "FileInfoID": 559412, "Url": "https://static2.vietstock.vn/data/HOSE/2026/NGHI QUYET HDQT/VN` | available | remote |
| vs_industry_tree | [] | GICS industry tree. Use before sector mapping. | Cây ngành GICS 285 nodes. | Vietstock GetTreeViewIndustryGICS | `{"tree": {"Id": 2, "Name": "Nhóm ngành", "ListIndustry": [{"IndustryID": 1, "Level": 1, "IndustryCode": 10, "ParentCode": 0, "IndustryName": "Năng lượng", "Ima` | available | remote |
| vs_industry_heatmap | [] | Live sector heatmap. Use for intraday rotation. | Heatmap ngành live trong phiên. | Vietstock GetHeatmapGICS | `{"heatmap": [{"IndustryCode": 10, "ParentCode": 0, "Level": 1, "DisplayOrder": 0, "IndustryName": "Năng lượng", "StockFullName": null, "ImageURL": "/content/im` | available | remote |
| vs_selftrading | [] | Prop-desk flow chart. Use alongside foreign flows. | Dòng tiền tự doanh CTCK. | Vietstock KQGDGiaoDichTuDoanhChart | `{"flow": [["/Date(1790841600000)/"], [{"TradingDate": "/Date(1788454800000)/", "BuyVol": 12735108, "BuyVal": 444.906387, "SellVol": 18948028, "SellVal": 618.016` | available | remote |
| vs_gics_index | ['group'] | GICS index closes with foreign flow. Use for sector context. group: index set (1, 2 or 3 return different groups). | Chỉ số ngành GICS theo 3 nhóm + NN mua/bán. | Vietstock GetGICSIndexMain {type} | `{"group": 1, "rows": [{"IndustryCode": 1010, "Url": "/nganh/1010-nang-luong.htm", "Text": "Năng lượng", "ChangeClose": 0.38, "CloseIndex": 361.99, "SectionID":` | available | remote |
| vs_currency | [] | Reference FX table. Use as fallback FX source. | Bảng FX tham chiếu (dự phòng). | Vietstock GetCurrency | `{"rows": [{"Percent": "+0.04%", "Last": "1.12", "Css": "up"}, {"Percent": "-0.52%", "Last": "29,943.94", "Css": "dn"}, {"Percent": "-0.27%", "Last": "34,797.85"` | available | remote |
| vs_market_info | ['exchange'] | Per-exchange board row: index, breadth, put-through. Use for 5s snapshots in hours. exchange: HOSE, HNX or UPCOM (endpoint is per-exchange, not per-symbol). | 1 dòng/sàn: index, breadth, thỏa thuận (snapshot 5s trong giờ). | Vietstock /data/marketinfo {type 1/2/3} | `{"exchange": "HOSE", "rows": [{"exId": 1, "c": "VN-Index", "n": "Chỉ số VN Index", "e": "HOSE", "p": 1739.61, "ch": -9.69, "pch": -0.55, "vol": 193007672, "val"` | available | remote |
| vs_xnk_detail | ['direction', 'from_date'] | Import/export by country via browser-session replay. Use for trade structure. direction: 'xk' exports (cat 64), 'nk' imports (65). termType monthly, from_date default current year (ISO). | Xuất/nhập khẩu theo quốc gia, triệu USD (HAR-session replay). | Vietstock Macro listID 64/65 (HAR-session) | `{"direction": "xk", "category": 64, "term_type": 2, "rows": [{"name": "EU", "group": "EU", "period": "Tháng 1/2026", "year": "2026", "value": 5446.79, "unit": "` | available | remote |

## vn_ext.py — 11 tools (10 + alias `vn_crypto_ohlv`)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vn_index_ohlcv | ['symbol', 'count', 'summary', 'columns', 'interval'] | Index bars for VN tickers. | Nến chỉ số VN (VNINDEX/VN30...). | vnstock Market.index (VCI) | `{"symbol": "VNINDEX", "count": 5, "last": 1739.61, "high": 1788.0, "low": 1731.03}` | available | remote |
| vn_equity_ohlcv | ['symbol', 'count', 'summary', 'columns', 'interval'] | Nến qua Market API, thay thế quotes khi cần OHLCV. Dùng khi cần nến phút/intraday hoặc nguồn nến thứ hai để đối chiếu. | Nến cổ phiếu qua Market API; dùng cho intraday (1m/15m) hoặc nguồn nến thứ hai; từ chối mã chỉ số. | vnstock Market API (intraday; index bị từ chối) | `{"symbol": "VCB", "count": 5, "last": 57.3, "high": 58.5, "low": 57.2}` | available | remote |
| vn_futures_ohlcv | ['symbol', 'count', 'summary', 'columns', 'interval'] | Futures bars. Use for derivatives backtest input. interval: bar size ('1D' daily; intraday like '1m'/'15m' where supported). summary/columns: summary returns {count,last,high,low} only; columns keeps named fields. | Nến phái sinh (input backtest VN30F1M). | vnstock Market.futures | `{"symbol": "VN30F1M", "count": 5, "last": 1886.3, "high": 1937.0, "low": 1881.3}` | available | remote |
| vn_forex_ohlcv | ['pair', 'count', 'summary', 'columns'] | FX daily bars (Yahoo). | Nến FX liên ngân hàng theo ngày (Yahoo); không phải giá mua/bán ngân hàng. | yfinance FX history | `{"symbol": "USDVND", "count": 5, "last": 25959.0, "high": 26014.0, "low": 25929.0}` | available | remote |
| vn_crypto_ohlcv (+alias `vn_crypto_ohlv`) | ['symbol', 'count', 'summary', 'columns'] | Crypto bars. Use for digital-asset regime reads. summary/columns: summary returns {count,last,high,low} only; columns keeps named fields. | Nến crypto quy VND. | vnstock Market.crypto | `{"symbol": "BTCUSDT", "count": 5, "last": 2172149396.85, "high": 2225338114.99, "low": 2146590963.65}` | available | remote |
| vn_global_index | ['symbol', 'count', 'summary', 'columns'] | Global index daily bars (Yahoo). Use for one world index's history. | Nến chỉ số thế giới qua Yahoo (alias SPX/DJI/N225/HSI...); VN-Index dùng vn_index_ohlcv. | yfinance daily bars (aliases) | `{"symbol": "USA30", "count": 5, "last": 50926.56, "high": 51874.94, "low": 50546.54}` | available | remote |
| vn_reference | ['exchange', 'by', 'key'] | ICB reference by exchange, group or industry. Use for universe construction. by: 'exchange' (use exchange=HOSE/HNX/UPCOM), 'group' or 'industry' (use key=group/industry name). | Universe theo sàn/nhóm/ngành (source KBS, HOSE 757 mã). | vnstock Reference (KBS source, filter local) | `{"exchange": "HOSE", "rows": [{"symbol": "VID", "organ_name": "CTCP Đầu tư Phát triển Thương mại Viễn Đông", "en_organ_name": "Vien Dong Investment Development ` | available | remote |
| vn_company | ['symbol', 'detail'] | Hồ sơ, cổ đông và ban lãnh đạo công ty. Dùng khi nghiên cứu doanh nghiệp. Dùng khi: "FPT làm gì, ai là cổ đông lớn". | Vốn hóa, rating, holders, officers (chậm khi throttle). | vnstock Company (VCI→KBS) | `{"symbol": "VCB", "info": {"symbol": "VCB", "organ_code": "VCB", "current_price": 57600.0, "market_cap": 481286885414400.0, "issue_share": 8355675094, "tag": nu` | available | remote |
| vn_msn_fx_gold | ['symbols', 'days'] | USD/VND and world gold daily series (Yahoo). Use for gold-basis math. | USDVND liên ngân hàng + vàng COMEX GC=F futures (không phải spot XAUUSD); tính gold-basis. | yfinance: USDVND + GC=F | `{"series": [{"symbol": "USDVND", "points": 21, "last": {"time": "2026-09-30 00:00:00", "open": 25964.0, "high": 25975.0, "low": 25959.0, "close": 25959.0, "volu` | available | remote |
| vn_trades | ['symbol', 'limit', 'board', 'from_date', 'to_date'] | Tick-level matched trades. Use for microstructure reads. board: board filter (default all boards). from_date/to_date: ISO dates bounding the trade window. | Băng khớp lệnh tick-level live. | vnstock Market.equity.trades | `{"symbol": "VCB", "trades": [{"time": "2026-10-02 10:17:17", "price": 57.4, "volume": 500, "match_type": "buy", "id": "2026-10-02_101717_574000_500"}, {"time": ` | available | remote |

## yf.py — 3 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| yf_global_indices | ['tickers', 'period', 'interval'] | 9 global benchmarks. Use for overnight context. tickers: subset override (default GLOBAL 9). period/interval: yfinance spellings ('2d', '1wk', '1mo'... x '1d'/'1wk'). | 9 benchmarks thế giới (S&P, Nasdaq...). | yfinance GLOBAL_9 (worker pump TTL 300s) | `{"indices": [{"ticker": "^GSPC", "price": 7666.4501953125, "prev": 7651.5400390625}, {"ticker": "^IXIC", "price": 26871.595703125, "prev": 26861.060546875}, {"t` | available | remote |
| yf_commodities | ['tickers', 'period', 'interval'] | Gold, oil, metals, BTC, VND and dollar index. Use for input-cost context. tickers: subset override (default COMMO 13). period/interval: yfinance spellings. | Vàng/dầu/kim loại/BTC/VND/DXY (giá đầu vào). | yfinance COMMO_13 | `{"items": [{"ticker": "GC=F", "price": 4200.60009765625, "prev": 4186.7001953125}, {"ticker": "SI=F", "price": 61.26499938964844, "prev": 60.097999572753906}, {` | available | remote |
| yf_yield_curve | [] | US 2Y/10Y and inversion flag. Use for rates and regime context. Falls back to FRED DGS10/DGS2 when yfinance is blocked (datacenter IPs). | Lợi suất US 2Y/10Y + cờ đảo ngược (chế độ rates). | yfinance ^TNX + 2YY=F | `{"us10y": 0.052369999885559085, "us2y": 0.046100001335144046, "inverted": false}` | available | remote |

## yf_world.py — 6 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| yf_world_indices | ['tickers'] | 24 world benchmarks. Use for global breadth. tickers: subset override (default WORLD 24). | 24 benchmarks (độ rộng toàn cầu). | yfinance batch download | `{"indices": [{"ticker": "^GSPC", "price": 7666.4501953125, "prev": 7651.5400390625}, {"ticker": "^IXIC", "price": 26871.595703125, "prev": 26861.060546875}, {"t` | available | remote |
| yf_oracle_markets | ['groups'] | 40 markets in 6 groups with 30d stats. Use for cross-asset state. groups: keep only named groups (crypto/metals/energy/agri/bonds_fx/index). | 40 thị trường/6 nhóm + stats 30d. | yfinance ~40 tickers 1mo | `{"crypto": [{"ticker": "BTC-USD", "price": 85271.9765625, "chg_30d": 10.31, "high30": 86602.9141, "low30": 75612.5078}, {"ticker": "ETH-USD", "price": 2715.4699` | available | remote |
| yf_regime_assets | [] | 7 regime drivers with 2y history. Use for RISK-ON/OFF calls. | 7 tài sản dẫn dắt chế độ + lịch sử 2y (RISK-ON/OFF). | yfinance 2y + rule classify local | `{"^GSPC": {"last": 7666.4501953125, "chg_1y_pct": 14.23}, "^VIX": {"last": 16.389999389648438, "chg_1y_pct": -1.56}, "DX-Y.NYB": {"last": 101.99299621582031, "c` | available | remote |
| yf_mega_flows | ['top_n'] | Mega-cap leader flows. Use to follow global smart money. top_n: leaders evaluated (default 15 of the ~20-name universe). | Dòng tiền mega-cap (AAPL/MSFT/NVDA...). | yfinance mega-cap 15 + screener | `{"universe": "mega-cap leaders", "leaders": [{"ticker": "AAPL", "price": 330.32000732421875, "prev": 333.0199890136719}, {"ticker": "MSFT", "price": 512.7999877` | available | remote |
| yf_alloc_history | ['asset', 'timeframe'] | Long allocation history per asset. Use for regime backtests. asset: GC/VND/BTC/OIL/SILVER/COFFEE (unknown falls back to GC). timeframe: '1d' or '1wk'; returns last 60 closes over 5y. | Lịch sử phân bổ 5y theo tài sản (backtest chế độ). | yfinance 5y | `{"asset": "GC", "ticker": "GC=F", "points": [{"t": "2026-07-09", "c": 4140.7998}, {"t": "2026-07-10", "c": 4113.7002}, {"t": "2026-07-13", "c": 4005.7}, {"t": "` | available | remote |
| yf_market_pins | [] | 5-day pins for world majors plus VN watchlist. Use for brief headers. | Neo 5 ngày + sparkline (tiêu đề brief). | yfinance world majors + VN watchlist | `{"world": [{"ticker": "^GSPC", "last": 7666.4502, "spark": [7743.4102, 7683.6899, 7670.8398, 7651.54, 7666.4502]}, {"ticker": "^IXIC", "last": 26871.5957, "spar` | available | remote |

## dnse_tools.py — 4 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| dnse_ohlc_history | ['symbol', 'resolution', 'bar_type', 'from_date', 'summary', 'columns', 'to_date', 'page_size'] | Paginated futures/index bars via cursor. | Nến futures/index phân trang bằng cursor (37k+ bars). | DNSE REST /price/ohlc (HMAC key) | `{"symbol": "VN30F1M", "count": 37748, "last": 1888, "high": 2115.7, "low": 560.1}` | available | remote |
| dnse_latest_trade | ['symbols', 'summary', 'columns'] | Latest match price and totals per symbol. | Giá khớp mới nhất theo mã (fallback realtime). | DNSE REST /price/{s}/trades/latest | `{"count": 1, "symbols": ["VN30F1M"]}` | available | remote |
| dnse_foreign_flow | [] | Mua/bán ròng khối ngoại TRÊN HỢP ĐỒNG TƯƠNG LAI VN30F1M từ cache WS. Scope là VN30F1M (futures), KHÔNG phải dòng ngoại toàn thị trường — DNSE WS chỉ subscribe kênh foreign cho symbol này (issue #38). | NN mua/bán ròng từ WS cache — cần worker local. | DNSE WS qua Redis (cần worker) | `{"tool": "dnse_foreign_flow"}` | unavailable | remote |
| dnse_ws_snapshot | ['symbols'] | Raw worker snapshot for symbols. Use to debug realtime staleness. symbols: channels to read (None reads VN30F1M+VNINDEX+VN30). | Snapshot WS thô để debug realtime — cần worker. | Redis mcp:market:dnse_ws_snapshot (cần worker) | `{"tool": "dnse_ws_snapshot"}` | unavailable | remote |

## dnse_ext.py — 5 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| dnse_orderbook | ['symbol', 'depth'] | Bid/ask depth. Use for microstructure reads. depth: levels per side (default 3; HOSE publishes 3, HNX/UPCoM/futures up to 10). | Depth bid/ask (futures rỗng ngoài giờ là đúng). | DNSE REST quotes/latest → /quotes | `{"symbol": "VCB", "bids": [], "asks": []}` | available | remote |
| dnse_indices | ['symbols'] | Index snapshots from WS cache. Use for live index reads. symbols: index channels to read (default VNINDEX+VN30). | Snapshot chỉ số từ WS cache — cần worker. | DNSE WS market_index Redis (cần worker) | `{"tool": "dnse_indices"}` | unavailable | remote |
| dnse_vn30f1m_live | ['bars'] | VN30F1M 1m bars aggregated to 15m with session remap. Use for intraday. bars: keep only the most recent N aggregated 15m bars. | Nến 1m gộp 15m, remap phiên 14:30→14:45. | DNSE REST 1m → local agg 15m remap | `{"symbol": "VN30F1M", "tf": "15m", "bars": [{"t": 1790907300, "o": 1897, "h": 1899.4, "l": 1894, "c": 1896.9, "v": 12674}, {"t": 1790908200, "o": 1896.9, "h": 1` | available | remote |
| dnse_working_dates | ['year'] | Lịch ngày giao dịch thực tế. Dùng khi lập kế hoạch phiên (ngày nào được giao dịch). Dùng khi: "thứ bảy có giao dịch không", "tháng này bao nhiêu phiên", kiểm tra ngày nghỉ lễ. | Lịch giao dịch (lên kế hoạch phiên). | DNSE REST /market/working-dates | `{"dates": {"workingDates": ["2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-` | available | remote |
| exchange_calendar | [] | Giờ HOSE/HNX/UPCoM, ATO/ATC, thanh toán T+2. Dùng khi hỏi cơ chế phiên. Dùng khi: "ATO là gì", "mấy giờ đóng cửa", "tỷ lệ ký quỹ bao lâu mới nhận tiền". | Giờ HOSE/HNX/UPCOM, ATO/ATC, T+2 (tĩnh). | static local (không mạng) | `{"sessions": [{"days": "Mon-Fri", "open": "09:00", "close": "15:00", "ato": "09:00-09:15", "atc": "14:30-14:45"}], "settlement": "T+2", "timezone": "Asia/Ho_Chi` | available | remote |

## crypto.py — 2 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| crypto_spot | ['symbols'] | Binance spot 24h tickers. Use for crypto price and volume reads. symbols: up to 10, any of BTCUSDT / BTC/USDT / btc-usdt spellings. | Spot Binance 24h, không key (BTC 83,476...). | Binance public /ticker/24hr (không key) | `{"tickers": [{"symbol": "BTCUSDT", "last": 85278.01, "change_pct": 2.11, "high": 85511.0, "low": 83186.0, "volume": 17780.18956, "quote_volume": 1497492624.8471` | available | remote |
| crypto_derivs | ['symbols'] | Binance futures funding, OI and long/short ratios. Use for leverage reads. symbols: up to 5 perpetual symbols (BTCUSDT ...). | Funding/OI/long-short ratio futures (đọc đòn bẩy). | Binance fapi funding/OI/LSR (không key) | `{"derivs": [{"symbol": "BTCUSDT", "mark_price": 85246.55378986, "funding_rate": 3.869e-05, "next_funding_time": 1790928000000, "open_interest": 98109.581, "ls_r` | available | remote |

## scan.py — 6 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| stock_screener | ['filters', 'max_pe', 'min_roe', 'limit', 'technical'] | Sàng danh sách mã theo định giá và chất lượng; metric cơ bản chỉ tra tối đa 30 mã. Dùng khi: "lọc cổ phiếu PE<10 ROE>15%", tìm mã theo điều kiện. | Lọc 1522 mã 3 stages (universe→fundamentals→technical). | vnstock listing + fundamentals + local filters (3 stages) | `{"universe": 1523, "filters": {}, "candidates": [{"symbol": "DPP", "name": "CTCP Dược Đồng Nai"}, {"symbol": "SDA", "name": "CTCP Simco Sông Đà"}, {"symbol": "C` | available | remote |
| signals_screener_columns | ['group', 'search'] | Screener column catalog (valuation/quality/universe/price). Use to build filters. group: keep only that column group; search: keep columns whose key or label contains this substring (case-insensitive). | Catalog cột lọc để build filters. | local catalog | `{"count": 2, "group": "valuation", "search": null, "columns": {"pe": {"group": "valuation", "desc": "Price / trailing earnings (P/E). Lower is cheaper."}, "mark` | available | remote |
| signals_technical | ['symbol', 'interval', 'indicators', 'ichimoku_convention'] | Chấm kỹ thuật đầy đủ từ nến local trên 1D/1W/1M. Dùng khi chọn thời điểm vào lệnh cho 1 mã. | Technicals đầy đủ + RS/pos_52w/sma150/patterns/Hỗ trợ-kháng cự + Ichimoku/swing/fibo/Elliott/Wyckoff (P17); `ichimoku_convention` = offset25 (mặc định) / classic26. | vnstock candles (250d) → pandas technicals local | `{"symbol": "VCB", "interval": "1D", "rsi14": 39.23, "stoch_k": 2.63, "stoch_d": 4.8, "cci20": -125.54, "adx14": 12.12, "macd": {"line": -0.3102, "signal": -0.13` | available | remote |
| sector_performance | ['level', 'top_n'] | Dòng heatmap GICS. Dùng khi đọc luân chuyển ngành (ngành nào đang khỏe). Dùng khi: "ngành nào đang khỏe", so hiệu suất các ngành. | Heatmap GICS (đọc luân chuyển ngành). | Vietstock GetHeatmapGICS | `{"level": 1, "rows": [{"IndustryCode": 10, "ParentCode": 0, "Level": 1, "DisplayOrder": 0, "IndustryName": "Năng lượng", "StockFullName": null, "ImageURL": "/c` | available | remote |
| money_flow | ['symbols'] | Tổng hợp dòng ngoại: DNSE WS trước, Vietstock đối chiếu sau. Dùng khi đọc smart money tổng hợp. | NN mua/bán: DNSE WS → Vietstock cross-check. | DNSE WS → Vietstock nn_chart → unavailable | `{"primary": "vietstock", "flow": [["/Date(1790911058990)/"], [{"TradingDate": "/Date(1788714000000)/", "BuyVol": 46533428, "BuyVal": 1813.559809, "SellVol": 651` | available | remote |
| alert_check | ['rules'] | Evaluate price/RSI rules against live quotes. Use for live watch. Each rule: {symbol, threshold, metric ('price'\|'rsi14'), op ('>'\|'gt'\|'>='\|'gte'\| '<'\|'lt'\|'<='\|'lte'\|'cross_up'\|'cross_down')}. | Đánh giá rules giá/RSI trên quotes live. | vnstock quote/candles + Redis cross-state | `{"rules": 1, "evaluated": 1, "triggered": [{"symbol": "VCB", "metric": "price", "price": 57300.0, "op": ">", "threshold": 50.0}]}` | available | remote |

## compute_financial.py — 7 tools (tách từ compute.py, behavior giữ nguyên)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| stock_forensic | ['symbol', 'detail', 'periods_n'] | Kiểm tra chất lượng lợi nhuận từ các báo cáo năm cùng kỳ và cùng pháp nhân. Beneish 8 biến theo bản CFO 2013; Piotroski 9 tín hiệu, turnover dùng assets đầu năm (§2.3.3). | Beneish 8 biến (CFO 2013) + Piotroski 9 tín hiệu từ BCTC năm cùng kỳ/cùng pháp nhân; M có thể partial khi thiếu input. | Vietstock detail statements → Beneish/Piotroski local | `{"symbol": "FPT", "dsri": 0.9772, "gmi": 1.0961, "aqi": 1.0107, "sgi": 1.1049, "sgai": 0.9951, "lvgi": 1.1257, "tata": 0.0349, "m_score": -2.0589, "m_partial": ` | available | remote |
| valuation_run | ['symbol', 'btype', 'method'] | Ensemble PER/PB. Dùng khi cần vùng giá trị hợp lý của 1 mã. Dùng khi: "FPT đáng giá bao nhiêu", vùng mua an toàn. | PER/PB ensemble; EPS/BVPS lấy quý mới nhất (4 quý gần nhất) trước, fallback financeinfo; method map theo btype. | Vietstock financeinfo (EPS/BVPS TTM) + quote → per_pb/pb_bank_broker local | `{"symbol": "VCB", "price": 57400.0, "method": "per_pb"}` | available | remote |
| financial_statements | ['symbol', 'period', 'statement', 'periods_n'] | Alias đọc BCTC (tương thích v3). Dùng khi đọc BCTC nhanh gọn, không cần JWT. Dùng khi: "báo cáo KQKD 4 quý gần nhất của FPT", đọc statement nhanh. | Alias đọc BCTC nhanh (wrap financeinfo mirror). | vs_financeinfo mirror (alias v3) | `{"symbol": "VCB", "period": "quarter", "pages": "Q2/2025 ..."}` | available | remote |
| financial_ratios | ['symbol', 'set', 'period', 'peers'] | Bảng chỉ số tài chính theo kỳ (Vietstock). Dùng khi soi chỉ số tài chính của 1 mã qua các năm/quý (kèm peers tuỳ chọn). | Bảng chỉ số theo kỳ từ financeinfo Vietstock; EPS TTM 4 quý; quý là số riêng quý cho ROE/ROA/margin; `set` lọc item. | Vietstock financeinfo (BCTC) → local ratio table | `{"symbol": "VCB", "period": "year", "ratios": {"data": [{"StockCode": "VCB", "TradingDate": "/Date(1790874000000)/", "ClosePrice": 57300, "ColorID": -1, "Change` | available | remote |
| peer_compare | ['symbol', 'peers', 'metrics'] | So sánh head-to-head chỉ số tài chính giữa các mã. Dùng khi chọn giữa vài ticker cùng ngành. | So trực tiếp tối đa 6 mã. | overview batch (cap 6) | `{"rows": [{"symbol": "VCB", "data": [{"StockCode": "VCB", "TradingDate": "/Date(1790874000000)/", "ClosePrice": 57300, "ColorID": -1, "Change": -300, "PerChange` | available | remote |
| stock_overview | ['symbol'] | Thông tin giao dịch + hồ sơ công ty gộp một lần. Dùng khi cần dossier nhanh về 1 mã. Dùng khi: lần đầu xem 1 mã (giá + công ty làm gì). | Hồ sơ nhanh 1 mã (trading info + profile). | vs_trading_info + vs_overview + vn_company | `{"trading": {"StockCode": "VCB", "TradingDate": "/Date(1790911060003)/", "KLCPLH": 8355675094, "KLCPNY": 8355675094, "PriorClosePrice": 57600, "CeilingPrice": 6` | available | remote |
| company_events | ['symbol', 'types'] | Classified disclosures and corporate actions. Use for event calendars. types: comma-separated kinds to keep, matched against kind/type fields (e.g. | Sự kiện phân loại từ công bố. | vs_documents + company (classify local) | `{"symbol": "VCB", "events": [{"FileExt": ".pdf ", "UpdateTime": null, "TotalRow": 487, "FileInfoID": 559412, "Url": "https://static2.vietstock.vn/data/HOSE/2026` | available | remote |

## compute_intel.py — 7 tools (tách từ compute.py, behavior giữ nguyên)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| fred_series | ['series_id', 'limit', 'spark'] | FRED observations. Use for US macro context. series_id like 'DGS10'; spark adds a value-only sparkline list. | Chuỗi FRED (bối cảnh macro Mỹ, cần key). | FRED API (FRED_API_KEY) | `{"series": "DGS10", "points": [{"t": "2026-09-30", "v": "5.29"}, {"t": "2026-09-29", "v": "5.26"}, {"t": "2026-09-28", "v": "5.24"}]}` | available | remote |
| world_macro_country | ['iso3', 'indicator', 'limit'] | WorldBank series per country. Use for global GDP/CPI/debt context. iso3: 3-letter country code (VNM/USA); indicator like 'NY.GDP.MKTP.KD.ZG'. limit caps returned points. | Chuỗi WorldBank theo quốc gia (GDP/CPI/nợ). | WorldBank API v2 | `{"country": "VNM", "indicator": "NY.GDP.MKTP.KD.ZG", "points": [{"t": "2025", "v": 8.01882998978245}, {"t": "2024", "v": 7.03955197123018}, {"t": "2023", "v": 4` | available | remote |
| world_fear_greed | ['limit'] | Crypto fear/greed index. Use for risk-appetite reads. limit: number of recent daily readings returned. | Chỉ số sợ hãi/tham lam crypto (đọc risk-appetite). | alternative.me API | `{"series": [{"t": "1790899200", "v": "72", "label": "Greed"}, {"t": "1790812800", "v": "74", "label": "Greed"}, {"t": "1790726400", "v": "71", "label": "Greed"}` | available | remote |
| sentiment_score | ['symbol', 'limit'] | Điểm tâm lý đám đông từ bài Fireant, chấm bằng Groq. Dùng khi đo rủi ro hype quanh 1 mã. Dùng khi: "cổ phiếu này có đang bị thổi phồng không", độ nóng cộng đồng. | Sentiment đám đông từ Fireant (Groq chấm, fallback heuristic). | Fireant posts → Groq (fallback heuristic likes) | `{"symbol": "VCB", "posts": 3, "score_heuristic": -0.25}` | available | remote |
| event_stats | ['query', 'limit'] | GDELT event aggregates for a query. Use for base-rate checks. | Aggregate GDELT (base-rate, không trùng article list geo_intel). | GDELT API (cache 600s, retry 1) | `{"query": "vietnam", "articles": [{"title": "ĐT Việt Nam chuẩn bị sẵn sàng cho trận đại chiến ĐT Thái Lan", "url": "http://vov.vn/the-thao/dt-viet-nam-chuan-bi-` | available | remote |
| compare_assets | ['assets', 'timeframe'] | Cross-asset last prices via yfinance. Use for allocation reads. assets: yfinance tickers (max 10). timeframe: '1d' (2d/1d), '1wk' (3mo/1wk), '1mo' (1y/1d) download window. | Giá chéo tài sản qua yfinance. | yfinance batch | `[{"ticker": "GC=F", "price": 4198.2998046875, "prev": 4186.7001953125}, {"ticker": "BTC-USD", "price": 85203.9375, "prev": null}]` | available | remote |
| insider_trading | ['symbol', 'limit'] | Giao dịch nội bộ qua vnstock Company. Dùng khi đọc dòng tiền người trong cuộc. Dùng khi: "ban lãnh đạo có mua/bán cổ phiếu không", kiểm tra informed flow. | Giao dịch nội bộ (rỗng = không có, đúng data). | vnstock Company VCI→KBS | `{"symbol": "VCB", "deals": []}` | available | remote |

## compute_infra.py — 6 tools (tách từ compute.py, behavior giữ nguyên)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| signals_scan | ['universe', 'exchange', 'max_symbols'] | Donchian-20d breakout scan. Use to hunt momentum across the market. | Quét breakout Donchian-20d (0 hits = không có, đúng). | vn_reference pool + quote_history từng mã → Donchian local | `{"hits": [], "scanned": 3, "requested": 3}` | available | remote |
| pattern_match | ['symbol', 'lookback', 'limit'] | Self-similarity of return windows by correlation. Use for analogies. lookback: daily closes fetched (window is last 20 bars). limit: top-N matches by correlation (best_* fields describe rank 1). | Quá khứ giống hiện tại bằng tương quan (analogy). | vnstock candles → correlation local | `{"symbol": "VCB", "best_corr": 0.379, "offset_bars": 30, "matches": [{"corr": 0.379, "offset_bars": 30}, {"corr": 0.323, "offset_bars": 29}]}` | available | remote |
| snapshot_history | ['kind', 'days'] | Daily-snapshot history saved by the worker. | Lịch sử snapshot ngày do worker lưu (data hay mất). | PG daily_snapshots (worker 17:15 VN) | `{"kind": "macro_curated", "count": 2, "rows": [{"date": "2026-10-02", "kind": "macro_curated", "payload": {"fx55_t1": {"rows": [{"name": "Tỷ giá trung tâm (từ 0` | available | remote |
| runs_list | ['id'] | Local run registry. Use to resume analysis sessions. id: filter by run id substring; use run_get for one full run. | Registry runs local (trống = chưa chạy, đúng). | data/runs.jsonl local | `{"runs": []}` | empty | remote |
| run_get | ['run_id'] | Local run registry fetch. Use to inspect past outputs. run_id: exact id from runs_list output. | Đọc 1 run đã lưu. | data/runs.jsonl local | `{"run_id": "x"}` | empty | remote |
| doctor | [] | Local self-check: env keys present, package versions. Use before handoff. | Self-check env keys + versions. | local env + package versions | `{"mcp_sdk": "1.x", "vietstock_jwt": true, "dnse_keys": true, "redis": true, "database": true, "fred": true, "groq": true, "fireant": true}` | available | remote |

## corp.py — 9 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| dividends_splits | ['symbol', 'region', 'limit'] | Cổ tức tiền mặt và phát hành/tách cổ phiếu. Dùng khi xem lịch sử trả thưởng của 1 mã. Dùng khi: "FPT đã chia cổ tức những năm nào". | Cổ tức tiền mặt + phát hành/tách (lịch sử chi trả). | vnstock Company.events → yfinance actions (world) | `{"symbol": "VCB", "region": "vn", "events": [{"event_code": "DIV", "title": "Cash Dividend - Year 2025 - 450 VND", "exright_date": "2026-07-23T00:00:00", "recor` | available | remote |
| holders | ['symbol', 'region', 'kind'] | Shareholder and institutional holder tables. | Bảng cổ đông/tổ chức (sở hữu). | vnstock shareholders → yfinance holders (world) | `{"symbol": "VCB", "region": "vn", "kind": "all", "holders": [{"symbol": "VCB", "share_holder": "Ngân Hàng Nhà Nước Việt Nam", "quantity": 6250338579, "share_own` | available | remote |
| event_calendar_vn | ['event', 'symbol', 'limit'] | Lịch sự kiện doanh nghiệp của Vietstock. Dùng khi cần ngày cổ tức/niêm yết/họp theo lịch. Dùng khi: "khi nào FPT chia cổ tức", "lịch họp ĐHĐCĐ". | Lịch cổ tức/niêm yết/ĐHĐCĐ Vietstock. | Vietstock /data/eventstypedata | `{"event": "dividends", "symbol": "VCB", "events": [{"event_id": 223751, "code": "VCB", "note": "Trả cổ tức  năm 2025  bằng tiền, 450 đồng/CP", "ex_date": "2026-` | available | remote |
| block_trades | ['symbol', 'from_date', 'to_date', 'limit'] | Tách khớp lệnh và thỏa thuận theo ngày. Dùng khi đọc dòng tiền thỏa thuận (dark-pool) của 1 mã. | Tách khớp lệnh vs thỏa thuận theo ngày (đọc dòng tiền lớn). | Vietstock /data/gettradingresult (MT vs PT) | `{"symbol": "VCB", "days": [{"date": "2026-10-02", "close": 57300, "mt_vol": 886900, "mt_val": 50930200000.0, "pt_vol": 0, "pt_val": 0.0, "pt_pct": 0.0}, {"date"` | available | remote |
| analyst_consensus | ['symbol', 'limit', 'report_type', 'days'] | Khuyến nghị và giá mục tiêu của CTCK, tách từ tiêu đề báo cáo. Dùng khi xem quan điểm phố (street views) về 1 mã hoặc toàn thị trường. | Rating + target từ titles (rỗng = không báo cáo mới); report_type=macro lọc báo cáo vĩ mô CTCK (entry section/report); `days` giữ báo cáo N ngày gần nhất, dòng không tách được ngày có `date_uncertain`. | scrape Vietstock /bao-cao-phan-tich (titles parse) | `{"symbol": "VCB", "reports": []}` | available | remote |
| ipo_calendar_vn | [] | HNX auction calendar plus announcement fallback. Use for upcoming supply. Calendar is often empty (no scheduled auctions); announcements carry the latest auction news with dates. | Lịch đấu giá HNX + thông báo (thường rỗng, đúng). | scrape HNX lich-dau-gia + tin-cong-bo | `{"auctions": [], "announcements": [{"posted": "23/09/2026 16:29", "title": "Không tổ chức bán đấu giá theo lô cổ phần của Tổng công ty Thủy sản Việt Nam - CTCP ` | available | remote |
| futures_basis | [] | VN30F1M price minus VN30 spot. Use for premium/discount reads. DNSE exposes no open-interest field, so no OI is reported; basis_bps is (futures-spot)/spot in basis points. | F1M − VN30 spot (premium/discount, fallback ohlc). | DNSE latest_trade/ohlc − vnstock VN30 spot | `{"futures": 1888.0, "spot": 1882.11, "basis": 5.89, "basis_bps": 31.3}` | available | remote |
| planned_targets | ['symbol', 'years'] | Business-plan targets (CTKH: planned revenue/profit by year). Use as expectation anchor. years: latest N plan years (unit VND billions). | Kế hoạch DT/LN năm của DN — neo kỳ vọng (P15 live). | Vietstock CTKH chain (session-gated) | `{"symbol": "FPT", "unit": "VNDbn", "years": [2025, 2026], "rows": [{"name": "Doanh thu kế hoạch", "planned_target_id": 5, "plan": {"2025": 75400.0, "2026": 5858` | available | remote |
| financial_detail | ['symbol', 'statement', 'periods_n'] | BCTC chi tiết đầy đủ, từng dòng mỗi kỳ. Dùng khi đọc sâu BCTC (soi từng chỉ tiêu). Dùng khi: phân tích forensic, kiểm tra dòng tiền/thuế/phải thu chi tiết. | FULL BCTC từng dòng theo kỳ (đọc sâu, P15 revive). | Vietstock /data/* chain object-array (permission filter) | `{"symbol": "FPT", "statement": "KQKD", "unit": "VNDbn", "periods": ["Q1/2026", "Q2/2026"], "rows": [{"norm_id": 2206, "name": "1. Doanh thu bán hàng và cung cấp` | available | remote |

## quant_backtest.py — 4 tools (tách từ quant.py + quant_shared.py engine chung, behavior giữ nguyên)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| quant_backtest | ['symbol', 'cost_bps', 'strategy', 'slippage_bps', 'benchmark'] | Backtest mua-giữ kèm chi phí trên lịch sử có sẵn. Dùng khi cần baseline so sánh. Dùng khi: baseline "nếu mua giữ 1 năm thì bao nhiêu". | Backtest buy-hold có phí (baseline). | vnstock candles → backtest local | `{"symbol": "VCB", "strategy": "buy_hold", "benchmark": "VNINDEX", "gross_return": -0.0687, "net_return": -0.0717, "bars": 285, "cost_bps": 10.0, "slippage_bps":` | available | remote |
| scenario_simulate | ['scenario', 'symbol', 'shock_pct'] | Đặt cú sốc giá lên giá đóng gần nhất rồi tính L/L mỗi 1000 cổ phiếu. Dùng khi đo khẩu vị rủi ro (sizing). | Shock giá → P/L trên 1000cp (cỡ vị thế). | vnstock candles → local | `{"scenario": "t", "symbol": "VCB", "last_close": 57.3, "shock_pct": -5.0, "shocked_price": 54.43, "pnl_per_1000_shares": -2870.0, "assumptions": ["linear shock,` | available | remote |
| backtest_strategies | ['symbol', 'strategy', 'fast', 'slow', 'cost_bps', 'rsi_low', 'rsi_high', 'months', 'quarters', 'condition_symbol', 'condition_rule', 'condition_lookback'] | Backtest theo quy tắc ngoài mua-giữ. Dùng khi so các quy tắc canh thời điểm trên 1 mã. Dùng khi: "nếu cắt MA50 có tốt hơn mua giữ không", kiểm định chiến lược giao cắt/seasonality. | Backtest sma/momentum vs buy-hold. | vnstock 365d → local engine | `{"symbol": "VCB", "strategy": "sma_cross", "fast": 10, "slow": 30, "cost_bps": 10.0, "trades": 6, "net_return": -0.0872, "max_drawdown": 0.2008, "win_rate": 0.3` | available | remote |
| param_sweep | ['symbol', 'strategy', 'fast_range', 'slow_range', 'cost_bps', 'months', 'quarters'] | Grid-search strategy lookbacks, ranked by net return. | Grid lookbacks ≤30 combos (chống overfit). | vnstock 365d → local grid (≤30 combos) | `{"symbol": "VCB", "strategy": "sma_cross", "combos_evaluated": 8, "ranked": [{"fast": 10, "slow": 20, "trades": 9, "net_return": 0.071, "max_drawdown": 0.142, "` | available | remote |

## quant_stats.py — 6 tools (tách từ quant.py, behavior giữ nguyên)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| quant_risk | ['returns', 'periods_per_year'] | Sharpe, sụt giảm tối đa và tỷ lệ thắng từ chuỗi lợi nhuận. Dùng khi chấm rủi ro một chiến lược/mô hình. | Sharpe/DD/win từ chuỗi lợi suất (cổng mô hình). | thuần local (returns input) | `{"sharpe_proxy": 12.8759, "max_drawdown": 0.005, "win_rate": 0.6667, "n": 3, "periods_per_year": 252}` | available | remote |
| quant_factors | ['symbol', 'lookback'] | Momentum, volatility and drawdown factors from candles. Use to expand features. lookback: daily closes fetched (20d factor windows fixed); also adds max_dd_full_pct over the full window. | Momentum/vol/DD từ nến (mở rộng features). | vnstock candles → local | `{"symbol": "VCB", "lookback": 60, "momentum_20d_pct": -1.21, "vol_20d_ann_pct": 15.44, "max_dd_20d_pct": -4.5, "max_dd_full_pct": 13.57}` | available | remote |
| correlation_matrix | ['symbols', 'days'] | Pairwise Pearson correlation of daily returns. Use for diversification reads. symbols: up to 8 tickers (same market). days: daily bars each. | Tương quan Pearson cặp mã (đa dạng hóa). | vnstock candles inner-join → local | `{"symbols": ["VCB", "HPG"], "common_dates": 91, "matrix": {"VCB": {"VCB": 1.0, "HPG": 0.5045}, "HPG": {"VCB": 0.5045, "HPG": 1.0}}, "date_note": "business-day w` | available | remote |
| seasonality | ['symbol', 'window'] | Rolling-window return stats per calendar month. Use for seasonal bias. window: trading days per window, 5-63 (21 ~= month). | Stats theo tháng (bias mùa vụ). | vnstock 400d → local buckets | `{"symbol": "VCB", "window": 21, "months": {"1": {"n": 22, "mean_pct": 4.67, "median_pct": -1.55, "hit_rate": 0.32, "best_pct": 33.8, "worst_pct": -5.48}, "2": {` | available | remote |
| portfolio_optimize | ['symbols', 'objective', 'days'] | Long-only weights by rule. Use for allocation starting points. objective: 'equal', 'inv_vol' (1/sigma), 'max_sharpe' (closed-form long-only heuristic, no scipy). days: daily bars each (max 8 symbols). | Tỷ trọng long-only (numpy, fallback equal). | vnstock candles → numpy-only local | `{"symbols": ["VCB", "HPG"], "objective": "max_sharpe", "weights": {"VCB": 0.5, "HPG": 0.5}, "common_dates": 156, "notes": ["long-only heuristic; rebalance and c` | available | remote |
| event_study | ['symbol', 'dates', 'window_before', 'window_after', 'benchmark'] | Abnormal returns around event dates vs benchmark. | CAR sự kiện (Tết/cổ tức/ĐHĐCĐ) so benchmark, nearest-day trong 3 phiên. | vnstock candles → local | `{"symbol": "VCB", "events": 1, "avg_car_pct": 0.25}` (live) | available | remote |
## brief.py — 8 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| brief_build | ['scope', 'date', 'calendars'] | Soạn bản tin sáng từ tin tức, chốt tâm lý và lịch. Dùng lúc mở đầu phiên hoặc khi user xin bản tin tổng hợp. | Brief sáng từ news+calendars (không odds). | fear_greed + Vietstock/GDELT news + categories + yf pins + `auth_status` live | `{"scope": "vn", "sections": {"world_pins": {"series": [{"t": "1790899200", "v": "72", "label": "Greed"}, {"t": "1790812800", "v": "74", "label": "Greed"}, {"t":` | available | remote |
| news_market | ['limit', 'sources'] | Tin thị trường: đọc Fireant trước, GDELT dự phòng. Dùng khi kiểm tra chất xúc tác chung của thị trường. | Tin thị trường: Fireant trước, GDELT fallback. | Fireant → GDELT (fallback trong tool) | `{"posts": [{"id": null, "user": null, "text": "Tổng thống Nga Vladimir Putin ngày 1.10 cảnh báo nguy cơ xung đột toàn cầu, kêu gọi phương Tây từ bỏ thế bá quyền` | available | remote |
| news_symbol | ['symbol', 'limit', 'sources'] | Tin về 1 mã: bài Fireant gắn mã đó, GDELT dự phòng. Dùng khi xác minh tin đồn về cổ phiếu cụ thể. | Tin theo mã: Fireant posts + GDELT fallback. | Fireant → GDELT (fallback trong tool) | `{"symbol": "VCB", "posts": [{"id": null, "user": null, "text": "Lãi suất Vietcombank hiện dao động từ 0,1-6%/năm. Khách hàng gửi 500 triệu đồng kỳ hạn 24 tháng ` | available | remote |
| economic_calendar | ['scope', 'limit'] | Danh mục series vĩ mô dùng thay lịch sự kiện. Dùng khi kiểm tra khả năng có dữ liệu (có series CPI/GDP nào không). | Catalog macro (proxy lịch sự kiện). | vs_categories (proxy catalogue) | `{"scope": "vn", "series": [{"category_id": 7, "name": "1. Tài khoản quốc gia (GDP)", "has_data": false}, {"category_id": 73, "name": "GDP danh nghĩa", "has_data` | available | remote |
| corporate_calendar | ['symbol', 'limit'] | Feed công bố thông tin thô dùng như sự kiện doanh nghiệp. Dùng khi quét cổ tức/họp cổ đông dạng feed thô. | Feed công bố thô (quét cổ tức/họp). | Vietstock GetDocument | `{"symbol": "VCB", "docs": [{"FileExt": ".pdf ", "UpdateTime": null, "TotalRow": 487, "FileInfoID": 559412, "Url": "https://static2.vietstock.vn/data/HOSE/2026/N` | available | remote |
| sbv_rates | [] | Nguồn lãi suất điều hành và liên ngân hàng SBV, trang tĩnh scrape. Dùng khi xem chế độ lãi suất. | Lãi suất điều hành + liên NH (scrape SBV). | scrape sbv.gov.vn (static) | `{"policy": [{"name": "Lãi suất tái chiết khấu", "value": "3,000%"}, {"name": "Lãi suất tái cấp vốn", "value": "4,500%"}], "interbank": [], "as_of": null}` | available | remote |
| macro_events_vn | [] | Danh sách công bố của Tổng cục Thống kê kèm ngày tham chiếu và ngày tới. Dùng khi lập lịch dữ liệu vĩ mô. | Lịch công bố NSO + ngày tham chiếu/kế tiếp. | scrape nso.gov.vn (releases) | `{"releases": [{"indicator": "CPI", "title": "Chỉ số giá tiêu dùng (CPI), chỉ số giá vàng và chỉ số giá đô la Mỹ tháng Tám và 8 tháng năm 2026", "url": null, "re` | available | remote |
| fireant_thread | ['post_id', 'limit'] | Một bài Fireant kèm replies. Dùng khi đọc luồng bình luận đằng sau bài nóng. Dùng khi: "dân Fireant đang bàn gì về FPT", cần tâm lý đám đông chi tiết. | Đọc post + replies Fireant (rumor nằm ở replies). | Fireant REST (`/posts/{id}` + `/replies`) | `{"reply_count": 2}` (live PNJ post) | available | remote |

## intel.py — 7 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| world_prediction_odds | ['query', 'limit', 'tag'] | Polymarket odds via jina proxy to Gamma, then direct. Use for Fed/macro odds. query: substring in title/slug/description. tag: Polymarket tag (e.g. | Odds Polymarket (outcomes+prob, sort vol24h). | Gamma API qua jina proxy → direct | `{"source": "https://r.jina.ai/https://gamma-api.polymarket.com", "events": [{"title": "Steelers vs. Browns", "slug": "nfl-pit-cle-2026-10-02", "tags": ["Sports"` | available | remote |
| polymarket_event | ['slug'] | One Polymarket event detail by slug (every market + odds). Use to drill in. slug: from world_prediction_odds rows. | Chi tiết 1 event theo slug (mọi market + odds). | Gamma /events?slug (outcomes/prices) | `{"slug": "nfl-pit-cle-2026-10-02", "title": "Steelers vs. Browns", "description": "In the upcoming NFL game, scheduled for October 1 at 8:15PM ET:\nIf Steelers ` | available | remote |
| geo_intel | ['topic', 'limit', 'days', 'military'] | Geopolitical coverage via GDELT (politics-filtered) or military ADS-B flights. | Tin địa chính trị qua GDELT (đã lọc thể thao/nhiễu) + aggregate; military=true trả máy bay quân sự live (count/by_country/by_type/near_zone/lost). | GDELT API (cache 600s) / adsb.lol /v2/mil (không key) | `{"query": "Vietnam", "articles": [{"title": "ĐT Việt Nam chuẩn bị sẵn sàng cho trận đại chiến ĐT Thái Lan", "url": "http://vov.vn/the-thao/dt-viet-nam-chuan-bi-` | available | remote |
| assets_rotation | [] | Cross-asset 1y momentum classes into RISK-ON/OFF. Use for allocation reads. | Momentum 1y → RISK-ON/OFF (phân bổ). | yfinance 2y → rule local | `{"regime": "neutral/mixed", "signals": ["equities momentum up", "crypto negative (risk-off lean)"], "drivers": {"^GSPC": {"last": 7666.4501953125, "chg_1y_pct":` | available | remote |
| compare_equities | ['symbols', 'metrics'] | Head-to-head overview rows and momentum. Use when picking tickers. metrics: keep only matching row keys (symbol column always kept). | Overview + momentum head-to-head (chọn mã). | vs_overview + vn quote batch | `{"rows": [{"symbol": "VCB", "quote": {"symbol": "VCB", "time": 1790911726385, "exchange": "HOSE", "ceiling_price": 61600, "floor_price": 53600, "reference_price` | available | remote |
| evidence_bundle | ['claim_ids', 'calc_ids'] | Lock weighted conclusion by evidence bundle. Use last for final verdict. claim_ids: claim ids to lock; calc_ids: supporting calculation ids (pass [] when none). | Khóa kết luận có trọng số (dùng cuối để verdict). | local (claims/calc ids) | `{"claims": ["c1"], "calc_ids": [], "locked": true, "note": "bundle closes server-side; attach calc ids at synthesis"}` | available | remote |
| oracle_meta | [] | Aggregator snapshot plus source health. Use for dashboard meta. | Snapshot aggregator + sức khỏe nguồn. | yf pins + source_status | `{"pins": {"world": [{"ticker": "^GSPC", "last": 7666.4502, "spark": [7743.4102, 7683.6899, 7670.8398, 7651.54, 7666.4502]}, {"ticker": "^IXIC", "last": 26871.59` | available | remote |

## watchlist.py — 12 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| watchlist_create | ['name'] | Create a named watchlist. Use to start tracking a symbol group. | Tạo watchlist theo tên (PG unique guard). | PG opentrading_mcp → fallback file JSON | `{"id": 1, "name": "tmp-full135", "symbols": []}` | available | remote |
| watchlist_list | [] | List all watchlists with their symbols. Use to recall tracking state. | Liệt kê watchlists + mã. | PG/file | `{"watchlists": [{"id": 1, "name": "tmp-full135", "symbols": [null]}]}` | available | remote |
| watchlist_get | ['list_id'] | Get one watchlist's symbols by id. Use before quoting a saved set. | Lấy mã 1 watchlist theo id. | PG/file | `{"id": 1, "name": "tmp-full135", "symbols": [null]}` | available | remote |
| watchlist_add | ['list_id', 'symbols'] | Add symbols (deduped, uppercase) to a watchlist. Use to track more. | Thêm mã (dedupe, uppercase). | PG/file (dedupe, uppercase) | `{"list_id": 1, "added": 1, "symbols": ["VCB"]}` | available | remote |
| watchlist_remove | ['list_id', 'symbols'] | Remove symbols from a watchlist. Use to trim tracking. | Bớt mã khỏi watchlist. | PG (transaction, không fallback) | `{"list_id": 1, "symbols": []}` | available | remote |
| watchlist_delete | ['list_id'] | Delete a watchlist and its items (cascade). Use to clean up. | Xóa watchlist + items (cascade). | PG/file (cascade) | `{"deleted": 1}` | available | remote |
| watchlist_update | ['list_id', 'name'] | Rename a watchlist. Use sparingly; names are unique labels. | Đổi tên watchlist. | PG/file | `{"id": 1, "name": "tmp-full135b", "symbols": ["VCB"]}` | available | remote |
| alert_create | ['symbol', 'op', 'threshold', 'metric'] | Create a stored alert rule (input to alert_check). Use for live watch. metric: 'price' or 'rsi14'. op: '>'/'>='/<'/'<=' (aliases 'gt'/'gte'/ 'lt'/'lte' accepted). threshold: comparison value for the metric. | Tạo rule alert (input cho alert_check). | PG/file (validate op) | `{"symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": true, "id": 1}` | available | remote |
| alert_list | [] | List stored alert rules (active and paused). Use before alert_check. | Liệt kê rules (active + paused). | PG/file | `{"rules": [{"id": 1, "symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": true}]}` | available | remote |
| alert_delete | ['rule_id'] | Delete a stored alert rule by id. Use to clean up alerts. | Xóa rule theo id. | PG/file | `{"deleted": 1}` | available | remote |
| alert_pause | ['rule_id'] | Pause a stored alert rule (active=false). Use to silence alerts. | Tạm dừng rule. | PG/file (active=false) | `{"id": 1, "symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": false, "state": "paused"}` | available | remote |
| alert_resume | ['rule_id'] | Resume a paused alert rule (active=true). Use to re-enable alerts. | Bật lại rule. | PG/file (active=true) | `{"id": 1, "symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": true, "state": "resumed"}` | available | remote |

## cycle_stats.py — 9 tools (PG-backed, thêm 2026-10-10)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| cycle_stats_check | [] | Staleness of cycle-stats tables. No fetch. Use first when locating market phase. | Độ mới bảng cycle: số dòng, ngày cập nhật gần nhất, version; không gọi mạng. | PG `cycle_*` + `cycle_meta` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_seasonality | ['basket', 'month'] | Month seasonality per basket from the stored table (mean/hit/relative vs VNINDEX). | Mean return/hit rate/tương quan VNINDEX theo tháng cho 15 rổ ngành; bỏ tham số trả toàn bảng. Nhận tên rổ tiếng Việt không dấu ("ngan hang", "dau khi"...). | PG `cycle_month_stats` (refresh từ VCI) | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_chains | ['pair'] | Relative rotation chains (A strong -> B vs VNINDEX next month). Omit pair for full table. | Chuỗi luân chuyển tương đối: rổ A mạnh → rổ B so VNINDEX tháng sau; bỏ `pair` trả toàn bảng. | PG `cycle_chains` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_turning | ['year'] | Each calendar year's highest/lowest close date per index (year to date for the current year). | Ngày đỉnh/đáy theo close của từng năm cho 11 chỉ số (năm hiện tại = YTD). | PG `cycle_turning` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_tet | ['basket'] | Tet (Lunar New Year) effect per basket: compounded return over the 6 sessions before / 5 after. | Hiệu ứng Tết theo rổ: lợi nhuận 6 phiên trước / 5 phiên sau Tết; nhận tên rổ tiếng Việt không dấu. | PG `cycle_tet` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_yearly | ['basket', 'year'] | Yearly return % per VN sector basket (bank, securities, realestate, vin, steel, tech...); ranks sectors by year (current year = year to date). Omit args for full table. | Lợi nhuận % theo năm của từng rổ ngành, xếp hạng; cờ `is_partial_year` cho năm đang chạy hoặc rổ thiếu phiên cuối năm. | PG `cycle_yearly` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_trough_events | [] | 3M forward returns per VN sector basket after major market troughs (which sectors lead recoveries). | Lợi nhuận 3 tháng sau các đáy lớn theo rổ; cờ `window_complete` và `rule` nói rõ độ tin cậy (đáy chỉ biết sau khi xác nhận). | PG `cycle_trough_events` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_stats_refresh | ['symbols'] | Incremental refresh a batch (max 15/call, recommend 12) of the tracked symbols. | Refresh tăng dần tối đa 15 mã/lần qua VCI (watermark + overlap 10 phiên, lệch close >0.5% → fetch lại full); mỗi mã một transaction, 1 refresh/lần. | VCI candles → PG `cycle_ohlcv` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| cycle_stats_finalize | ['extra_tet'] | Recompute derived tables from cache in one transaction; bump meta. Run after all batches. | Tính lại bảng dẫn xuất từ cache trong một transaction và bump meta; chạy sau khi refresh đủ batch. | PG `cycle_ohlcv` → `cycle_month_stats/chains/...` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |

## asset_cycle.py — 11 tools (PG-backed, thêm 2026-10-10)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vn_asset_check | [] | Staleness of VN multi-asset tables. No fetch. | Độ mới bảng tài sản VN: 6 tài sản (VNINDEX, GOLD_W, USDVND, RON95, BTC, BRENT), ngày cuối. | PG `vn_asset_*` + `vn_asset_meta` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_asset_seasonality | ['asset', 'month'] | Monthly mean/hit per VN asset (VNINDEX, GOLD_W, USDVND, RON95, BTC, BRENT). | Mean return/hit rate theo tháng của 6 tài sản VN. | PG `vn_asset_monthly` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_asset_anchors | ['asset'] | Anchor data (yields/spreads/walls/flows) with provenance; curated by hand. | Dữ liệu neo (yield/spread/wall/flow) có nguồn, curate thủ công. | PG `vn_asset_anchors` (curated) | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_asset_chains | [] | Cross-asset lead-lag links (BTC->VNI, Brent->RON95); curated by hand. | Liên kết lead-lag chéo tài sản (BTC→VNI, Brent→RON95), curate thủ công. | PG `vn_asset_chains` (curated) | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| g_asset_check | [] | Staleness of global asset tables. No fetch. | Độ mới bảng tài sản toàn cầu (17 ETF + USREC), ngày cuối. | PG `g_*` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| g_asset_seasonality | ['asset', 'month'] | Monthly mean/hit per global asset (17 ETFs). Omit args for full table. | Mean return/hit rate theo tháng của 17 ETF; bỏ tham số trả toàn bảng. | PG `g_asset_monthly` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| g_asset_phase | ['asset'] | NBER-phase returns (Early/Late/Mid/Recession); Early/Late/Recession rest on few months. | Lợi nhuận theo pha NBER (Early/Late/Mid/Recession); pha hiếm có ít tháng Quan sát. | PG `g_asset_phase` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| g_asset_corr | ['regime'] | Cross-asset monthly correlations in percent (85.3 = 0.853). regime: full / pre22 / post22. | Tương quan tháng giữa các tài sản (đơn vị %, 85.3 = 0.853); `regime` = full/pre22/post22. | PG `g_asset_corr` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| g_asset_outlook | ['house'] | Curated bank/fund allocation calls per quarter (with sources). Manually refreshed. | Khuyến nghị phân bổ theo quý của bank/fund kèm nguồn; cập nhật thủ công. | PG `g_asset_outlook` (curated) | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_asset_refresh | [] | Refresh the 6 VN assets (incremental) + recompute monthly. One refresh at a time. | Refresh tăng dần 6 tài sản VN + tính lại bảng tháng; 1 refresh/lần. | vnstock/yfinance → PG `vn_asset_*` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| g_asset_refresh | [] | Refresh 17 ETFs + USREC (incremental) + recompute monthly/phase/corr. | Refresh tăng dần 17 ETF + USREC + tính lại tháng/phase/corr; 1 refresh/lần. | yfinance + FRED USREC → PG `g_*` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |

## market_timing.py — 1 tool (thêm 2026-10-14)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| distribution_count | ['symbol', 'days', 'undercut_reverse_day1'] | Đếm phiên phân phối O'Neil + trạng thái follow-through. Dùng khi đánh giá rủi ro chung của thị trường theo O'Neil. | Đếm phiên phân phối trong 25 phiên gần nhất (close giảm ≥0.2% + volume tăng) + state machine follow-through (rally_attempt/confirmed/failed/stale). Mức 0-2 bình thường · 3 quan sát · 4 cảnh báo · 5 cảnh báo cao · >5 nguy hiểm. `undercut_reverse_day1` mặc định True (strict-IBD). | vnstock VCI candles VNINDEX (chỉ phiên đã đóng) | `{"count_25": 5, "status": "canh_bao_cao", "ftd": {"state": "rally_attempt", "day1_date": "2026-11-20"}, "decline_from_high_pct": -4.34}` (live 2026-11-23) | available | remote |

## vn_predictions.py — 3 tools (PG shared `predictions`, thêm 2026-10-28)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vn_predictions_check | [] | Độ mới của bảng dự báo hàng ngày (số tài sản, ngày dự báo gần nhất). Dùng trước tiên. | Độ mới bảng dự báo 12 tháng: số dòng, số tài sản, ngày gần nhất; không fetch. | PG `predictions.predictions_daily` (pipeline `mcp-opentrading-sub`) | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_predictions_latest | ['asof', 'currency', 'asset'] | Bảng dự báo 12 tháng mới nhất (43 tài sản VND + đối chiếu USD). | Bảng dự báo 12 tháng mới nhất: p_profit/p_gain/p_loss/median/q10/q90; lọc `asof` (YYYY-MM-DD), `currency` (VND/USD), `asset`. | PG `predictions.predictions_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_predictions_sparkline | ['asset', 'currency', 'days'] | Chuỗi biến động dự báo theo ngày cho MỘT tài sản (sparkline N ngày gần nhất). | Chuỗi xác suất/median theo ngày cho một tài sản; `days` tối đa 365. | PG `predictions.predictions_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |

## vn_screener.py — 3 tools (PG shared `predictions`, thêm 2026-10-29)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vn_screener_check | [] | Độ mới của bảng tín hiệu screener (số mã, ngày gần nhất). Dùng trước tiên. | Độ mới bảng screener: số dòng, số mã đã chấm, ngày gần nhất. | PG `predictions.screener_signals_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_screener_top | ['limit', 'min_probability'] | Top mã có xác suất chạm +20% trong 20 phiên cao nhất (ngày gần nhất). | Top mã theo P(touch +20%/20 phiên), `limit` 1-50, `min_probability` 0-1. Xác suất nghiên cứu (TB 6.8% vs thực tế 4.2%) — chỉ để xếp hạng, không phải tín hiệu mua. | PG `predictions.screener_signals_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_screener_symbol | ['symbol'] | Lịch sử tín hiệu của một mã (toàn bộ ngày đã ghi — sparkline P(touch)). | Lịch sử P(touch) của một mã, tối đa 90 ngày. | PG `predictions.screener_signals_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |

## vnindex_scenarios.py — 4 tools (PG shared `predictions`, thêm 2026-10-29)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vnindex_scenarios_check | [] | Độ mới của bảng kịch bản VNINDEX (số khối kỳ hạn, ngày gần nhất). Dùng trước tiên. | Độ mới bảng kịch bản: số dòng, số ngày, ngày gần nhất. | PG `predictions.vnindex_scenarios_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vnindex_scenarios_latest | ['asof', 'horizon'] | Kịch bản VNINDEX mới nhất: tăng/tích lũy/giảm + xác suất + vùng điểm có điều kiện + credibility ngoài mẫu. | Kịch bản tăng/tích lũy/giảm + xác suất + vùng điểm + credibility; `horizon` 10/20/40/60 (mặc định tất cả), `asof` tuỳ chọn. | PG `predictions.vnindex_scenarios_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vnindex_scenarios_history | ['horizon', 'days'] | Chuỗi kịch bản theo ngày cho MỘT kỳ hạn (sparkline xác suất tăng/tích lũy/giảm). | Chuỗi xác suất theo ngày cho một kỳ hạn; `days` tối đa 180. | PG `predictions.vnindex_scenarios_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vnindex_risk_heads | ['asof'] | Cảnh báo rủi ro: P(chạm -5%/-10% sau 10/20 phiên) kèm baseline và credibility. | P(chạm -5%/-10% sau 10/20 phiên) + baseline + credibility. | PG `predictions.vnindex_scenarios_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |

## vn_reversal.py — 4 tools (PG shared `predictions`, thêm 2026-10-31)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu (live gần nhất) | Avail| Nơi chạy |
|---|---|---|---|---|---|---|---|
| vn_reversal_check | [] | Độ mới của bảng tín hiệu MUA/BÁN (số cổ phiếu — không kể VNINDEX, trạng thái VNINDEX riêng, ngày gần nhất, model_version). | Độ mới bảng tín hiệu: số mã (trừ VNINDEX), số MUA/BÁN, trạng thái VNINDEX riêng, model_version. | PG `predictions.reversal_signals_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_reversal_signals | ['asof', 'action', 'include_neutral'] | Danh sách tín hiệu MUA/BÁN mới nhất cho từng cổ phiếu. | Tín hiệu MUA/BÁN mới nhất từng mã; VNINDEX trả riêng ở `data.vnindex`. `action` = MUA/BAN/bỏ trống; `include_neutral` gồm mã trung tính. Trạng thái 6 mức (MUA MANH/MUA/BAN MANH/BAN/BIEN DONG CAO/TRUNG BINH). | PG `predictions.reversal_signals_daily` (Stage D) | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_reversal_dashboard | ['asof'] | Dashboard ngành: 15 rổ (theo cycle_stats: bank, securities, ..., vin) + 4 Họ (Vin/GELEX/FPT/Viettel). | Dashboard ngành: 15 rổ + 4 Họ, số mã xác nhận đáy/đỉnh W5, số tín hiệu, ret5, breadth trên SMA50, leader mỗi rổ. | PG `predictions.reversal_sector_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |
| vn_reversal_history | ['symbol', 'days'] | Chuỗi xác suất/tín hiệu theo ngày cho MỘT mã (sparkline N ngày gần nhất). | Chuỗi p_ban/p_mua/p_swing theo ngày cho một mã (hoặc VNINDEX); `days` tối đa 365. | PG `predictions.reversal_signals_daily` | — (chưa chạy live; cần `DATABASE_URL`) | chưa verify (PG) | remote |

---

## Tools local của harness OpenTrading (không qua MCP)

> Sau merge upstream 06-10: **21 tools** chạy **local** trong tiến trình harness
> (`OpenTrading/src/core/`), không phải tools của MCP-server. Nguyên tắc chia: secrets +
> network + team-shared state → remote; session-local + render + deterministic → local.
> Turn-guards (doom-loop/budget 20) bị upstream thay bằng `PermissionGate` (ask trước tool
> side-effect). Chi tiết: `docs/architecture-review-2026-10-05.md` §8.5.

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Nguồn | Nơi chạy |
|---|---|---|---|---|---|
| current_time | [] | Trả về ngày giờ hiện tại theo giờ Việt Nam (Asia/Ho_Chi_Minh, UTC+7) và thứ trong tuần. | Đồng hồ VN deterministic để model không đoán "now". | `tools/builtin/current-time.ts` (Intl, không mạng) | local |
| load_skill | ['name', 'file?'] | Nạp hướng dẫn chi tiết của một skill trong catalog rồi làm theo. | Progressive skill loading: system prompt chỉ list tên, body fetch khi cần. | `tools/builtin/load-skill.ts` + `skills/<slug>/SKILL.md` | local |
| ask_user | [questions] | Hỏi người dùng 1–4 câu trắc nghiệm khi thiếu thông tin. | Upstream merge 06-10; thay denial khi thiếu data. | `tools/builtin/ask-user.ts` + AskBroker | local |
| todo_write | [items] | Ghi danh sách việc cần làm; ghim trên prompt, nhắc mỗi lượt. | Upstream merge 06-10 (PR #22-24); items viết cho user. | `tools/builtin/todo-write.ts` | local |
| tool_search | [query] | Tìm + nạp tool đang hoãn theo tên. | Tool-search deferral: 174 MCP tools deferred — model thấy tên, nạp schema khi cần. | `tools/builtin/tool-search.ts` | local |
| list_mcp_resources / read_mcp_resource | [uri?] | Liệt kê/đọc resources MCP. | Upstream merge 06-10; đọc catalog/reference. | `tools/builtin/` | local |
| chart_render | ['kind', 'symbol?', 'bars?', 'series?', 'labels?', 'matrix?', 'value?', 'max?', 'unit?', 'width?', 'height?', 'color?'] | Vẽ biểu đồ text có màu từ dữ liệu đã có. | 10 kinds: candlestick/line/sparkline/bar/histogram/heatmap/gauge/donut/area/winloss; màu ANSI theo chiều (tăng xanh/giảm đỏ); chỉ render, không fetch. | `@crafter/charts` (zero-dep) | local |
| chart_compare | ['title?', 'series[2-5]', 'width?', 'height?', 'color?'] | Vẽ nhiều đường giá chồng nhau để so sánh. | Overlay + legend, chuẩn hóa % từ điểm đầu, chuỗi ngắn tự căn phải. | `@crafter/charts` multi-mark | local |
| chart_depth | ['symbol?', 'bids', 'asks', 'depth?'] | Vẽ ladder bid/ask text từ orderbook đã có. | ASK/mid/BID + thanh volume; rỗng 2 bên → báo trung thực (ngoài giờ). | thuần local | local |
| session_list | ['limit?'] | Liệt kê các phiên hội thoại đã lưu trên máy này. | Thay `runs_list` server-share bằng sessions của chính user (không trộn runs). | `~/.opentrading/sessions/index.jsonl` | local |
| session_get | ['id'] | Đọc tóm tắt một phiên cũ theo id. | Lấy lại câu hỏi user từng hỏi để nối ngữ cảnh. | `session/store.ts loadSession` | local |
| doctor_local | [] | Tự kiểm tra harness trên máy này. | Model/MCP status local; phân biệt với `doctor` (env của server). | runtime + `mcp.status()` | local |
| watchlist_local_create | ['name'] | Tạo watchlist CÁ NHÂN trên máy này. | Tracking riêng, offline được; share team thì dùng `watchlist_create` remote. | `~/.opentrading/watchlists.json` | local |
| watchlist_local_list | [] | Liệt kê watchlist cá nhân kèm mã đang theo dõi. | Đọc file local, không qua RPC. | `~/.opentrading/watchlists.json` | local |
| watchlist_local_add | ['name', 'symbols'] | Thêm mã vào watchlist cá nhân (uppercase, dedupe). | Validate + sort local. | `~/.opentrading/watchlists.json` | local |
| watchlist_local_remove | ['name', 'symbols'] | Bớt mã khỏi watchlist cá nhân. | Lọc local. | `~/.opentrading/watchlists.json` | local |
| watchlist_local_delete | ['name'] | Xóa watchlist cá nhân. | Xóa key local. | `~/.opentrading/watchlists.json` | local |
| spawn_subagent | ['task', 'skills?', 'tools?', 'workdir?', 'timeout?'] | Chạy worker AI con (opencode) cho việc nặng song song. | Tiered spawn (local CLI trước, API fallback), transcript đầy đủ vào trace; thay thế pattern spawn thủ công. | `tools/subagent/spawn.ts` (opencode CLI/API) | local |
| web_fetch | ['url', 'maxChars?'] | Đọc 1 URL → text sạch (đệ quy nội bộ). | Render song song (browser headless → Readability → html thô), không denial text; khác `web_fetch` remote (server-side, PDF). | `tools/web/fetch.ts` | local |
| web_search | ['query', 'count?'] | Tìm web (song ngữ) trả URL + snippet + text. | Exa→Parallel→DuckDuckGo HTML (theo key có sẵn); 60s timeout, top 5. | `tools/web/search.ts` | local |

---

# PHẦN II — 6 WORKFLOWS (prompts, chạy live 2026-10-02)

Prompts không fetch data — chúng chỉ dẫn agent gọi tools theo thứ tự. Dưới đây là kết quả chạy thật từng workflow.

## WF1 — morning_briefing (scope=vn): 5 available + 1 partial

| # | Tool | Result live |
|---|---|---|
| 1 | brief_build | available 2.1s — Greed 70–74 (7 ngày), Fireant news live (Quỹ bình ổn xăng dầu, đất nền HN, thuế) |
| 2 | market_overview | partial — VCB 57,400 (−0.35%), HPG 19,950 (−0.50%); session leg null (thiếu worker) |
| 3 | breadth_scan | available — advancers 1 / decliners 6 |
| 4 | money_flow | available — NN bán ròng (BuyVal 1,814 vs SellVal 2,268 tỷ) |
| 5 | futures_basis | available — F1M premium +6.95 (+37bps) |
| 6 | world_prediction_odds | available 9.9s — Fed giữ nguyên tháng 10: 74.5% |

**Verdict WF1**: phiên yếu (breadth 1/6, bluechip đỏ, NN bán ròng), phái sinh premium nhẹ +37bps, macro ngoài êm (Fed 74.5% giữ). Unknowns: session chính xác (thiếu worker), NN intraday realtime.

## WF2 — ticker_analysis (VCB): 8/8 available

| # | Tool | Result live |
|---|---|---|
| 1 | stock_overview | available — VCB ~57,400, vốn hóa 479.6T |
| 2 | signals_technical | available — RSI 39.2, ADX 12.1 (trend yếu), MACD −0.31/−0.13, giá dưới EMA10/20/50 |
| 3 | valuation_run | available — per_pb @57,300 |
| 4 | stock_forensic | available — DSRI 0.72/GMI 1.93/AQI 1.01/SGI 1.08, SGAI null (LCTT rỗng) → M partial, F 4/6, không flags |
| 5 | insider_trading | available — không deals (đúng data) |
| 6 | analyst_consensus | available — rỗng (không báo cáo mới, đúng) |
| 7 | company_events | available — 487 docs, link PDF trực tiếp |
| 8 | news_symbol | available — Fireant posts (lãi suất VCB 0.1–6%) |

**Verdict WF2**: BEAR ngắn hạn (kỹ thuật yếu toàn diện) / NEUTRAL cơ bản (forensic sạch, minh bạch cao). Điều đổi nhận định: RSI <30 oversold thật hoặc vượt lại EMA50 58.74.

## WF3 — pre_earnings (FPT): 13/13 available → Grade B

| Leg | Tools | Result live |
|---|---|---|
| 1. Date | company_events + event_calendar_vn | 466 docs; thưởng CP 10:1 ex 21-09-2026 (đã qua); ngày BCTC Q3 chưa rõ → unknown |
| 2. Trend | financial_statements | Q1–Q2/2026 số thật (warning: statement filter trả all pages) |
| 3. Manipulation | stock_forensic | **M −2.06 sạch (đủ 7 chỉ số)**, F 2/6, không flags |
| 4. Anchor | planned_targets + analyst_consensus + news_symbol + sentiment_score | KH DT 61,850/75,400/58,580 (2024/25/26); consensus rỗng; sentiment −0.25 heuristic (thiếu Groq key); tin HOSE chứng quyền |
| 5. Positioning | insider_trading + money_flow + block_trades | insider none; NN bán ròng chung; FPT pt 0% hôm nay |
| 6. Cushion | valuation_run + scenario_simulate | per_pb @62,700; shock −5% → −3,140đ/1000cp |

**Verdict WF3**: Grade **B** — chất lượng sạch + KH rõ, trừ F-score thấp (2/6), sentiment âm, thiếu street coverage, chưa rõ ngày BCTC.

## WF4 — sector_rotation: tiền vào Vật liệu, ra Tài chính/BĐS

| # | Tool | Result live |
|---|---|---|
| 1 | sector_performance | available — Vật liệu **+1.12%** (YTD +8.9); Tài chính −0.8%; BĐS −1.33%; Năng lượng YTD +48.2% |
| 2 | money_flow | available — NN bán ròng |
| 3 | futures_basis | available — +6.58 (+35bps) |
| 4 | ipo_calendar_vn | available — auctions rỗng, chỉ announcements cũ (đúng) |
| 5 | compare_equities (HPG,HSG) | available — HPG 19,950 (−0.50%) vol 9.6tr |

**Verdict WF4**: rotation **tài-chính/BĐS → vật-liệu (thép)** trong phiên; YTD thì năng lượng (+48%) và viễn thông (+39.8%) dẫn. Unknowns: leaders ngành vật liệu ngoài HPG/HSG.

## WF5 — ai_detect (HPG, validate mode): 7/7 available → REJECT

| Leg | Tools | Result live |
|---|---|---|
| 1. Trend | signals_technical | **FAIL** — 19.95 < sma50 21.37 < sma150 23.07 < sma200 23.31; RS −7.32; pos_52w 0.008; recommend Sell |
| 2. Contraction | technicals | partial — oversold sâu (stoch 2.9/0.98, CCI −129.6), ATR 0.37 |
| 3. Breakout | signals_scan + pattern_match | **FAIL** — scan 0 hits; pattern corr cao nhất 0.41 (yếu) |
| 4. Fundamentals | vn_fundamentals + valuation_run | trung tính — có EPS/BVPS/PE; per_pb @19,900 |
| 5. Flow | money_flow + block_trades | **FAIL** — NN bán ròng; pt chỉ 1.1% hôm nay |

**Verdict WF5**: **REJECT (0–1/5 legs)** — đang rơi, ngồi ngay support 19.9. Invalidation: thủng 19.9 → tránh; chỉ xem lại khi vượt sma50 + scan có hit.

## WF6 — risk_check (VCB,HPG buy 100tr): 10/10 available → HALF

| # | Tool | Result live |
|---|---|---|
| 1 | quant_risk (VCB 63 phiên) | Sharpe −1.15, maxDD 12.3%, win 41% |
| 2 | scenario_simulate | shock −5% @57.4 → −2,870đ/1000cp (≈ −5tr trên size 100tr) |
| 3 | correlation_matrix | VCB-HPG 0.50 (91 phiên chung) |
| 4 | stock_forensic ×2 | VCB: M partial, F 4/6; HPG: M −2.24, F 2/6; cả 2 không flags |
| 5 | company_events + event_calendar_vn | VCB 487 docs; cổ tức 450đ đã qua ex 23-07 → không blackout 10 ngày |
| 6 | valuation_run | per_pb @57,400 (cushion) |

**Verdict WF6**: **HALF (size tối đa ~50tr)** — rủi ro lịch sử xấu (Sharpe âm, win <50%) nhưng forensic sạch + không blackout nên không NO-GO. Invalidation: VCB thủng 54.5. Unknowns: trượt giá khi bán mạnh, biến động sau ĐHĐCĐ, tương quan lúc stress.

---

## Phụ lục — Tools đã xóa (có thay thế)

| Tool | Lý do xóa | Thay thế live |
|---|---|---|
| vs_reports_search | Route 404 mọi params | analyst_consensus, news_symbol |
| vs_stock_industry | model rỗng mọi level | vs_industry_tree + vs_industry_heatmap |
| vs_top_liquidity | Body rỗng | market_movers |
| vs_news_search | dc route chết | news_market + sources=gdelt |
| dnse_foreign_rest | Endpoint từ chối mọi range | dnse_foreign_flow, money_flow |
| vs_financial_values | Gói JWT giới hạn kỳ | vs_financeinfo, financial_detail |
| signals_trade_log | Log trống | runs_list/run_get |
| macro_reports, mega_flows, foreign_flow, oracle_health | Alias/gộp | analyst_consensus, money_flow, oracle_meta |

## Lịch sử phases (tóm tắt)

| Phase | Nội dung | Commit |
|---|---|---|
| P5 | Enrich params 126 tools (65 tests) | 7dcc77e |
| P6 | Viết lại descriptors + disambiguation 6 nhóm overlap | 258d634 |
| P7 | 17 tools mới (corp 7, crypto 2, quant 5, brief 2) | — |
| P8 | 6 prompts + SEPA legs (sma150/rs/pos_52w) | c8a9ddc |
| P9 | Honest-availability (không available-giả) | 17e1155 |
| P10 | Required POST fields (nn/selftrading/gics/marketinfo sống lại) | 1027287 |
| P11 | breadth case-fix, reference KBS, vàng BTMC https | 4c91136 |
| P12/P13 | Xóa tools chết | ac99396, e1fd4b9 |
| P14 | Macro HAR-session + snapshots PG + catalog 136 | 958b957 |
| P15 | BCTC-detail revive + forensic rewrite + full-135 live | 3485e6a |
| Docs | Full-135 + fix stale counts + 6 workflows live | 1d9f498 |
| P18 | Hủy preset → single surface 139 + annotations + paginate + 7 correctness fixes + arch 10-05 | working-tree 2026-10-05 |
| P19/P20 | Tách compute→3 + quant→2 files; `@guarded` vnstock/intel; vocab `source` chuẩn (`ALLOWED_SOURCES`); verify 139 + assert; mount `/sse`; `as_of` tz-aware; crypto caps; world_prediction_odds retry; local harness +3 (spawn_subagent/web_fetch/web_search) | working-tree 2026-10-06 |
| P21 | Xóa preset-gating harness + descriptors coerce/vd/phủ định (vs_indicator_data, quant_risk, dnse_latest_trade, valuation, analyst, quote_history, trading_info) + 7 skills source-guard | working-tree 2026-10-06 |
| P22 | geo_intel lọc chính trị + aggregate + military (adsb.lol, port oracle 8010); event_stats aggregate tách vai; valuation btype validation; 9 skills bỏ call-count + feedback fixes (forensic explanation, bỏ Step 1 BCTC, top-20 posts+comments) | 0157d2a |
| P23 | Render full-matrix verify (137/139): sub-batch equity_quote_batch 10/chunk + partial + non-blocking shutdown (fix 502 OOM); quant_backtest equity_curve; vn_msn_fx_gold series; geo_intel empty-fallback; yf_yield_curve FRED fallback; crypto_spot vision+CoinGecko fallback; valuation EPS fallback; vn_retail_gold 30s | working-tree 2026-10-06 |
| P25 | vnstock API key (Trading_Agents .env → 60 req/min community tier): auto-register once/process + quota_info trong source_status; render.yaml thêm VNSTOCK_API_KEY (sync:false, admin set value) | working-tree 2026-10-06 |
| P25 | market_movers universe vn30 default (static VN30, bỏ HOSE ref call treo/crash instance) + test | working-tree 2026-10-06 |
| P24 | Vietstock JWT session fallback (`_detail_session_post` + `_browser_post` shared): detail/macro endpoints serve real values WITHOUT HAR — 5 tools mở trên Render (financial_detail 25 rows, planned_targets, stock_forensic, vs_indicator_data 1995 rows, vs_xnk_detail 504 rows) | 7182c5b |
| P23 | Merge upstream harness (tool-search #19, mcp-instructions #20, prompt-tuning #21, todo #22-24, compact #23): theirs pipeline + ours local tools, registry 160 (21 local + 139 deferred); turn-guards → PermissionGate | baf7a2c, da10329 |
| P26 | Cycle stats PG-backed (20 tools: `cycle_stats` 9 + `asset_cycle` 11), baskets v2 (15 ngành + Vin), trough events | b1500f0, 36facd7 |
| P27 | `distribution_count` — O'Neil distribution days + follow-through state machine | ce224f1 |
| P28 | `vn_predictions_*` — đọc dự báo 12 tháng (43 tài sản) từ schema `predictions` | a19ab99 |
| P29 | `vn_screener_*` + `vnindex_scenarios_*` — P(touch +20%), kịch bản VNINDEX, risk heads | 3862803 |
| P30 | `vn_reversal_*` — tín hiệu MUA/BÁN + dashboard ngành (Stage D, model 4) | 397f5aa |
| vn6 | vnstock 6.0.0 final: ratios qua `vnstock_quant.fa`/financeinfo, FX-gold-global qua Yahoo, index routing, batch quote, release verdict trong `source_status` | 6cb7531, ea27705 |
