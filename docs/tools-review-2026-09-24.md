# Tools + Workflow — opentrading-mcp (báo cáo chi tiết, số liệu live 2026-10-02)

**136 tools unique · 127 READ_ONLY / 9 READ_WRITE · 6 presets · 6 prompts (workflows) · 4 resources**
(P16 mới: `symbol_resolve` — multi-asset resolver; `signals_technical` mở 1W/1M + Ichimoku/swing/fibo; `backtest_strategies` thêm `rsi_meanrev` + filter months/quarters)
Chạy live 135/135 ngày 2026-10-02 (có key): **129 available · 1 partial · 2 empty (đúng bản chất) · 3 unavailable (WS trio, thiếu worker local)**. 0 tool chết.

## 0. Tổng quan presets

| Preset | Tools | Cap | Modules |
|---|---|---|---|
| market | 66 (65 khi thiếu websearch key) | 75 | market(9), web, vn, vs, vs_bctc, vn_ext, yf, yf_world, dnse_tools, dnse_ext, crypto |
| scan | 47 | 60 | scan(6) + compute(20) + watchlist(12) + corp(9) |
| quant | 9 | 50 | quant |
| brief | 7 | 50 | brief |
| intel | 8 (9 khi có websearch key — web_search gate theo key) | 50 | intel(7) + web(1+1 key) |
| all | 136 (137 khi có websearch key; web_fetch dùng chung market+intel) | không cap | 18 modules |

| Kênh avail | Số tools | Ghi chú |
|---|---|---|
| available | 129 | gồm 3 tools re-run xác nhận (signals_scan, valuation_run, financial_statements — lỗi thoáng qua) |
| partial | 1 | market_overview (session leg null, thiếu WS worker) |
| empty (đúng) | 2 | runs_list, run_get (chưa có runs local) |
| unavailable | 3 | dnse_foreign_flow, dnse_ws_snapshot, dnse_indices (cần worker local; prod có) |

TIMEOUT_MATRIX (contract client): tools_list 30, market_snapshot 15, breadth_scan 15, yf_mega_flows 60, dnse_ohlc_history 60, quant_backtest 120, quant_factors 120, stock_screener 60, signals_screener_columns 30, watchlist_get 30, alert_check 30.

Env chạy lại: `set -a; source ~/Trading_Agents/.env; set +a; export MCP_DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:15432/opentrading_mcp" VIETSTOCK_HAR_FILE="docs/finance.vietstock.vn_Archive [26-10-01 18-35-43].har"`.

---
## market.py — 9 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| market_snapshot | ['symbols', 'as_of'] | Snapshot of VN market with provenance. Use when a broad market picture is needed. | Báo giá 30 mã VN30 kèm trần/sàn/tham chiếu/vol + nguồn. Tham số as_of chỉ là nhãn. | vnstock quote_batch (cache 60s) | `{"quotes": [{"symbol": "ACB", "time": 1790910967815.0, "exchange": "HOSE", "ceiling_price": 22550.0, "floor_price": 19650.0, "reference_price": 21100.0, "open_p` | available |
| source_status | [] | Health of every upstream plus TTL state. Use to debug stale data. | Sức khỏe từng upstream (JWT, vnstock, WS, TTL cache). Gọi đầu tiên khi nghi data cũ. | local aggregator (env + TTL states) | `{"upstreams": {"vietstock": {"authenticated": true, "jwt_expires_at": 1790943335}, "vnstock": "ok", "dnse_ws": "cold"}, "stateless": true, "ttl": {"snapshot": 5` | available |
| market_candles_batch | ['symbols', 'days', 'summary', 'columns'] | Batch OHLCV for symbols, one request per symbol. Use for multi-chart context. | Nến hàng loạt; mã lỗi vào `missing`, không fail cả batch. | vnstock VCI→KBS per symbol | `{"series": [{"symbol": "VCB", "count": 5, "last": 57.3, "high": 58.5, "low": 57.2}, {"symbol": "HPG", "count": 5, "last": 19.95, "high": 20.8, "low": 19.9}], "m` | available |
| symbol_resolve | ['query', 'limit'] | Resolve ANY asset code to symbol + class + next tool. Use FIRST when unsure. | Phân giải mọi mã (CK VN, crypto, forex, index TG, futures, vàng/dầu) thành symbol chuẩn + loại tài sản + tool tiếp theo, xếp hạng + cờ ambiguous để fallback. | local tables + vnstock Listing | `{"resolved": {"symbol": "GC=F", "asset_class": "commodity"}}` (live: vàng→GC=F, BTC→BTCUSDT, VN30F1M→futures) | available |
| symbol_lookup | ['query', 'limit'] | Resolve company name to symbol, venue and sector. Use before any symbol-scoped call. | Tra mã từ tên công ty không dấu (`hoa phat` → HPG). | vnstock Listing + Reference | `{"hits": [{"symbol": "HPG", "name": "CTCP Tập đoàn Hòa Phát"}, {"symbol": "HPA", "name": "CTCP Phát triển Nông nghiệp Hòa Phát"}, {"symbol": "HTP", "name": "CTC` | available |
| market_movers | ['top_n'] | Top gainers, losers and volume leaders. Use for session pulse checks. | Top tăng/giảm/thanh khoản của bluechip trong phiên. | local snapshot (VN30 universe) | `{"movers": [{"symbol": "VCB", "time": 1790910971687, "exchange": "HOSE", "ceiling_price": 61600, "floor_price": 53600, "reference_price": 57600, "open_price": 5` | available |
| breadth_scan | ['exchange'] | Advancers, decliners, ceiling and floor counts. Use to judge rally health. | Đếm mã tăng/giảm/trần/sàn toàn sàn (đếm case-insensitive). | Vietstock getmarketprice + marketinfo | `{"advancers": 1, "decliners": 6, "rows": 7}` | available |
| market_overview | ['top_n'] | One-call market context: bluechip quotes, movers, breadth, session. Use for briefs. | Gộp quotes+movers+breadth+session một call; legs degrade độc lập (partial khi thiếu worker). | vnstock batch + DNSE WS (session) | `{"quotes": [{"symbol": "VCB", "time": 1790910974093, "exchange": "HOSE", "ceiling_price": 61600, "floor_price": 53600, "reference_price": 57600, "open_price": 5` | partial |
| dnse_market_status | [] | DNSE session state plus latest index snapshot. Use for open/close checks. | Trạng thái phiên DNSE + snapshot chỉ số (REST fallback khi WS lạnh). | DNSE WS cache → DNSE REST → unavailable | `{"rest": [{"symbol": "VN30F1M", "trades": []}]}` | available |

## web.py — 1 tool (+1 gated)

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| web_fetch | ['url', 'format', 'timeout_seconds'] | Fetch a URL and convert to markdown, text or html. Use for reading web content. | Đọc URL → markdown/text/html, cap 5MB, retry khi CF-403. | httpx trực tiếp (browser-UA, cap 5MB) | `{"title": "https://example.com (text/html; charset=utf-8)", "output": "Example DomainThis domain is for use in documentation examples without needing permission` | available |

## vn.py — 6 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| vn_quote_history | ['symbol', 'days', 'summary', 'columns', 'interval'] | Candles for a VN symbol (1D/1W/1M), VCI then KBS fallback. Use for any price history. | Nến ngày/tuần/tháng 1 mã VN, VCI→KBS tự fallback. | vnstock VCI→KBS tự fallback | `{"symbol": "VCB", "count": 5, "last": 57.3, "high": 58.5, "low": 57.2}` | available |
| vn_equity_quote_batch | ['symbols', 'summary', 'columns'] | One-request price board for many symbols. Use for snapshots and movers. | Bảng giá N mã trong 1 request — nhanh nhất để snapshot. | vnstock Market.equity(list) | `{"count": 2, "symbols": ["VCB", "HPG"]}` | available |
| vn_listing | ['limit'] | Full symbol list with company names. Use for universe and lookup. | Universe 1522 mã toàn thị trường kèm tên công ty. | vnstock Listing().all_symbols() | `{"count": 1523, "symbols": [{"symbol": "DPP", "name": "CTCP Dược Đồng Nai"}, {"symbol": "SDA", "name": "CTCP Simco Sông Đà"}, {"symbol": "CLH", "name": "CTCP Xi` | available |
| vn_fundamentals | ['symbol', 'period', 'report_type'] | Ratios and statements via vnstock Fundamental and Finance. Use for quick valuation. | PE/ROE/EPS/BVPS nhanh qua vnstock (có thể throttle giờ cao điểm). | vnstock Fundamental + Finance | `{"symbol": "VCB", "ratios": "                                                 item  ...      2022\n0   Thu nhập trên mỗi cổ phần của 4 quý gần nhất (...  ...   ` | available |
| vn_retail_gold | ['source'] | SJC and ring gold buy/sell from BTMC retail. Use for local gold premium. | Giá vàng SJC/nhẫn BTMC trực tiếp qua https (timeout 15s). | BTMC JSON https trực tiếp → vnstock fallback | `{"rows": [{"name": "VÀNG MIẾNG SJC (Vàng SJC)", "karat": "24k", "gold_content": "999.9", "buy_price": "13950000", "sell_price": "14350000", "world_price": "4150` | available |
| vn_retail_fx | [] | VCB USD buy/sell rates. Use for currency conversion context. | Tỷ giá mua/bán của VCB (đa ngoại tệ). | vnstock Retail (VCB) | `{"rows": [{"currency_code": "AUD", "currency_name": "AUSTRALIAN DOLLAR", "buy_cash": "17,507.78", "buy_transfer": "17,684.63", "sell": "18,251.32", "date": "202` | available |

## vs.py — 8 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| vs_auth_status | [] | Vietstock JWT state and expiry. Use before any paid BCTC call. | Trạng thái JWT Vietstock + hạn dùng. | Vietstock session (env JWT → session.json) | `{"authenticated": true, "jwt_expires_at": 1790943335}` | available |
| vs_financeinfo | ['symbol', 'period'] | Free-mirror statements, 12 quarters or years. Use when JWT is absent. | BCTC mirror miễn phí 12 quý/năm — nguồn BCTC chính khi không cần detail. | Vietstock /data/financeinfo (mirror free) | `{"symbol": "VCB", "period": "quarter", "pages": [[[{"ID": 5, "Row": 5, "CompanyID": 1167, "YearPeriod": 2025, "TermCode": "Q2", "TermName": "Quý 2", "TermNameEN` | available |
| vs_market_price | ['type'] | Live board snapshot from Vietstock. Use as secondary quote source. | Board giá live Vietstock (dự phòng cho bảng giá). | Vietstock /data/getmarketprice | `{"rows": [{"Code": "VNIndex", "Name": "VN-Index", "Price": 1740.46, "Change": -8.84, "PerChange": -0.51, "Color": "#F00", "TradingDate": "/Date(1790874000000)/"` | available |
| vs_market_index | [] | Index closes with 1M and YTD change. Use for index context. | Chỉ số + biến động 1M/YTD. | Vietstock GetMarketIndexVNData | `{"indices": {"data": [{"IndexID": "1", "IndexTitle": "VN-Index", "MarketType": 0, "IndexType": 1, "BasicIndex": 1749.3, "CloseIndex": 1740.41, "PerChange": -0.5` | available |
| vs_nn_flow | ['days'] | Foreign investor buy/sell chart. Use to cross-check DNSE WS flows. | Chart mua/bán khối ngoại (bắt buộc đủ POST fields). | Vietstock KQGDGiaoDichNDTNNChart | `{"flow": [["/Date(1790910869700)/"], [{"TradingDate": "/Date(1790528400000)/", "BuyVol": 51180300, "BuyVal": 1461.532125, "SellVol": 58399100, "SellVal": 1682.1` | available |
| vs_categories | [] | Macro indicator catalogue (~60 categories). Use before indicator queries. | Danh mục ~60 chỉ tiêu macro để tra cứu trước khi query. | Vietstock Macro GetIndicatorCategoryData | `{"categories": [{"CategoryID": 7, "ParentID": 0, "CategoryName": "1. Tài khoản quốc gia (GDP)", "Level": 1, "DisplayOrder": 1, "HasData": false, "ListTermType":` | available |
| vs_indicator_data | ['category_id', 'term_type_id', 'sub_term_type_id', 'from_date', 'to_date'] | Macro series (GDP/CPI/FX/trade) via browser-session replay. Use for macro reads. | Số macro thật (GDP/CPI/XK) qua HAR-session replay + termType đúng. | Vietstock Macro (HAR-session replay, cache 6h) | `{"category": 73, "term_type": 3, "rows": [{"name": "TỔNG SỐ", "group": "", "period": "Quý 1/2022", "year": "2022", "value": 2137413.0, "unit": "Tỷ VNĐ", "timeor` | available |
| vs_trading_info | ['symbol'] | Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot. | Trần/sàn/room/EPS/BVPS/PE/PB nhanh theo mã. | Vietstock /company/tradinginfo | `{"symbol": "VCB", "info": {"StockCode": "VCB", "TradingDate": "/Date(1790910986000)/", "KLCPLH": 8355675094, "KLCPNY": 8355675094, "PriorClosePrice": 57600, "Ce` | available |

## vs_bctc.py — 12 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| vs_financial_terms | [] | Report term catalogue (annual, Q1-Q4, H1, 9M). Use before BCTC value queries. | Danh mục kỳ báo cáo (năm, Q1–Q4, H1, 9M). | Vietstock GetListReportTerm | `{"terms": {"data": [{"ReportTermID": 1, "ReportTermTypeID": 1, "Description": "Năm", "DescriptionEn": "Year", "DisplayOrdering": 1, "ExportName": "NAM", "FromMo` | available |
| vs_financial_norms | ['btype'] | 190+ BCTC line items for a business type. Use to resolve norm ids. | Tra 190+ chỉ tiêu BCTC theo loại hình DN (256 norms). | Vietstock BCTC_GetChiTieuForTable | `{"btype": 1, "count": 256, "norms": [{"ReportNormID": -1111, "Name": "Báo cáo tình hình tài chính", "PublishNormCode": null, "NormCode": null, "CssStyle": null}` | available |
| vs_company_info | ['symbol'] | Company names, exchange and description. Use for profiles. | Hồ sơ DN: tên, sàn, mô tả. | Vietstock BCTC_CompanyByCodes | `{"info": {"data": [{"StockCode": "VCB", "CompanyID": 1167, "CatID": 1, "CompanyName": "Ngân hàng TMCP Ngoại thương Việt Nam", "CompanyNameEN": "Joint Stock Comm` | available |
| vs_overview_trading | ['symbol'] | EPS, BVPS, PE, PB, ROEA/ROAA snapshot. Use for valuation inputs. | Snapshot định giá EPS/BVPS/PE/PB/ROEA/ROAA. | Vietstock GetStockDeal_OverviewTrading | `{"overview": {"data": [{"StockCode": "VCB", "TradingDate": "/Date(1790874000000)/", "ClosePrice": 57300, "ColorID": -1, "Change": -300, "PerChange": -0.52, "Tot` | available |
| vs_documents | ['symbol', 'page_size'] | Filings and disclosures with links. Use for corporate actions. | Công bố thông tin + link PDF tải trực tiếp. | Vietstock /data/GetDocument | `{"docs": [{"FileExt": ".pdf ", "UpdateTime": null, "TotalRow": 487, "FileInfoID": 559412, "Url": "https://static2.vietstock.vn/data/HOSE/2026/NGHI QUYET HDQT/VN` | available |
| vs_industry_tree | [] | GICS industry tree. Use before sector mapping. | Cây ngành GICS 285 nodes. | Vietstock GetTreeViewIndustryGICS | `{"tree": {"Id": 2, "Name": "Nhóm ngành", "ListIndustry": [{"IndustryID": 1, "Level": 1, "IndustryCode": 10, "ParentCode": 0, "IndustryName": "Năng lượng", "Ima` | available |
| vs_industry_heatmap | [] | Live sector heatmap. Use for intraday rotation. | Heatmap ngành live trong phiên. | Vietstock GetHeatmapGICS | `{"heatmap": [{"IndustryCode": 10, "ParentCode": 0, "Level": 1, "DisplayOrder": 0, "IndustryName": "Năng lượng", "StockFullName": null, "ImageURL": "/content/im` | available |
| vs_selftrading | [] | Prop-desk flow chart. Use alongside foreign flows. | Dòng tiền tự doanh CTCK. | Vietstock KQGDGiaoDichTuDoanhChart | `{"flow": [["/Date(1790841600000)/"], [{"TradingDate": "/Date(1788454800000)/", "BuyVol": 12735108, "BuyVal": 444.906387, "SellVol": 18948028, "SellVal": 618.016` | available |
| vs_gics_index | ['group'] | GICS index closes with foreign flow. Use for sector context. | Chỉ số ngành GICS theo 3 nhóm + NN mua/bán. | Vietstock GetGICSIndexMain {type} | `{"group": 1, "rows": [{"IndustryCode": 1010, "Url": "/nganh/1010-nang-luong.htm", "Text": "Năng lượng", "ChangeClose": 0.38, "CloseIndex": 361.99, "SectionID":` | available |
| vs_currency | [] | Reference FX table. Use as fallback FX source. | Bảng FX tham chiếu (dự phòng). | Vietstock GetCurrency | `{"rows": [{"Percent": "+0.04%", "Last": "1.12", "Css": "up"}, {"Percent": "-0.52%", "Last": "29,943.94", "Css": "dn"}, {"Percent": "-0.27%", "Last": "34,797.85"` | available |
| vs_market_info | ['exchange'] | Per-exchange board row: index, breadth, put-through. Use for 5s snapshots in hours. | 1 dòng/sàn: index, breadth, thỏa thuận (snapshot 5s trong giờ). | Vietstock /data/marketinfo {type 1/2/3} | `{"exchange": "HOSE", "rows": [{"exId": 1, "c": "VN-Index", "n": "Chỉ số VN Index", "e": "HOSE", "p": 1739.61, "ch": -9.69, "pch": -0.55, "vol": 193007672, "val"` | available |
| vs_xnk_detail | ['direction', 'from_date'] | Import/export by country via browser-session replay. Use for trade structure. | Xuất/nhập khẩu theo quốc gia, triệu USD (HAR-session replay). | Vietstock Macro listID 64/65 (HAR-session) | `{"direction": "xk", "category": 64, "term_type": 2, "rows": [{"name": "EU", "group": "EU", "period": "Tháng 1/2026", "year": "2026", "value": 5446.79, "unit": "` | available |

## vn_ext.py — 10 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| vn_index_ohlcv | ['symbol', 'count', 'summary', 'columns', 'interval'] | Index bars for VN tickers. Use for index history and breadth. | Nến chỉ số VN (VNINDEX/VN30...). | vnstock Market.index (VCI) | `{"symbol": "VNINDEX", "count": 5, "last": 1739.61, "high": 1788.0, "low": 1731.03}` | available |
| vn_equity_ohlcv | ['symbol', 'count', 'summary', 'columns', 'interval'] | Equity bars via Market API. Use as OHLCV alternative to quotes. | Nến cổ phiếu qua Market API (thay thế quote_history). | vnstock Market.equity (VCI) | `{"symbol": "VCB", "count": 5, "last": 57.3, "high": 58.5, "low": 57.2}` | available |
| vn_futures_ohlcv | ['symbol', 'count', 'summary', 'columns', 'interval'] | Futures bars. Use for derivatives backtest input. | Nến phái sinh (input backtest VN30F1M). | vnstock Market.futures | `{"symbol": "VN30F1M", "count": 5, "last": 1886.3, "high": 1937.0, "low": 1881.3}` | available |
| vn_forex_ohlcv | ['pair', 'count', 'summary', 'columns'] | FX bars. Use for currency context. | Nến FX (USDVND...). | vnstock Market.forex | `{"symbol": "USDVND", "count": 5, "last": 25959.0, "high": 26014.0, "low": 25929.0}` | available |
| vn_crypto_ohlv | ['symbol', 'count', 'summary', 'columns'] | Crypto bars. Use for digital-asset regime reads. | Nến crypto quy VND. | vnstock Market.crypto | `{"symbol": "BTCUSDT", "count": 5, "last": 2172149396.85, "high": 2225338114.99, "low": 2146590963.65}` | available |
| vn_global_index | ['symbol', 'count', 'summary', 'columns'] | Global index bars. Use as yfinance fallback. | Nến chỉ số thế giới (fallback yfinance). | vnstock Market.index scope=global | `{"symbol": "USA30", "count": 5, "last": 50926.56, "high": 51874.94, "low": 50546.54}` | available |
| vn_reference | ['exchange', 'by', 'key'] | ICB reference by exchange, group or industry. Use for universe construction. | Universe theo sàn/nhóm/ngành (source KBS, HOSE 757 mã). | vnstock Reference (KBS source, filter local) | `{"exchange": "HOSE", "rows": [{"symbol": "VID", "organ_name": "CTCP Đầu tư Phát triển Thương mại Viễn Đông", "en_organ_name": "Vien Dong Investment Development ` | available |
| vn_company | ['symbol', 'detail'] | Profile, holders and officers. Use for company research. | Vốn hóa, rating, holders, officers (chậm khi throttle). | vnstock Company (VCI→KBS) | `{"symbol": "VCB", "info": {"symbol": "VCB", "organ_code": "VCB", "current_price": 57600.0, "market_cap": 481286885414400.0, "issue_share": 8355675094, "tag": nu` | available |
| vn_msn_fx_gold | ['symbols', 'days'] | USDVND and XAUUSD via MSN. Use for gold-basis math. | USDVND/XAUUSD qua MSN (tính gold-basis). | vnstock explorer.msn | `{"series": [{"symbol": "USDVND", "points": 21, "last": {"time": "2026-09-30 00:00:00", "open": 25964.0, "high": 25975.0, "low": 25959.0, "close": 25959.0, "volu` | available |
| vn_trades | ['symbol', 'limit', 'board', 'from_date', 'to_date'] | Tick-level matched trades. Use for microstructure reads. | Băng khớp lệnh tick-level live. | vnstock Market.equity.trades | `{"symbol": "VCB", "trades": [{"time": "2026-10-02 10:17:17", "price": 57.4, "volume": 500, "match_type": "buy", "id": "2026-10-02_101717_574000_500"}, {"time": ` | available |

## yf.py — 3 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| yf_global_indices | ['tickers', 'period', 'interval'] | 9 global benchmarks. Use for overnight context. | 9 benchmarks thế giới (S&P, Nasdaq...). | yfinance GLOBAL_9 (worker pump TTL 300s) | `{"indices": [{"ticker": "^GSPC", "price": 7666.4501953125, "prev": 7651.5400390625}, {"ticker": "^IXIC", "price": 26871.595703125, "prev": 26861.060546875}, {"t` | available |
| yf_commodities | ['tickers', 'period', 'interval'] | Gold, oil, metals, BTC, VND and dollar index. Use for input-cost context. | Vàng/dầu/kim loại/BTC/VND/DXY (giá đầu vào). | yfinance COMMO_13 | `{"items": [{"ticker": "GC=F", "price": 4200.60009765625, "prev": 4186.7001953125}, {"ticker": "SI=F", "price": 61.26499938964844, "prev": 60.097999572753906}, {` | available |
| yf_yield_curve | [] | US 2Y/10Y and inversion flag. Use for rates and regime context. | Lợi suất US 2Y/10Y + cờ đảo ngược (chế độ rates). | yfinance ^TNX + 2YY=F | `{"us10y": 0.052369999885559085, "us2y": 0.046100001335144046, "inverted": false}` | available |

## yf_world.py — 6 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| yf_world_indices | ['tickers'] | 24 world benchmarks. Use for global breadth. | 24 benchmarks (độ rộng toàn cầu). | yfinance batch download | `{"indices": [{"ticker": "^GSPC", "price": 7666.4501953125, "prev": 7651.5400390625}, {"ticker": "^IXIC", "price": 26871.595703125, "prev": 26861.060546875}, {"t` | available |
| yf_oracle_markets | ['groups'] | 40 markets in 6 groups with 30d stats. Use for cross-asset state. | 40 thị trường/6 nhóm + stats 30d. | yfinance ~40 tickers 1mo | `{"crypto": [{"ticker": "BTC-USD", "price": 85271.9765625, "chg_30d": 10.31, "high30": 86602.9141, "low30": 75612.5078}, {"ticker": "ETH-USD", "price": 2715.4699` | available |
| yf_regime_assets | [] | 7 regime drivers with 2y history. Use for RISK-ON/OFF calls. | 7 tài sản dẫn dắt chế độ + lịch sử 2y (RISK-ON/OFF). | yfinance 2y + rule classify local | `{"^GSPC": {"last": 7666.4501953125, "chg_1y_pct": 14.23}, "^VIX": {"last": 16.389999389648438, "chg_1y_pct": -1.56}, "DX-Y.NYB": {"last": 101.99299621582031, "c` | available |
| yf_mega_flows | ['top_n'] | Mega-cap leader flows. Use to follow global smart money. | Dòng tiền mega-cap (AAPL/MSFT/NVDA...). | yfinance mega-cap 15 + screener | `{"universe": "mega-cap leaders", "leaders": [{"ticker": "AAPL", "price": 330.32000732421875, "prev": 333.0199890136719}, {"ticker": "MSFT", "price": 512.7999877` | available |
| yf_alloc_history | ['asset', 'timeframe'] | Long allocation history per asset. Use for regime backtests. | Lịch sử phân bổ 5y theo tài sản (backtest chế độ). | yfinance 5y | `{"asset": "GC", "ticker": "GC=F", "points": [{"t": "2026-07-09", "c": 4140.7998}, {"t": "2026-07-10", "c": 4113.7002}, {"t": "2026-07-13", "c": 4005.7}, {"t": "` | available |
| yf_market_pins | [] | 5-day pins for world majors plus VN watchlist. Use for brief headers. | Neo 5 ngày + sparkline (tiêu đề brief). | yfinance world majors + VN watchlist | `{"world": [{"ticker": "^GSPC", "last": 7666.4502, "spark": [7743.4102, 7683.6899, 7670.8398, 7651.54, 7666.4502]}, {"ticker": "^IXIC", "last": 26871.5957, "spar` | available |

## dnse_tools.py — 4 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| dnse_ohlc_history | ['symbol', 'resolution', 'bar_type', 'from_date', 'summary', 'columns', 'to_date', 'page_size'] | Paginated futures/index bars via cursor. Use for VN30F1M backtest input. | Nến futures/index phân trang bằng cursor (37k+ bars). | DNSE REST /price/ohlc (HMAC key) | `{"symbol": "VN30F1M", "count": 37748, "last": 1888, "high": 2115.7, "low": 560.1}` | available |
| dnse_latest_trade | ['symbols', 'summary', 'columns'] | Latest match price and totals per symbol. Use for realtime fallback. | Giá khớp mới nhất theo mã (fallback realtime). | DNSE REST /price/{s}/trades/latest | `{"count": 1, "symbols": ["VN30F1M"]}` | available |
| dnse_foreign_flow | [] | Net foreign flow from WS cache. Use as primary smart-money read. | NN mua/bán ròng từ WS cache — cần worker local. | DNSE WS qua Redis (cần worker) | `{"tool": "dnse_foreign_flow"}` | unavailable |
| dnse_ws_snapshot | ['symbols'] | Raw worker snapshot for symbols. Use to debug realtime staleness. | Snapshot WS thô để debug realtime — cần worker. | Redis mcp:market:dnse_ws_snapshot (cần worker) | `{"tool": "dnse_ws_snapshot"}` | unavailable |

## dnse_ext.py — 5 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| dnse_orderbook | ['symbol', 'depth'] | Bid/ask depth. Use for microstructure reads. | Depth bid/ask (futures rỗng ngoài giờ là đúng). | DNSE REST quotes/latest → /quotes | `{"symbol": "VCB", "bids": [], "asks": []}` | available |
| dnse_indices | ['symbols'] | Index snapshots from WS cache. Use for live index reads. | Snapshot chỉ số từ WS cache — cần worker. | DNSE WS market_index Redis (cần worker) | `{"tool": "dnse_indices"}` | unavailable |
| dnse_vn30f1m_live | ['bars'] | VN30F1M 1m bars aggregated to 15m with session remap. Use for intraday. | Nến 1m gộp 15m, remap phiên 14:30→14:45. | DNSE REST 1m → local agg 15m remap | `{"symbol": "VN30F1M", "tf": "15m", "bars": [{"t": 1790907300, "o": 1897, "h": 1899.4, "l": 1894, "c": 1896.9, "v": 12674}, {"t": 1790908200, "o": 1896.9, "h": 1` | available |
| dnse_working_dates | ['year'] | Trading calendar. Use for session planning. | Lịch giao dịch (lên kế hoạch phiên). | DNSE REST /market/working-dates | `{"dates": {"workingDates": ["2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-` | available |
| exchange_calendar | [] | HOSE/HNX/UPCOM hours, ATO/ATC, T+ settlement. Use for mechanics. | Giờ HOSE/HNX/UPCOM, ATO/ATC, T+2 (tĩnh). | static local (không mạng) | `{"sessions": [{"days": "Mon-Fri", "open": "09:00", "close": "15:00", "ato": "09:00-09:15", "atc": "14:30-14:45"}], "settlement": "T+2", "timezone": "Asia/Ho_Chi` | available |

## crypto.py — 2 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| crypto_spot | ['symbols'] | Binance spot 24h tickers. Use for crypto price and volume reads. | Spot Binance 24h, không key (BTC 83,476...). | Binance public /ticker/24hr (không key) | `{"tickers": [{"symbol": "BTCUSDT", "last": 85278.01, "change_pct": 2.11, "high": 85511.0, "low": 83186.0, "volume": 17780.18956, "quote_volume": 1497492624.8471` | available |
| crypto_derivs | ['symbols'] | Binance futures funding, OI and long/short ratios. Use for leverage reads. | Funding/OI/long-short ratio futures (đọc đòn bẩy). | Binance fapi funding/OI/LSR (không key) | `{"derivs": [{"symbol": "BTCUSDT", "mark_price": 85246.55378986, "funding_rate": 3.869e-05, "next_funding_time": 1790928000000, "open_interest": 98109.581, "ls_r` | available |

## scan.py — 6 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| stock_screener | ['filters', 'max_pe', 'min_roe', 'limit', 'technical'] | Screen universe by valuation and quality. Use when hunting candidates. | Lọc 1522 mã 3 stages (universe→fundamentals→technical). | vnstock listing + fundamentals + local filters (3 stages) | `{"universe": 1523, "filters": {}, "candidates": [{"symbol": "DPP", "name": "CTCP Dược Đồng Nai"}, {"symbol": "SDA", "name": "CTCP Simco Sông Đà"}, {"symbol": "C` | available |
| signals_screener_columns | ['group', 'search'] | Screener column catalog (valuation/quality/universe/price). Use to build filters. | Catalog cột lọc để build filters. | local catalog | `{"count": 2, "group": "valuation", "search": null, "columns": {"pe": {"group": "valuation", "desc": "Price / trailing earnings (P/E). Lower is cheaper."}, "mark` | available |
| signals_technical | ['symbol', 'interval', 'indicators'] | Full technicals rating from local candles on 1D/1W/1M. Use for timing entries. | Technicals đầy đủ + RS/pos_52w/sma150/patterns/Hỗ trợ-kháng cự. | vnstock candles (250d) → pandas technicals local | `{"symbol": "VCB", "interval": "1D", "rsi14": 39.23, "stoch_k": 2.63, "stoch_d": 4.8, "cci20": -125.54, "adx14": 12.12, "macd": {"line": -0.3102, "signal": -0.13` | available |
| sector_performance | ['level', 'top_n'] | GICS heatmap rows. Use for sector rotation reads. | Heatmap GICS (đọc luân chuyển ngành). | Vietstock GetHeatmapGICS | `{"level": 1, "rows": [{"IndustryCode": 10, "ParentCode": 0, "Level": 1, "DisplayOrder": 0, "IndustryName": "Năng lượng", "StockFullName": null, "ImageURL": "/c` | available |
| money_flow | ['symbols'] | Compose foreign flow: DNSE WS then Vietstock cross-check. Use for smart money. | NN mua/bán: DNSE WS → Vietstock cross-check. | DNSE WS → Vietstock nn_chart → unavailable | `{"primary": "vietstock", "flow": [["/Date(1790911058990)/"], [{"TradingDate": "/Date(1788714000000)/", "BuyVol": 46533428, "BuyVal": 1813.559809, "SellVol": 651` | available |
| alert_check | ['rules'] | Evaluate price/RSI rules against live quotes. Use for live watch. | Đánh giá rules giá/RSI trên quotes live. | vnstock quote/candles + Redis cross-state | `{"rules": 1, "evaluated": 1, "triggered": [{"symbol": "VCB", "metric": "price", "price": 57300.0, "op": ">", "threshold": 50.0}]}` | available |

## compute.py — 20 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| stock_forensic | ['symbol', 'detail', 'periods_n'] | Beneish M-Score + Piotroski F-Score from FULL detailed statements (P15). | M-Score Beneish + Piotroski F từ FULL detail (P15). | Vietstock detail statements → Beneish/Piotroski local | `{"symbol": "FPT", "dsri": 0.9772, "gmi": 1.0961, "aqi": 1.0107, "sgi": 1.1049, "sgai": 0.9951, "lvgi": 1.1257, "tata": 0.0349, "m_score": -2.0589, "m_partial": ` | available |
| snapshot_history | ['kind', 'days'] | Daily-snapshot history saved by the worker. Use for data that vanishes. | Lịch sử snapshot ngày do worker lưu (data hay mất). | PG daily_snapshots (worker 17:15 VN) | `{"kind": "macro_curated", "count": 2, "rows": [{"date": "2026-10-02", "kind": "macro_curated", "payload": {"fx55_t1": {"rows": [{"name": "Tỷ giá trung tâm (từ 0` | available |
| valuation_run | ['symbol', 'btype', 'method'] | PER/PB ensemble with DCF-lite. Use for fair-value ranges. | PER/PB ensemble + DCF-lite (vùng giá hợp lý). | vs_overview + vn quote → per_pb/DCF local | `{"symbol": "VCB", "price": 57400.0, "method": "per_pb"}` | available |
| fred_series | ['series_id', 'limit', 'spark'] | FRED observations. Use for US macro context. | Chuỗi FRED (bối cảnh macro Mỹ, cần key). | FRED API (FRED_API_KEY) | `{"series": "DGS10", "points": [{"t": "2026-09-30", "v": "5.29"}, {"t": "2026-09-29", "v": "5.26"}, {"t": "2026-09-28", "v": "5.24"}]}` | available |
| world_macro_country | ['iso3', 'indicator', 'limit'] | WorldBank series per country. Use for global GDP/CPI/debt context. | Chuỗi WorldBank theo quốc gia (GDP/CPI/nợ). | WorldBank API v2 | `{"country": "VNM", "indicator": "NY.GDP.MKTP.KD.ZG", "points": [{"t": "2025", "v": 8.01882998978245}, {"t": "2024", "v": 7.03955197123018}, {"t": "2023", "v": 4` | available |
| world_fear_greed | ['limit'] | Crypto fear/greed index. Use for risk-appetite reads. | Chỉ số sợ hãi/tham lam crypto (đọc risk-appetite). | alternative.me API | `{"series": [{"t": "1790899200", "v": "72", "label": "Greed"}, {"t": "1790812800", "v": "74", "label": "Greed"}, {"t": "1790726400", "v": "71", "label": "Greed"}` | available |
| sentiment_score | ['symbol', 'limit'] | Crowd sentiment from Fireant posts, Groq-scored. Use for hype risk. | Sentiment đám đông từ Fireant (Groq chấm, fallback heuristic). | Fireant posts → Groq (fallback heuristic likes) | `{"symbol": "VCB", "posts": 3, "score_heuristic": -0.25}` | available |
| insider_trading | ['symbol', 'limit'] | Insider deals via vnstock Company. Use for informed-flow reads. | Giao dịch nội bộ (rỗng = không có, đúng data). | vnstock Company VCI→KBS | `{"symbol": "VCB", "deals": []}` | available |
| stock_overview | ['symbol'] | Trading info plus company profile. Use for quick dossiers. | Hồ sơ nhanh 1 mã (trading info + profile). | vs_trading_info + vs_overview + vn_company | `{"trading": {"StockCode": "VCB", "TradingDate": "/Date(1790911060003)/", "KLCPLH": 8355675094, "KLCPNY": 8355675094, "PriorClosePrice": 57600, "CeilingPrice": 6` | available |
| company_events | ['symbol', 'types'] | Classified disclosures and corporate actions. Use for event calendars. | Sự kiện phân loại từ công bố. | vs_documents + company (classify local) | `{"symbol": "VCB", "events": [{"FileExt": ".pdf ", "UpdateTime": null, "TotalRow": 487, "FileInfoID": 559412, "Url": "https://static2.vietstock.vn/data/HOSE/2026` | available |
| financial_statements | ['symbol', 'period', 'statement', 'periods_n'] | Mirror statements alias (v3 compat). Use for statement reads. | Alias đọc BCTC nhanh (wrap financeinfo mirror). | vs_financeinfo mirror (alias v3) | `{"symbol": "VCB", "period": "quarter", "pages": "Q2/2025 ..."}` | available |
| financial_ratios | ['symbol', 'set', 'period', 'peers'] | Overview plus vnstock ratios merged. Use for ratio screens. | Bộ chỉ số + so peers. | vs_overview + vn_fundamentals merge | `{"symbol": "VCB", "period": "year", "ratios": {"data": [{"StockCode": "VCB", "TradingDate": "/Date(1790874000000)/", "ClosePrice": 57300, "ColorID": -1, "Change` | available |
| peer_compare | ['symbol', 'peers', 'metrics'] | Head-to-head overview rows. Use when picking tickers. | So trực tiếp tối đa 6 mã. | overview batch (cap 6) | `{"rows": [{"symbol": "VCB", "data": [{"StockCode": "VCB", "TradingDate": "/Date(1790874000000)/", "ClosePrice": 57300, "ColorID": -1, "Change": -300, "PerChange` | available |
| signals_scan | ['universe', 'exchange', 'max_symbols'] | Donchian-20d breakout scan. Use to hunt momentum across the market. | Quét breakout Donchian-20d (0 hits = không có, đúng). | vn_reference pool + quote_history từng mã → Donchian local | `{"hits": [], "scanned": 3, "requested": 3}` | available |
| pattern_match | ['symbol', 'lookback', 'limit'] | Self-similarity of return windows by correlation. Use for analogies. | Quá khứ giống hiện tại bằng tương quan (analogy). | vnstock candles → correlation local | `{"symbol": "VCB", "best_corr": 0.379, "offset_bars": 30, "matches": [{"corr": 0.379, "offset_bars": 30}, {"corr": 0.323, "offset_bars": 29}]}` | available |
| event_stats | ['query', 'limit'] | GDELT event counts for a query. Use for base-rate checks. | Đếm sự kiện GDELT (base-rate). | GDELT API (cache 600s, retry 1) | `{"query": "vietnam", "articles": [{"title": "ĐT Việt Nam chuẩn bị sẵn sàng cho trận đại chiến ĐT Thái Lan", "url": "http://vov.vn/the-thao/dt-viet-nam-chuan-bi-` | available |
| compare_assets | ['assets', 'timeframe'] | Cross-asset last prices via yfinance. Use for allocation reads. | Giá chéo tài sản qua yfinance. | yfinance batch | `[{"ticker": "GC=F", "price": 4198.2998046875, "prev": 4186.7001953125}, {"ticker": "BTC-USD", "price": 85203.9375, "prev": null}]` | available |
| runs_list | ['id'] | Local run registry. Use to resume analysis sessions. | Registry runs local (trống = chưa chạy, đúng). | data/runs.jsonl local | `{"runs": []}` | empty |
| run_get | ['run_id'] | Local run registry fetch. Use to inspect past outputs. | Đọc 1 run đã lưu. | data/runs.jsonl local | `{"run_id": "x"}` | empty |
| doctor | [] | Local self-check: env keys present, package versions. Use before handoff. | Self-check env keys + versions. | local env + package versions | `{"mcp_sdk": "1.x", "vietstock_jwt": true, "dnse_keys": true, "redis": true, "database": true, "fred": true, "groq": true, "fireant": true}` | available |

## corp.py — 9 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| dividends_splits | ['symbol', 'region', 'limit'] | Cash dividends and share issues/splits. Use for payout history. | Cổ tức tiền mặt + phát hành/tách (lịch sử chi trả). | vnstock Company.events → yfinance actions (world) | `{"symbol": "VCB", "region": "vn", "events": [{"event_code": "DIV", "title": "Cash Dividend - Year 2025 - 450 VND", "exright_date": "2026-07-23T00:00:00", "recor` | available |
| holders | ['symbol', 'region', 'kind'] | Shareholder and institutional holder tables. Use for ownership reads. | Bảng cổ đông/tổ chức (sở hữu). | vnstock shareholders → yfinance holders (world) | `{"symbol": "VCB", "region": "vn", "kind": "all", "holders": [{"symbol": "VCB", "share_holder": "Ngân Hàng Nhà Nước Việt Nam", "quantity": 6250338579, "share_own` | available |
| event_calendar_vn | ['event', 'symbol', 'limit'] | Vietstock corporate-action calendar. Use for dividend/meeting/listing dates. | Lịch cổ tức/niêm yết/ĐHĐCĐ Vietstock. | Vietstock /data/eventstypedata | `{"event": "dividends", "symbol": "VCB", "events": [{"event_id": 223751, "code": "VCB", "note": "Trả cổ tức  năm 2025  bằng tiền, 450 đồng/CP", "ex_date": "2026-` | available |
| block_trades | ['symbol', 'from_date', 'to_date', 'limit'] | Matched vs negotiated put-through splits per day. Use for dark-pool-style reads. | Tách khớp lệnh vs thỏa thuận theo ngày (đọc dòng tiền lớn). | Vietstock /data/gettradingresult (MT vs PT) | `{"symbol": "VCB", "days": [{"date": "2026-10-02", "close": 57300, "mt_vol": 886900, "mt_val": 50930200000.0, "pt_vol": 0, "pt_val": 0.0, "pt_pct": 0.0}, {"date"` | available |
| analyst_consensus | ['symbol', 'limit'] | Analyst ratings and price targets parsed from report titles. Use for street views. | Rating + target từ titles báo cáo (rỗng = không báo cáo mới). | scrape Vietstock /bao-cao-phan-tich (titles parse) | `{"symbol": "VCB", "reports": []}` | available |
| ipo_calendar_vn | [] | HNX auction calendar plus announcement fallback. Use for upcoming supply. | Lịch đấu giá HNX + thông báo (thường rỗng, đúng). | scrape HNX lich-dau-gia + tin-cong-bo | `{"auctions": [], "announcements": [{"posted": "23/09/2026 16:29", "title": "Không tổ chức bán đấu giá theo lô cổ phần của Tổng công ty Thủy sản Việt Nam - CTCP ` | available |
| futures_basis | [] | VN30F1M price minus VN30 spot. Use for premium/discount reads. | F1M − VN30 spot (premium/discount, fallback ohlc). | DNSE latest_trade/ohlc − vnstock VN30 spot | `{"futures": 1888.0, "spot": 1882.11, "basis": 5.89, "basis_bps": 31.3}` | available |
| planned_targets | ['symbol', 'years'] | Business-plan targets (CTKH: planned revenue/profit by year). Use as expectation anchor. | Kế hoạch DT/LN năm của DN — neo kỳ vọng (P15 live). | Vietstock CTKH chain (session-gated) | `{"symbol": "FPT", "unit": "VNDbn", "years": [2025, 2026], "rows": [{"name": "Doanh thu kế hoạch", "planned_target_id": 5, "plan": {"2025": 75400.0, "2026": 5858` | available |
| financial_detail | ['symbol', 'statement', 'periods_n'] | FULL detailed statements, every line item per period. Use for deep BCTC reads. | FULL BCTC từng dòng theo kỳ (đọc sâu, P15 revive). | Vietstock /data/* chain object-array (permission filter) | `{"symbol": "FPT", "statement": "KQKD", "unit": "VNDbn", "periods": ["Q1/2026", "Q2/2026"], "rows": [{"norm_id": 2206, "name": "1. Doanh thu bán hàng và cung cấp` | available |

## quant.py — 9 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| quant_backtest | ['symbol', 'cost_bps', 'strategy', 'slippage_bps', 'benchmark'] | Buy-and-hold backtest with costs over available history. Use for baseline stats. | Backtest buy-hold có phí (baseline). | vnstock candles → backtest local | `{"symbol": "VCB", "strategy": "buy_hold", "benchmark": "VNINDEX", "gross_return": -0.0687, "net_return": -0.0717, "bars": 285, "cost_bps": 10.0, "slippage_bps":` | available |
| quant_risk | ['returns', 'periods_per_year'] | Sharpe, max drawdown and win rate from a return series. Use to gate models. | Sharpe/DD/win từ chuỗi lợi suất (cổng mô hình). | thuần local (returns input) | `{"sharpe_proxy": 12.8759, "max_drawdown": 0.005, "win_rate": 0.6667, "n": 3, "periods_per_year": 252}` | available |
| quant_factors | ['symbol', 'lookback'] | Momentum, volatility and drawdown factors from candles. Use to expand features. | Momentum/vol/DD từ nến (mở rộng features). | vnstock candles → local | `{"symbol": "VCB", "lookback": 60, "momentum_20d_pct": -1.21, "vol_20d_ann_pct": 15.44, "max_dd_20d_pct": -4.5, "max_dd_full_pct": 13.57}` | available |
| scenario_simulate | ['scenario', 'symbol', 'shock_pct'] | Apply a price shock to latest close and report P/L per 1000 shares. Use for sizing. | Shock giá → P/L trên 1000cp (cỡ vị thế). | vnstock candles → local | `{"scenario": "t", "symbol": "VCB", "last_close": 57.3, "shock_pct": -5.0, "shocked_price": 54.43, "pnl_per_1000_shares": -2870.0, "assumptions": ["linear shock,` | available |
| correlation_matrix | ['symbols', 'days'] | Pairwise Pearson correlation of daily returns. Use for diversification reads. | Tương quan Pearson cặp mã (đa dạng hóa). | vnstock candles inner-join → local | `{"symbols": ["VCB", "HPG"], "common_dates": 91, "matrix": {"VCB": {"VCB": 1.0, "HPG": 0.5045}, "HPG": {"VCB": 0.5045, "HPG": 1.0}}, "date_note": "business-day w` | available |
| seasonality | ['symbol', 'window'] | Rolling-window return stats per calendar month. Use for seasonal bias. | Stats theo tháng (bias mùa vụ). | vnstock 400d → local buckets | `{"symbol": "VCB", "window": 21, "months": {"1": {"n": 22, "mean_pct": 4.67, "median_pct": -1.55, "hit_rate": 0.32, "best_pct": 33.8, "worst_pct": -5.48}, "2": {` | available |
| backtest_strategies | ['symbol', 'strategy', 'fast', 'slow', 'cost_bps', 'rsi_low', 'rsi_high', 'months', 'quarters'] | Rule-based backtests beyond buy-and-hold (sma/momentum/rsi_meanrev + month filter). Use to compare timing rules. | Backtest sma/momentum vs buy-hold. | vnstock 365d → local engine | `{"symbol": "VCB", "strategy": "sma_cross", "fast": 10, "slow": 30, "cost_bps": 10.0, "trades": 6, "net_return": -0.0872, "max_drawdown": 0.2008, "win_rate": 0.3` | available |
| portfolio_optimize | ['symbols', 'objective', 'days'] | Long-only weights by rule. Use for allocation starting points. | Tỷ trọng long-only (numpy, fallback equal). | vnstock candles → numpy-only local | `{"symbols": ["VCB", "HPG"], "objective": "max_sharpe", "weights": {"VCB": 0.5, "HPG": 0.5}, "common_dates": 156, "notes": ["long-only heuristic; rebalance and c` | available |
| param_sweep | ['symbol', 'strategy', 'fast_range', 'slow_range', 'cost_bps'] | Grid-search strategy lookbacks, ranked by net return. Use to avoid overfit picks. | Grid lookbacks ≤30 combos (chống overfit). | vnstock 365d → local grid (≤30 combos) | `{"symbol": "VCB", "strategy": "sma_cross", "combos_evaluated": 8, "ranked": [{"fast": 10, "slow": 20, "trades": 9, "net_return": 0.071, "max_drawdown": 0.142, "` | available |

## brief.py — 7 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| brief_build | ['scope', 'date', 'calendars'] | Compose morning brief from news, odds and calendars. Use at session start. | Brief sáng từ news+odds+calendars. | fear_greed + Vietstock/GDELT news + categories + yf pins | `{"scope": "vn", "sections": {"world_pins": {"series": [{"t": "1790899200", "v": "72", "label": "Greed"}, {"t": "1790812800", "v": "74", "label": "Greed"}, {"t":` | available |
| news_market | ['limit', 'sources'] | Market news: Fireant posts first, GDELT fallback. Use for catalyst checks. | Tin thị trường: Fireant trước, GDELT fallback. | Fireant → GDELT (fallback trong tool) | `{"posts": [{"id": null, "user": null, "text": "Tổng thống Nga Vladimir Putin ngày 1.10 cảnh báo nguy cơ xung đột toàn cầu, kêu gọi phương Tây từ bỏ thế bá quyền` | available |
| news_symbol | ['symbol', 'limit', 'sources'] | Symbol news: Fireant posts about the ticker, GDELT fallback. Use to verify rumors. | Tin theo mã: Fireant posts + GDELT fallback. | Fireant → GDELT (fallback trong tool) | `{"symbol": "VCB", "posts": [{"id": null, "user": null, "text": "Lãi suất Vietcombank hiện dao động từ 0,1-6%/năm. Khách hàng gửi 500 triệu đồng kỳ hạn 24 tháng ` | available |
| economic_calendar | ['scope', 'limit'] | Macro series catalogue as event proxy. Use for data-availability checks. | Catalog macro (proxy lịch sự kiện). | vs_categories (proxy catalogue) | `{"scope": "vn", "series": [{"category_id": 7, "name": "1. Tài khoản quốc gia (GDP)", "has_data": false}, {"category_id": 73, "name": "GDP danh nghĩa", "has_data` | available |
| corporate_calendar | ['symbol', 'limit'] | Disclosures feed as corporate actions. Use for dividend/meeting scans. | Feed công bố thô (quét cổ tức/họp). | Vietstock GetDocument | `{"symbol": "VCB", "docs": [{"FileExt": ".pdf ", "UpdateTime": null, "TotalRow": 487, "FileInfoID": 559412, "Url": "https://static2.vietstock.vn/data/HOSE/2026/N` | available |
| sbv_rates | [] | SBV policy and interbank rates, scraped static page. Use for rate regime. | Lãi suất điều hành + liên NH (scrape SBV). | scrape sbv.gov.vn (static) | `{"policy": [{"name": "Lãi suất tái chiết khấu", "value": "3,000%"}, {"name": "Lãi suất tái cấp vốn", "value": "4,500%"}], "interbank": [], "as_of": null}` | available |
| macro_events_vn | [] | NSO release listings with reference and next dates. Use for data calendar. | Lịch công bố NSO + ngày tham chiếu/kế tiếp. | scrape nso.gov.vn (releases) | `{"releases": [{"indicator": "CPI", "title": "Chỉ số giá tiêu dùng (CPI), chỉ số giá vàng và chỉ số giá đô la Mỹ tháng Tám và 8 tháng năm 2026", "url": null, "re` | available |

## intel.py — 7 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| world_prediction_odds | ['query', 'limit', 'tag'] | Polymarket odds via jina proxy to Gamma, then direct. Use for Fed/macro odds. | Odds Polymarket (outcomes+prob, sort vol24h). | Gamma API qua jina proxy → direct | `{"source": "https://r.jina.ai/https://gamma-api.polymarket.com", "events": [{"title": "Steelers vs. Browns", "slug": "nfl-pit-cle-2026-10-02", "tags": ["Sports"` | available |
| polymarket_event | ['slug'] | One Polymarket event detail by slug (every market + odds). Use to drill in. | Chi tiết 1 event theo slug (mọi market + odds). | Gamma /events?slug (outcomes/prices) | `{"slug": "nfl-pit-cle-2026-10-02", "title": "Steelers vs. Browns", "description": "In the upcoming NFL game, scheduled for October 1 at 8:15PM ET:\nIf Steelers ` | available |
| geo_intel | ['topic', 'limit', 'days'] | Geopolitical coverage via GDELT. Use when geopolitics threatens markets. | Tin địa chính trị qua GDELT. | GDELT API (cache 600s) | `{"query": "Vietnam", "articles": [{"title": "ĐT Việt Nam chuẩn bị sẵn sàng cho trận đại chiến ĐT Thái Lan", "url": "http://vov.vn/the-thao/dt-viet-nam-chuan-bi-` | available |
| assets_rotation | [] | Cross-asset 1y momentum classes into RISK-ON/OFF. Use for allocation reads. | Momentum 1y → RISK-ON/OFF (phân bổ). | yfinance 2y → rule local | `{"regime": "neutral/mixed", "signals": ["equities momentum up", "crypto negative (risk-off lean)"], "drivers": {"^GSPC": {"last": 7666.4501953125, "chg_1y_pct":` | available |
| compare_equities | ['symbols', 'metrics'] | Head-to-head overview rows and momentum. Use when picking tickers. | Overview + momentum head-to-head (chọn mã). | vs_overview + vn quote batch | `{"rows": [{"symbol": "VCB", "quote": {"symbol": "VCB", "time": 1790911726385, "exchange": "HOSE", "ceiling_price": 61600, "floor_price": 53600, "reference_price` | available |
| evidence_bundle | ['claim_ids', 'calc_ids'] | Lock weighted conclusion by evidence bundle. Use last for final verdict. | Khóa kết luận có trọng số (dùng cuối để verdict). | local (claims/calc ids) | `{"claims": ["c1"], "calc_ids": [], "locked": true, "note": "bundle closes server-side; attach calc ids at synthesis"}` | available |
| oracle_meta | [] | Aggregator snapshot plus source health. Use for dashboard meta. | Snapshot aggregator + sức khỏe nguồn. | yf pins + source_status | `{"pins": {"world": [{"ticker": "^GSPC", "last": 7666.4502, "spark": [7743.4102, 7683.6899, 7670.8398, 7651.54, 7666.4502]}, {"ticker": "^IXIC", "last": 26871.59` | available |

## watchlist.py — 12 tools

| Tool | Params | Descriptor | Mô tả chi tiết (TV) | Source data (upstream) | Dữ liệu mẫu live 2026-10-02 | Avail |
|---|---|---|---|---|---|---|
| watchlist_create | ['name'] | Create a named watchlist. Use to start tracking a symbol group. | Tạo watchlist theo tên. | PG opentrading_mcp → fallback file JSON | `{"id": 1, "name": "tmp-full135", "symbols": []}` | available |
| watchlist_list | [] | List all watchlists with their symbols. Use to recall tracking state. | Liệt kê watchlists + mã. | PG/file | `{"watchlists": [{"id": 1, "name": "tmp-full135", "symbols": [null]}]}` | available |
| watchlist_get | ['list_id'] | Get one watchlist's symbols by id. Use before quoting a saved set. | Lấy mã 1 watchlist theo id. | PG/file | `{"id": 1, "name": "tmp-full135", "symbols": [null]}` | available |
| watchlist_add | ['list_id', 'symbols'] | Add symbols (deduped, uppercase) to a watchlist. Use to track more. | Thêm mã (dedupe, uppercase). | PG/file (dedupe, uppercase) | `{"list_id": 1, "added": 1, "symbols": ["VCB"]}` | available |
| watchlist_remove | ['list_id', 'symbols'] | Remove symbols from a watchlist. Use to trim tracking. | Bớt mã khỏi watchlist. | PG (transaction, không fallback) | `{"list_id": 1, "symbols": []}` | available |
| watchlist_delete | ['list_id'] | Delete a watchlist and its items (cascade). Use to clean up. | Xóa watchlist + items (cascade). | PG/file (cascade) | `{"deleted": 1}` | available |
| watchlist_update | ['list_id', 'name'] | Rename a watchlist. Use sparingly; names are unique labels. | Đổi tên watchlist. | PG/file | `{"id": 1, "name": "tmp-full135b", "symbols": ["VCB"]}` | available |
| alert_create | ['symbol', 'op', 'threshold', 'metric'] | Create a stored alert rule (input to alert_check). Use for live watch. | Tạo rule alert (input cho alert_check). | PG/file (validate op) | `{"symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": true, "id": 1}` | available |
| alert_list | [] | List stored alert rules (active and paused). Use before alert_check. | Liệt kê rules (active + paused). | PG/file | `{"rules": [{"id": 1, "symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": true}]}` | available |
| alert_delete | ['rule_id'] | Delete a stored alert rule by id. Use to clean up alerts. | Xóa rule theo id. | PG/file | `{"deleted": 1}` | available |
| alert_pause | ['rule_id'] | Pause a stored alert rule (active=false). Use to silence alerts. | Tạm dừng rule. | PG/file (active=false) | `{"id": 1, "symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": false, "state": "paused"}` | available |
| alert_resume | ['rule_id'] | Resume a paused alert rule (active=true). Use to re-enable alerts. | Bật lại rule. | PG/file (active=true) | `{"id": 1, "symbol": "VCB", "metric": "price", "op": ">", "threshold": 999999.0, "active": true, "state": "resumed"}` | available |

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
