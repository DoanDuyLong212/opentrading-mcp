# Skills & Tools — bản v4 FULL (MCP-server TỰ LẤY trực tiếp, 8010 chỉ fallback)

> Nguyên tắc chốt: hạn chế lấy dữ liệu TỪ port 8010. MCP-server học CÁCH 8010 lấy
> (cùng libs, cùng URLs, cùng params) rồi tự fetch trực tiếp từ upstream + cache riêng.
> 8010/8001 chỉ là fallback khi upstream chết.
> Quy ước tên skill: `^[a-z0-9]+(-[a-z0-9]+)*$` trùng tên thư mục `SKILL.md`.
> Quy ước tên tool: `snake_case`, prefix theo nguồn `vs_|vn_|yf_|dnse_|world_|signals_|quant_|brief_|intel_`.
> 1 tool = 1 endpoint family. Cấm gộp `a / b / c` trong 1 dòng như v3.
> Xóa: `investor_flow` (0 hit trong repo), `TCBS/vn-stock-sdk` (0 hit, bỏ từ vnstock v4), `Feat:*` (doc cũ),
> `Vietstock gold` (không tồn tại — vàng SJC từ Retail BTMC).

## Bảng 0 — Công thức 8010 đang dùng (MCP-server copy nguyên, đã verify file thật)

| Mảng | 8010 lấy như nào (file thật) | MCP-server làm giống vậy |
|---|---|---|
| Realtime VN | `signal_viewer/realtime.py` RealtimeFeed → DNSE WS msgpack `wss://ws-openapi.dnse.com.vn/v1/stream?encoding=msgpack` sub `ohlc.1.json [VN30F1M,VNINDEX,VN30]` + `dashboard/dnse_ws.py` bản JSON sub thêm `market_index.VNINDEX/VN30.json + foreign.*.json`, auth HMAC `DNSE_API_KEY:ts:nonce` | Mở WS trực tiếp cả 2 encoding, loop 5s build snapshot, cache riêng |
| Giá/OHLC VN | `dashboard/data_fetcher.py`: `Quote(history VCI daily)` + `Market.index/equity ohlcv(length=2,1D)` + `fetch_market_status_rest (DNSEClient.get_latest_trade x167 ThreadPool20 TTL60s)` + `fetch_market_status_from_db (Market.equity(list).quote() 1 req = price_board)` | Gọi vnstock + DNSE REST trực tiếp + cache riêng |
| Intraday F1M | `signal_engine.py:244 Quote(VN30F1M,KBS,resolution=1m)` quét 120 ngày → resample 15m, fix `14:30→14:45` + `loader_dnse.py GET /price/ohlc?type=derivative&resolution=15&from=2018-08-01&pageSize=10000&time=cursor→nextTime` | Cùng 2 nguồn, pickle + cache riêng |
| BCTC trả phí | `mcp/tools/vietstock/financial.py _build_params`: `GET /` lấy `__RequestVerificationToken` → `POST /Account/Login {Email,Password}` → `CookieLogin JWT (exp 2026-10-02)` → `POST /FinancialStatement/BCTC_GetChiTieuForTable {BusinessTypeId 1/2/3/5, ReportComponentCodes CD,KQ,LCTT}` → `POST /BCTC_LoadReportData_Async {ReportNormIds, ListParams 3y×tids[2,3,4,5,9]=15 cols; stock_full 4y×[1,2,3,4,5,9,12]=28 cols}` | Cùng flow login + params, bảng terms/norms/values riêng |
| BCTC mirror free | `signal_viewer/vietstock_finance.py stock_finance`: `POST /data/financeinfo {Code,Page 1-3,PageSize=4,ReportTermType=2 quarter/1 year,ReportType=BCTQ,Unit=1}` = 12 quý / năm | Cùng params, cache file 6h |
| Company/snapshot | `POST /company/tradinginfo {code,s=0}` + `POST /data/GetStockDeal_OverviewTrading {stockCode}` → EPS/BVPS/PE/PB/MCap/Ceiling/Floor/Room | Cùng 2 endpoints, upsert snapshot riêng |
| Reports/PDF | `POST /CompanyReport/CompanyReportSearch {stockCode,categoryId=2,pageSize≤50}` + `POST /data/GetDocument {code,pageSize=60}` | Cùng flow, Mongo riêng |
| Industry | `POST /FinancialStatementSector/GetTreeViewIndustryGICS` + `GetBusinessTypeIDCompanyByGICS {IndustryID}` + `POST /Data/GetHeatmapGICS (live)` | Cùng 3 endpoints |
| Market/NN Vietstock | `POST /data/getmarketprice {type=2}` + `GeneralMarket_GetMarketIndexVNData` + `KQGDGiaoDichNDTNNChart/TuDoanhChart` + `GetTopStockLiquidity` + `GetGICSIndexMain` + `GetCurrency` + `marketinfo` + `dc.vietstock.vn SearchArticleNewAsync` | Cùng endpoints, mem TTL 300s |
| Vĩ mô VN | `vietstock_macro.py` + `dashboard/vietstock_macro.py`: `POST /Macro/GetIndicatorCategoryData (~60 cats)` + `POST /Macro/GetReportDataByIDs {termTypeID 1 Ngày/2 Tháng/3 Quý/4 Năm/5 YTD/6 MoM/7 YoY/8 QoQ, type=CATEGORY, listID[]=cat}`; XNK `63→64/65 termTypeID=2`; curated 27 ids | Cùng endpoints + termType map |
| Reference/ICB | `vnstock Reference().equity.list_by_exchange/group/industry + industry.list/sectors + company().info/shareholders/officers/subsidiaries + Listing().all_symbols()` | Gọi vnstock trực tiếp |
| Fundamentals vnstock | `Fundamental().equity(sym).*(quarter/year)` + `Finance.ratio(year/ttm, source KBS)` + `Company(VCI).info()` | Gọi trực tiếp, cache pkl |
| Vàng/FX VN | `vn_macro()` + `fetch_vn_gold_fx()`: `vnstock.explorer.msn Quote(USDVND/XAUUSD 35d 1D)` + `Retail().gold(source=btmc: SJC/NHẪN)` + `Retail().exchange_rate() (VCB USD)` + SJC webgia qua jina | Cùng 3 nguồn, cache 15' (900s, 180s nếu thiếu SJC) |
| World indices/commo | `data_fetcher.py`: `yf.download(batch,2d/1d,group_by=ticker)` GLOBAL 9 + COMMO 13 + WORLD 43; `Ticker(^TNX,2YY=F).history(1d)` yield; loop 60s global/commo TTL120, loop 300s world TTL300 | Gọi yfinance trực tiếp, loop riêng |
| Oracle/world sâu | `server.py oracle_markets ~40 6 groups 1mo/1d` + `macro_regime_signals 7×2y` + `mega_flows Nasdaq screener cap≥2B + 26 intl batch300 1mo/1d` + `alloc 6 max daily/weekly → pkl` | Cùng tickers + params, cache 900/1800s + file 24h/7d |
| Odds Polymarket | `fetch_polymarket_jina()`: `r.jina.ai` proxy Gamma API, fetch 2 lần (all + tag fed), sort volume24h, cache 45' | Cùng proxy + cache; chain: jina → Kalshi direct → Manifold |
| Intel/geo | `intel_sources.py`: GDELT geojson, Celestrak TLE, OpenSky, adsb, Telegram HTML, State Dept RSS — đều direct | Port các hàm direct, bỏ qua 8010 |
| Council/intel AI | `oracle.py`: Groq `qwen/qwen3.6-27b` | Gọi Groq trực tiếp |
| Foreign flow | DNSE WS `T==f → dash:foreign:* → SCAN net=buy-sell` + Vietstock `KQGDGiaoDichNDTNNChart` (cross-check). `investor_flow` không tồn tại | DNSE primary, Vietstock secondary |
| Forensic | `forensic.py` tính local từ BCTC (13 trường output) | Port nguyên module, tính local |
| Cache | PG ohlcv/macro + Redis `dash:ohlc/index/foreign/market_status/last_update/spark/yf (TTL 12h, yf 60-300s)` + Mongo news | Cache riêng MCP-server (SQLite/PG + TTL: 5s/60s/300s/3600s) |

## Bảng 1 — Skills v4 (10 nhóm × 58 skills, Descriptor = frontmatter SKILL.md)

| Nhóm | Skill | Descriptor (frontmatter description) | Tools gọi (v4) | Nguồn trực tiếp |
|---|---|---|---|---|
| market-data | `vn-quotes` | Fetch realtime and OHLCV quotes for VN tickers and indices with automatic source fallback. Use when any price, candle, or market snapshot is needed. | `symbol_lookup, vn_quote_history, vn_equity_quote_batch, vn_index_ohlcv, dnse_ws_snapshot, dnse_market_status` | vnstock VCI→KBS + DNSE WS/REST |
|  | `vn-financials` | Fetch Vietnamese financial statements with selectable report type, period, and range. Use when income, balance sheet, or cashflow data is needed for any stock. | `vs_financial_values, vs_financeinfo, vs_financial_terms, vs_financial_norms` | Vietstock JWT → financeinfo mirror → vnstock |
|  | `vn-ratios` | Fetch grouped financial ratios (profitability, liquidity, leverage, efficiency, valuation). Use when ratio analysis or peer benchmarking is needed. | `vs_overview_trading, vn_fundamentals, vs_financial_values` | Vietstock CSTC + Finance.ratio KBS |
|  | `vn-macro` | Fetch Vietnamese macro indicators across 48 indicators and 11 groups. Use when GDP, CPI, trade, labour, money, or rates context is needed. | `vs_categories, vs_indicator_data, vs_xnk_detail` | Vietstock categories direct |
|  | `derivatives-assets` | Fetch VN30F1M derivatives plus metals, oil, forex, BTC, and crypto data. Use for futures basis, gold, FX, or crypto inputs. | `dnse_vn30f1m_live, dnse_ohlc_history, yf_commodities, vn_forex_ohlcv, vn_crypto_ohlv, vn_retail_gold` | DNSE + yfinance + vnstock |
|  | `prediction-search` | Search prediction-market events and read odds, liquidity, resolution, and end dates. Use when forecasting Fed, macro, or election outcomes. | `world_prediction_odds` | jina→Gamma → Kalshi → Manifold |
|  | `intl-macro` | Fetch international macro series for any country and indicator. Use when global GDP, CPI, debt, or trade context is needed. | `fred_series, world_macro_country` | FRED → WorldBank → Comtrade |
| analysis-equity | `technical` | Analyze technical setup with RSI, MACD, Bollinger, MA, Ichimoku, ATR, Stochastics, ADX, OBV, VWAP plus Wyckoff, Elliott, and Fibonacci structure. Use when timing entries, exits, or trend regimes. | `vn_quote_history, signals_technical` | Tính local từ candles tự lấy |
|  | `fundamental` | Analyze financial statements for forensic warnings using M-Score, Piotroski, Dechow, red flags, and cross-checks. Use when judging earnings quality or accounting risk. | `vs_financial_values, vs_financeinfo, stock_forensic` | forensic.py port |
|  | `revenue-debt` | Track revenue, profit, and debt trends including CFO vs net income quality, leverage, and interest coverage. Use when assessing growth sustainability and balance-sheet safety. | `vs_financial_values, stock_forensic, vs_trading_info` | Vietstock + ratios tự tính |
|  | `valuation` | Value a stock with the method fitting its industry (banks P/B, brokers P/B+ROE, insurers P/EV, others DCF+PER ensemble). Use when estimating fair value or margin of safety. | `valuation_run, vn_fundamentals, vs_overview_trading` | Port ValuationManager local |
|  | `information` | Gather company profile, shareholders, leadership, corporate events, and insider trades. Use when researching what a company is and who runs and owns it. | `vs_company_info, vs_trading_info, vn_company, vs_documents, vn_reference, insider_trading` | Vietstock + vnstock Reference |
|  | `news` | Collect news from Yasuyuki-style official sources only (Fireant, Vietstock reports, mainstream RSS). Use when checking catalysts or verifying market rumors. | `news_symbol, news_market, vs_news_search, vs_reports_search, macro_reports` | Fireant + Vietstock + RSS |
|  | `sentiment` | Score per-symbol sentiment from community posts and news flow. Use when gauging crowd positioning or hype risk. | `sentiment_score` | Fireant + Groq |
|  | `history` | Find similar historical setups of a stock using feature matching and cluster maps. Use when asking what happened last time conditions looked like this. | `pattern_match, vn_quote_history` | Redis/PG + cluster pkl |
|  | `synthesis` | Synthesize multi-angle analysis into a weighted conclusion locked by evidence bundle. Use last, when producing the final investment verdict. | `evidence_bundle` | Khóa từ mọi nguồn trên |
| analysis-assets | `fixed-income` | Analyze bonds and the US yield curve including 2s10s spreads. Use when rates, curve, or credit context matters. | `yf_yield_curve, fred_series` | yfinance ^TNX/2YY=F + FRED |
|  | `gold-vn` | Compare Vietnamese SJC gold basis against world gold converted at FX. Use when pricing local gold premium or hedging. | `vn_retail_gold, vn_msn_fx_gold, vn_retail_fx` | Retail BTMC + MSN (không phải Vietstock) |
|  | `forex` | Track USDVND and major FX pairs. Use when currency moves affect earnings or flows. | `vn_forex_ohlcv, vn_retail_fx, vs_currency` | vnstock forex + Retail VCB + Vietstock |
|  | `crypto` | Track crypto spot and candles across coins and timeframes. Use when digital-asset regime affects risk appetite. | `vn_crypto_ohlv, yf_oracle_markets` | vnstock Market.crypto + yfinance |
|  | `derivatives` | Analyze VN30F1M futures basis, term structure, and intraday behavior. Use when trading or hedging via derivatives. | `dnse_vn30f1m_live, dnse_ohlc_history, dnse_orderbook` | DNSE WS + REST |
|  | `commodities` | Track gold, oil, and commodity prices. Use when input costs or energy exposure matter. | `yf_commodities, yf_oracle_markets` | yfinance → EIA (khi có key) |
| market-scan | `equities-screen` | Screen the equity universe by P/E, ROE, market cap, sector, breakout, and BCD signals. Use when hunting candidates. | `stock_screener, signals_scan, vn_reference` | vnstock ICB + models local |
|  | `breadth-scan` | Scan market breadth including advancers, decliners, ceiling, and floor counts per exchange. Use when judging rally health. | `market_snapshot, breadth_scan, market_movers, sector_performance` | Tính từ snapshot riêng |
|  | `assets-rotation` | Identify asset-class phases and rotation across equities, bonds, gold, FX, and crypto. Use when allocating across assets. | `assets_rotation, yf_oracle_markets, yf_regime_assets` | Regime classify port |
|  | `realtime-alerts` | Watch price, indicator, and risk thresholds including open positions. Use when monitoring live danger or entries. | `alert_check, dnse_market_status, oracle_meta` | Evaluator trên snapshot |
|  | `money-flow` | Track foreign flows, self-trading, and global mega flows. Use when following smart money. | `dnse_foreign_flow, vs_nn_flow, vs_selftrading, yf_mega_flows` | DNSE primary + Vietstock + Nasdaq/yf (xóa investor_flow/TCBS) |
|  | `insider-scan` | Scan abnormal insider buying and selling across tickers. Use when front-running informed flows. | `insider_trading` | Fireant insider direct |
|  | `dividend-scan` | Scan dividends, yields, and corporate actions. Use for income setups and event calendars. | `company_events, corporate_calendar` | Fireant + Vietstock GetDocument |
| quant | `quant-features` | Build and select predictive features from OHLCV, financials, and flows. Use when starting any model pipeline. | `quant_backtest, vn_quote_history, vs_financial_values` | PG/Redis riêng |
|  | `quant-labels` | Build and select labels including forward returns and triple-barrier outcomes. Use when defining what the model predicts. | `quant_backtest, signals_trade_log` | trade_log.json trực tiếp |
|  | `quant-split` | Split train-test with purging, embargo, and walk-forward schemes. Use before any training or evaluation. | `quant_backtest` | PG riêng |
|  | `quant-backtest` | Backtest a strategy with costs, slippage, benchmark, and regime filters. Use when measuring if a strategy survives reality. | `quant_backtest, quant_factors` | Sandbox local (8002 fallback) |
|  | `quant-risk` | Measure Brier score, win rate, drawdown, Sharpe, and profit factor against auto-trigger thresholds. Use when deciding if a model ships. | `quant_risk, signals_trade_log` | Tính từ trade_log |
|  | `quant-factors` | Mine and validate new factors from data and literature. Use when expanding the feature universe. | `quant_factors` | Sandbox local |
| morning-brief | `brief-vn` | Build the morning brief with overnight news, upcoming events, and corporate calendars for Vietnam. Use at session start. | `brief_build, economic_calendar, corporate_calendar, news_market, vs_news_search` | Fireant + RSS + Vietstock |
|  | `brief-world` | Build the world brief with overnight recap, global events, prediction odds, and economic calendar. Use for global context. | `brief_build, world_prediction_odds, economic_calendar, yf_market_pins` | RSS + GDELT + Kalshi/jina |
| intelligence | `geo-intel` | Report geopolitical hotspots, conflict escalation, and travel advisory levels with event frequency. Use when geopolitics threatens markets. | `geo_intel, source_status` | intel_sources port |
|  | `finance-intel` | Report cross-asset states, phases, and RISK-ON/OFF regime with sector rotation. Use when positioning across regimes. | `assets_rotation, source_status` | Tự tính + aggregator |
| critic-compare | `redteam` | Attack a thesis to find anomalies, holes, and severity-graded risks. Use before committing capital to any conclusion. | `evidence_bundle, scenario_simulate` | Bundles + sandbox |
|  | `premortem` | Assume the thesis failed and trace the most likely causes. Use when overconfidence is the biggest risk. | `evidence_bundle` | Bundles |
|  | `base-rate` | Check claims against historical base rates and event statistics. Use when a forecast sounds too good. | `event_stats` | GDELT + lifecycle |
|  | `thesis-ledger` | Keep a bull, bear, catalyst, and sizing ledger for every thesis. Use to force balanced bookkeeping. | `evidence_bundle` | Bundles |
|  | `guru-lens` | Cross-check against Buffett, Graham, Lynch, Dalio, and Marks philosophies and methods. Use when testing style fit. | `valuation_run, compare_equities` | Tính local |
|  | `compare-equities` | Compare securities head-to-head on ratios, growth, and price action. Use when picking between tickers. | `compare_equities, vn_fundamentals, vn_quote_history` | Ratios + candles tự lấy |
|  | `compare-assets` | Compare asset classes on return, risk, and regime behavior. Use when allocating. | `compare_assets, yf_oracle_markets` | Indices + commo tự lấy |
|  | `event-stats` | Statistically profile event types and their market aftermath. Use when pricing event risk. | `event_stats` | GDELT direct |
|  | `scenario-simulate` | Simulate what-if scenarios with explicit assumptions. Use when sizing under uncertainty. | `scenario_simulate` | Port simulate.py |
| glossary | `market-structure` | Explain ATO, ATC, odd lots, foreign room, bands, and T+ settlement. Use when market mechanics confuse the thesis. | — | references |
|  | `order-derivatives` | Explain order types, futures basis, leverage, and prediction-market resolution. Use for derivatives and odds mechanics. | — | references |
|  | `macro-vn` | Explain policy rates, OMO, and central exchange rates. Use when Vietnamese monetary policy matters. | — | references |
|  | `quant-risk` | Explain Sharpe, Sortino, max drawdown, walk-forward, overfitting, and Brier scores. Use when evaluation metrics mislead. | — | references |
|  | `forensic-terms` | Explain accruals, channel stuffing, DSO, DIO, and Beneish inputs. Use when reading forensic output. | — | references + forensic.py |
|  | `prediction-terms` | Explain liquidity, volume, and UMA resolution in prediction markets. Use when reading odds. | — | Gamma/Kalshi docs |
| engineering | `tdd-workflow` | Enforce test-first development with 80%+ coverage. Use when writing new features, fixes, or refactors. | `runs_list, run_get` | session store local |
|  | `systematic-debugging` | Debug systematically before proposing fixes. Use on any bug, failure, or surprise. | `run_get, doctor` | session store + doctor |
|  | `verification-loop` | Verify outputs against checklists before claiming done. Use before handoff or commit. | `doctor` | local |
|  | `skill-authoring` | Author new skills following naming, frontmatter, and disclosure rules. Use when expanding the library. | — | local |

## Bảng 2 — Tools v4 FULL (chia theo nguồn, 1 tool = 1 endpoint family)

### Nhóm A — Vietstock trả phí (JWT `VIETSTOCK_COOKIE_LOGIN`, exp 2026-10-02, check mỗi phiên)

| Tool | Parameters | Lấy trực tiếp như nào (copy 8010) | TTL/cache | Fallback |
|---|---|---|---|---|
| `vs_auth_status` | — | `POST /Account/GetAuthToken` sau `GET /` refresh CSRF → `{authenticated, jwt_expires_at}` | mem 300s | `session.json` → `.env` → Chrome SSO |
| `vs_categories` | — | `POST /Macro/GetIndicatorCategoryData {__RequestVerificationToken}` → `[{CategoryID,ParentID,CategoryName,Level,HasData,ListTermType[]}]` ~60 cats | DB + mem 7d | PG cache |
| `vs_indicator_data` | `category_id, term_type_id=3, sub_term_type_id?, from_date?=2021-06-30, to_date?=today` | `POST /Macro/GetReportDataByIDs {termTypeID 1-8, subTermTypeID, fromDate, toDate, type=CATEGORY, listID[]=cat}` pipe-parse `DataStructure\|Data` | DB upsert, skip macro nếu <24h | PG → 8010 |
| `vs_xnk_detail` | `direction=xk\|nk, from_date?, to_date?` | `listID 64 (XK theo nước) / 65 (NK theo nước) termTypeID=2` → `{country,group,period,year,value,unit}` | mem 6h | `vs_indicator_data` |
| `vs_financial_terms` | — | `POST /financedata/GetListReportTerm` → `ReportTermId 1 cả năm/2 Q1/3 Q2/4 Q3/5 Q4/9 6T/12 9T` | DB upsert | — |
| `vs_financial_norms` | `btype=1\|2\|3\|5` | `POST /FinancialStatement/BCTC_GetChiTieuForTable {BusinessTypeId, ReportComponentCodes=CD,KQ,LCTT}` 190+ norms | DB upsert | — |
| `vs_financial_values` | `symbol, btype=auto(1 CTCP/2 CK/3 Bank/5 BH), years?=3, tids?=[2,3,4,5,9]` | `POST /FinancialStatement/BCTC_LoadReportData_Async {ReportNormIds=csv, ListParams=years×tids {Index,YearPeriod,ReportTermId,StockCode,Unit=1,AuditedStatusId=-1,UnitedId=-1}}` → `{value,audited_status,auditor,publish_date}` | DB upsert | `vs_financeinfo` → Fireant → vnstock → 8010 |
| `vs_company_info` | `symbol` | `POST /FinancialStatement/BCTC_CompanyByCodes {stockCodes}` → `{StockCode,CompanyName/EN,CatGroup=exchange,DescriptionVN}` | DB | — |
| `vs_trading_info` | `symbol` | `POST /company/tradinginfo {code,s=0}` → `{KLCPLH/KLCPNY,TotalRoom,AvrPrice,PriorClose,Ceiling/Floor,TotalVal,MarketCapital,Min/Max52W,Vol52W,OutstandingBuy/Sell,OwnedRatio,CurrRoom/RemainRoom,F_Buy/Sell,MarketStatus}` | snapshot DB + mem 60s | vnstock quote |
| `vs_financeinfo` | `symbol, period=quarter\|year` | `POST /data/financeinfo {Code,Page 1-3 quarter/1 year,PageSize=4,ReportTermType=2/1,ReportType=BCTQ,Unit=1}` → 12 quý + sections KQKD/CĐKT/CSTC | file+mem 6h | 8010 `stock-finance` |
| `vs_overview_trading` | `symbol` | `POST /data/GetStockDeal_OverviewTrading {stockCode}` + `tradinginfo` → `{price,change,pct,volume,EPS,BVPS,PE,PB,ROEA/ROAA}` | mem 15' | `vs_trading_info` |
| `vs_documents` | `symbol` | `POST /data/GetDocument {code,page=1,pageSize=60}` → `[{title,kind=bctc/giai_trinh/nghi_quyet/dieule/khac,date,url,ext}]` | file+mem 24h | — |
| `vs_reports_search` | `symbol?, keywords?, page_size≤50` | `POST /CompanyReport/CompanyReportSearch {stockCode,categoryId=2 BC phân tích}` → Mongo `vietstock_news` | Mongo upsert | `vs_news_search` |
| `vs_industry_tree` | — | `POST /FinancialStatementSector/GetTreeViewIndustryGICS` | DB | — |
| `vs_stock_industry` | `industry_id` | `POST /FinancialStatementSector/GetBusinessTypeIDCompanyByGICS {IndustryID lv2-3}` | DB | — |
| `vs_industry_heatmap` | — | `POST /Data/GetHeatmapGICS {industryCode=0,detailIndustry=true}` live | không (live) | — |
| `vs_market_price` | `type?=2` | `POST /data/getmarketprice` → `[{code,name,price,change,change_percent,trading_date}]` | mem 60s | `vn_equity_quote_batch` |
| `vs_market_index` | — | `POST /Data/GeneralMarket_GetMarketIndexVNData` → `{IndexID,CloseIndex,PerChange,1M,YTD}` | mem 60s | `vn_index_ohlcv` |
| `vs_nn_flow` | — | `POST /data/KQGDGiaoDichNDTNNChart` → `[[dates],[{TradingDate,BuyVol/Val,SellVol/Val}]]` | DB + mem 300s | `dnse_foreign_flow` |
| `vs_selftrading` | — | `POST /data/KQGDGiaoDichTuDoanhChart` cùng shape trên | DB + mem 300s | — |
| `vs_top_liquidity` | `index?=VNINDEX, top_n?` | `POST /Data/GetTopStockLiquidity` | mem 60s | snapshot riêng |
| `vs_gics_index` | — | `POST /data/GetGICSIndexMain` → `{IndustryCode,CloseIndex,Vol,Val,ForeignBuy/SellVol}` | mem 60s | `vs_industry_heatmap` |
| `vs_currency` | — | `POST /data/GetCurrency` → USD/VND `[1]` | mem 300s | `vn_retail_fx` |
| `vs_market_info` | `symbol?` | `POST /data/marketinfo` → `{c,p,ch,pch,vol,val,up,dn,fbvol,fsvol,bvol,svol}` | mem 5s (giờ mở) | `dnse_market_status` |
| `vs_news_search` | `query, page_size?, page?` | `POST https://dc.vietstock.vn/api/Search/SearchArticleNewAsync {keySearch,pageSize,filterTime=all}` | không | GDELT layer |

### Nhóm B — vnstock (VCI/KBS/MSN, `vnstock>=4.0`)

| Tool | Parameters | Lấy trực tiếp như nào | TTL/cache | Fallback |
|---|---|---|---|---|
| `vn_quote_history` | `symbol, start?, end?, days?=365, interval?=1D, resolution?, source_order?=VCI→KBS` | `Quote(symbol,source).history(start,end,interval/resolution)`: VCI daily equity/index; KBS 90d repair + `resolution=1m/15m` intraday F1M/VNINDEX/VN30; sleep 2s, retry 3 | PG + file pkl | Market ohlcv → 8010 batch |
| `vn_index_ohlcv` | `symbol=VNINDEX\|VN30\|VN30F1M\|HNX\|UPCOM, length?=2, interval?=1D` | `Market().index(sym).ohlcv(length,interval,source=vci)` → `save_index dash:index:*` | Redis 5s loop | `vn_quote_history` |
| `vn_equity_ohlcv` | `symbol, length?=2, interval?=1D` | `Market().equity(sym).ohlcv(length,interval)` | Redis 60s | `vn_quote_history` |
| `vn_equity_quote_batch` | `symbols[]` (= price_board, thay `price_board` không tồn tại) | `Market().equity(list).quote()` 1 req → `{close_price,volume_accumulated,total_value,percent_change}` pad thiếu = 0 | mem 5s | `dnse_latest_trade` |
| `vn_trades` | `symbol, board?, from?, to?, limit?` | `Market().equity(sym).trades()` | mem 60s | `dnse_latest_trade` |
| `vn_futures_ohlcv` | `symbol=VN30F1M, start?, end?, length?` | `Market().futures(sym).ohlcv()` + `Quote(VN30F1M,VCI).history(5d)` | Redis + DB | `dnse_ohlc_history` |
| `vn_reference` | `by=exchange\|group\|industry, key?` | `Reference().equity.list_by_exchange/group/industry + industry.list/sectors` → ICB 4-level | DB + delay 0.5s | `vs_industry_tree` |
| `vn_company` | `symbol` | `Company(sym,VCI).info/shareholders/officers/subsidiaries` → `{organ_name,sector_EN}` map ICB→GICS | file pkl | `vs_company_info` |
| `vn_fundamentals` | `symbol, period=year\|quarter, report_type?=ttm` | `Fundamental().equity(sym).*(period)` + `Finance(sym,KBS).ratio(period,report_type)` → `{pe,pb,eps,roe,roa,rev_g}` | file pkl 24h | `vs_financial_values` |
| `vn_listing` | — | `Listing().all_symbols()` → `[{symbol,organ_name}]` sort | file 24h | `vn_reference` |
| `vn_retail_gold` | `source?=btmc` | `Retail().gold(source)` filter `SJC/NHẪN TRÒN` → `{buy_price,sell_price,world_price}` | mem 15' | jina/webgia |
| `vn_retail_fx` | — | `Retail().exchange_rate()` filter `USD` → `{buy_transfer,sell}` VCB | mem 15' | `vs_currency` |
| `vn_msn_fx_gold` | `symbols?=[USDVND,XAUUSD], days?=35` | `explorer.msn Quote(symbol_id).history(35d,1D)` → `{price,chg_1d,spark,quydoi_trieu_luong=XAU/31.10347*37.5*fx/1e6}` | mem 15' (180s nếu thiếu SJC) | yfinance |
| `vn_forex_ohlcv` | `pair=USDVND\|EURUSD\|..., interval?=1d, length?=5, side?=mid` | `Market().forex(pair).ohlcv(interval,length,side)` | mem 300s | yfinance `=X` |
| `vn_crypto_ohlv` | `symbol=BTCUSDT, interval?=1d, limit?=5` | `Market().crypto(sym).ohlcv(interval,limit)` | mem 60s | Binance/CoinGecko |
| `vn_global_index` | `symbol=USA30, interval?=4h, length?=5` | `Market().index(sym,scope=global).ohlcv()` | mem 300s | yfinance |

### Nhóm C — yfinance (loops riêng, không qua 8010)

| Tool | Parameters | Tickers/params thật | TTL/loop | Fallback |
|---|---|---|---|---|
| `yf_global_indices` | — | GLOBAL 9 `^GSPC,^IXIC,^DJI,^N225,^HSI,000001.SS,^KS11,^GDAXI,^FTSE` `download(2d/1d,group_by=ticker)` | loop 60s TTL120 | vn_global_index |
| `yf_commodities` | — | COMMO 13 `GC=F,SI=F,CL=F,HG=F,PL=F,PA=F,BZ=F,NG=F,RB=F,HO=F,BTC-USD,VND=X,DX-Y.NYB` | loop 60s TTL120 | — |
| `yf_yield_curve` | — | `Ticker(^TNX).history(1d)/100` 10Y + `2YY=F` 2Y → `{us3m..us30y approx,inverted}` | loop 60s | FRED |
| `yf_world_indices` | — | WORLD 43 + VNINDEX via vnstock (list đầy đủ Bảng 0) `download(2d/1d)` | loop 300s TTL300 | 8010/8001 |
| `yf_market_pins` | — | 45 world + 7 VN `Ticker.history(5d)` threaded 10 (chỉ khi Shadowbroker down) | file TTL 3600s | `yf_world_indices` |
| `yf_oracle_markets` | — | ~40 6 groups crypto/metals/energy/agri/bonds_fx/index/sectors `download(1mo/1d)` → `{price,chg,chg_7d/30d,spark,rsi14,high30/low30}` | mem 900s | — |
| `yf_regime_assets` | — | 7 `^GSPC,^VIX,DX-Y.NYB,^TNX,BTC-USD,GC=F,CL=F` `download(2y/1d)` → regime/confidence | mem 1800s | — |
| `yf_mega_flows` | — | Nasdaq screener `cap≥2B` + 26 intl `download(batch300,1mo/1d)` → sector median + top15/bottom10 | RAM 900s + file 24h/7d | — |
| `yf_alloc_history` | `asset=GC\|VND\|BTC\|OIL\|SILVER\|COFFEE, tf=1d\|1wk` | `download(max,1d/1wk,auto_adjust)` → `*.pkl` | file, retry 3 backoff | — |

### Nhóm D — DNSE (`DNSE_API_KEY/SECRET`, base `https://openapi.dnse.com.vn` v2026-05-07)

| Tool | Parameters | Lấy trực tiếp như nào | TTL/loop | Fallback |
|---|---|---|---|---|
| `dnse_ohlc_history` | `symbol=VN30F1M\|VN30, bar_type=derivative\|index, resolution?=15, from?=2018-08-01, page_size?=10000` | `GET /price/ohlc?type&symbol&resolution&from&to&pageSize&time=cursor→nextTime` → `{t,o,h,l,c,v}` TZ Asia/HCM | pickle + csv | `vn_futures_ohlcv` |
| `dnse_latest_trade` | `symbols[]` | `GET /price/{sym}/trades/latest` ×N ThreadPool20 → `{matchPrice,openPrice,totalVolumeTraded,grossTradeAmount}` | mem 60s | `vn_equity_quote_batch` |
| `dnse_orderbook` | `symbol, depth?=3` | `GET /price/{sym}/quotes[/latest]` bid/ask (MỚI — repo đang `pass`, cần implement) | live, không cache | — |
| `dnse_foreign_rest` | `symbol` | `GET /price/{sym}/foreign-trading` (MỚI — repo chưa dùng trong loop) | mem 60s | `dnse_ws_snapshot` |
| `dnse_ws_snapshot` | `symbols?=[VN30F1M,VNINDEX,VN30]` | WS `wss://.../v1/stream?encoding=msgpack\|json` HMAC auth, sub `ohlc.1.json + market_index.* + foreign.*` → `dash:ohlc/index/foreign:*` | Redis TTL 12h, build 30s | `dnse_latest_trade` |
| `dnse_market_status` | — | `_build_market_status: dash:ohlc+foreign` → WS rỗng + giờ mở → `fetch_market_status_rest` → đóng phiên → `fetch_market_status_from_db` | 5s broadcast | 8010 meta |
| `dnse_indices` | — | `dash:index:*` từ WS `T==mi` + `fetch_vn_indices_vnstock` | 5s loop | `vs_market_index` |
| `dnse_foreign_flow` | — | `SCAN dash:foreign:*` WS `T==f {Buy/SellVolume/Amount}` → `net=buy-sell` → PG `vn_foreign_flow` | 60s fresh check | `vs_nn_flow` |
| `dnse_vn30f1m_live` | — | WS nến 1m aggregate 15m (`BAR_15M`, remap `14:30→14:45`, `closed_bars≤60`) + `Quote(KBS) resolution=1m` backfill | run_loop 10s (09:00-15:05) | `dnse_ohlc_history` |
| `dnse_working_dates` | — | `GET /market/working-dates` (= exchange_calendar) | file 7d | — |

### Nhóm E — Pure-read tổng hợp (không fetch upstream mới, chỉ aggregate)

| Tool | Parameters | Tính từ đâu | TTL | Ghi chú |
|---|---|---|---|---|
| `symbol_lookup` | `query` | `vn_listing + vn_reference + vs_company_info` | 24h | resolve tên cty → mã/sàn/ICB |
| `market_snapshot` | `as_of?, symbols[]?` | `dnse_market_status + vn_equity_quote_batch + yf_global_indices` | 5s | thay `/api/meta` |
| `market_movers` | `top_n?` | tính từ snapshot | 60s | top tăng/giảm/vol |
| `sector_performance` | `level?` | `vs_gics_index + vn_reference` | 60s | theo GICS/ICB |
| `breadth_scan` | — | snapshot → `{advancers,decliners,ceiling,floor/exchange}` | 60s | rally health |
| `exchange_calendar` | — | `dnse_working_dates` | 7d | giờ mở/ATO/ATC/T+ |
| `economic_calendar` | `scope=vn\|world` | `vs_categories` VN + FRED/WorldBank world (tách khỏi `brief_build`) | 24h | lịch sự kiện |
| `corporate_calendar` | `symbol?` | `vs_documents + company_events` (tách khỏi `brief_build`) | 24h | cổ tức/ĐHCĐ |
| `source_status` | — | health mọi upstream + JWT exp + Redis `last_update` (tách khỏi `oracle_health`) | 60s | debug TTL |
| `market_candles_batch` | `symbols[], days?` | `vn_quote_history` multi, 1 req/mã chống herd | theo candles | batch OHLCV |

### Nhóm F — Compute/signal/quant/intel (tính local, không fetch upstream mới)

| Tool | Parameters | Tính như nào | Fallback |
|---|---|---|---|
| `stock_screener` | `filters{}, universe?, limit?` | `vn_reference + vn_fundamentals + vs_trading_info` + models breakout/BCD pkl | 8010 universe |
| `stock_forensic` | `symbol` | Port `forensic.py` từ `vs_financial_values` (M-Score/Piotroski/Dechow 13 fields) | 8010 forensic |
| `valuation_run` | `symbol, method=auto\|dcf\|per\|pb\|ev\|ensemble` | Port ValuationManager (bank P/B, broker P/B+ROE, insurer P/EV, khác DCF+PER) | OPC routes |
| `fred_series` | `series_id, limit?, spark?` | FRED HTTP direct → OpenBB | 8010 fed-watch |
| `world_macro_country` | `iso3, indicator` | WorldBank v2 direct | FRED |
| `world_prediction_odds` | `query?, tag?, status?, min_liquidity?, min_volume?, order?` | jina→Gamma cache 45' → Kalshi → Manifold | Oracle cache |
| `world_fear_greed` | — | alternative.me direct | Oracle |
| `news_symbol` | `symbol, limit?, sources?` | Fireant + `vs_news_search` + RSS | Oracle/GDELT |
| `news_market` | `limit?, sources?` | Fireant + RSS + Vietstock reports | Oracle/GDELT |
| `sentiment_score` | `symbol` | Fireant + Groq | — |
| `macro_reports` | `limit?` | Vietstock PDF + Groq tóm tắt | — |
| `stock_overview` | `symbol` | `vs_trading_info + vs_overview_trading + vn_company` (giữ alias cũ cho skill `information`) | 8010 dossier |
| `company_events` | `symbol, types?` | `vs_documents + Fireant` (giữ alias) | 8010 dossier |
| `insider_trading` | `symbol, window?` | Fireant insider direct | 8010 dossier |
| `financial_statements` | `symbol, statement, period, periods_n≤15` | alias `vs_financial_values + vs_financeinfo` (giữ tương thích v3) | 8010 finance |
| `financial_ratios` | `symbol, set, period, peers[]?` | alias `vs_overview_trading + vn_fundamentals` | 8010 CSTC |
| `peer_compare` | `symbol, peers[], metrics[]?` | cùng nguồn ratios | — |
| `signals_scan` | `force?, universe?` | models breakout/BCD local + screener | 8010 scan |
| `signals_technical` | `symbol, tf, indicators[], lengths{}` | pandas local + Wyckoff/Elliott port | 8010 |
| `signals_trade_log` | `days≤365, side?` | đọc `trade_log.json` | 8010 trade-log |
| `pattern_match` | `symbol, lookback?` | Redis/PG + cluster pkl | 8010 cluster |
| `quant_backtest` | `strategy, params{cost,slippage,benchmark,walk_forward,regime_filter}` | sandbox local | 8002 |
| `quant_factors` | `strategy, params{}` | sandbox local | 8002 |
| `quant_risk` | `run_id?` | từ trade_log | — |
| `evidence_bundle` | `claim_ids[], calc_ids[]` | MCP-server tự đóng | — |
| `assets_rotation` | — | regime classify port + `yf_oracle_markets` | 8010 |
| `mega_flows` | — | alias `yf_mega_flows` (Nasdaq+yf, KHÔNG phải DNSE/TCBS) | — |
| `foreign_flow` | — | alias `dnse_foreign_flow` (primary) | `vs_nn_flow` |
| `alert_check` | `rules[{metric,op,threshold}]` | evaluator trên snapshot | — |
| `oracle_meta` | — | aggregator snapshot + `source_status` | 8010 (tạm) |
| `oracle_health` | — | alias `source_status` + aggregator | 8010 (tạm) |
| `geo_intel` | `topic?` | port intel_sources direct | 8010 layers |
| `event_stats` | — | GDELT direct + lifecycle | — |
| `scenario_simulate` | `scenario` | port simulate.py sandbox | 8010 whatif |
| `brief_build` | `scope=vn\|world, date?` | compose từ `news_* + economic_calendar + corporate_calendar + *_pins` (không fetch trực tiếp) | — |
| `compare_equities` | `symbols[]` | từ ratios + candles tự lấy | — |
| `compare_assets` | `assets[]` | từ indices + commo tự lấy | — |
| `runs_list` | `id?` | session store local | — |
| `run_get` | `id` | session store local | — |
| `doctor` | — | local validate | — |

## Bảng 3 — Nguồn trực tiếp + fallback (v4)

| Tầng | Lấy trực tiếp (chính) | Fallback 1 | Fallback 2 | Cảnh báo |
|---|---|---|---|---|
| Giá VN realtime | `dnse_ws_snapshot` (WS msgpack/json) + `vn_equity_quote_batch` 5s + `dnse_latest_trade` ThreadPool20 | `vs_market_info` | 8010 meta / 8001 indices | `/market-status` rỗng — cấm; `price_board` string không tồn tại, dùng batch quote |
| OHLCV daily | `vn_quote_history` VCI + `vn_index_ohlcv/vn_equity_ohlcv` | KBS repair 90d | PG read-only → 8010 batch | kline clamp 100–5000; `interval` (1D) vs `resolution` (1m/15m) khác nhau |
| Intraday F1M | `dnse_vn30f1m_live` WS 1m→15m + `dnse_ohlc_history` cursor | `Quote(KBS,resolution=1m)` backfill | `Quote(VCI)` 5d | remap `14:30→14:45`, TZ Asia/HCM |
| Orderbook | `dnse_orderbook` (mới implement, repo đang pass) | — | — | chưa có consumer |
| BCTC trả phí | Vietstock JWT (`vs_financial_values` 15/28 cols, check exp 2026-10-02 mỗi phiên, cron refresh <7 ngày) | `vs_financeinfo` mirror 12Q | Fireant → vnstock → 8010 | `btype` 1/2/3/5 bắt buộc đúng; `tids` 1,2,3,4,5,9,12 |
| Company | `vs_company_info + vs_trading_info + vn_company + vn_reference` | Fireant | 8010 dossier | — |
| Vĩ mô VN | `vs_categories + vs_indicator_data + vs_xnk_detail` | PG cache | 8010 | `termTypeID/sub` sai = số liệu sai kỳ |
| Global/macro | yfinance 9 nhóm trên + FRED + WorldBank | OpenBB | 8010/8001 | Finnhub/EIA/AlphaVantage thiếu key |
| Odds | jina→Gamma (45') → Kalshi → Manifold | Oracle cache | — | Gamma blocked local — bắt buộc jina |
| Vàng VN | `vn_retail_gold` (BTMC SJC/nhẫn) + `vn_msn_fx_gold` (XAUUSD) + `vn_retail_fx` | jina/webgia SJC | — | webgia cũ 404 — dùng jina; Vietstock KHÔNG có vàng |
| FX | `vn_forex_ohlcv + vn_retail_fx (VCB) + vs_currency` | yfinance `VND=X` | — | — |
| News/sentiment | Fireant + `vs_news_search + vs_reports_search` + RSS | GDELT layer | 8010 | bật pipeline Mongo riêng |
| Intel/geo | intel_sources port direct | Shadowbroker (down) | 8010 layers | — |
| Flows | `dnse_foreign_flow` (WS f) + `vs_nn_flow/vs_selftrading` + `yf_mega_flows` (Nasdaq) | cross-check chéo | 8010 | `investor_flow`/TCBS không tồn tại — đã xóa |
| Quant | sandbox local | 8002 (down) | OPC routes | — |

## Tham số chuẩn mọi tool + TTL + per-agent filter

`timeout_seconds` (read 10–30, quant 120) · `max_result_bytes` (snapshot 256KB, candles 1MB, news 512KB) ·
`concurrency` (read PARALLEL, quant/alert EXCLUSIVE) · `permission` (MARKET_READ/NEWS_READ/SIGNAL_READ) ·
`as_of` ISO8601 + Asia/Ho_Chi_Minh · `symbol` HOSE/HNX/UPCOM · `limit` clamp + paginate ·
`btype` auto (1 CTCP/2 CK/3 Bank/5 BH) · `tids` [1,2,3,4,5,9,12] · `period=quarter(12 kỳ)|year` ·
`termTypeID` 1-8 + `subTermTypeID` · `interval` (1D/1h/4h) vs `resolution` (1m/15m) · `consolidated` + `audited_status` kèm ·
`source_order=VCI→KBS` · `api_version=2026-05-07` (DNSE) · `pageSize` 4 (financeinfo) / 60 (document) / 10000 (DNSE ohlc).

TTL: snapshot/orderbook 5s · trading/market_info 60s · indices/commo/world 60-300s · overview/FX/gold 15' ·
financeinfo 6h · documents 24h · listing/calendar 24h-7d · categories 7d · odds 45' · regime 1800s · alloc max file.

Per-agent filter (bắt buộc, tránh bloat context — theo docs Opencode `tools: {mcp_*}`):
`market-data agent: vs_* + vn_* + dnse_*` · `macro agent: vs_categories/indicator/xnk + fred/world_macro + yf_*` ·
`scan agent: vn_reference/fundamentals + stock_screener/signals_*` · `quant agent: quant_* + vn_quote_history + vs_financial_values` ·
`brief agent: brief_build + news_* + economic/corporate_calendar` · global disable `mcp_*=false` rồi enable theo agent.

## Changelog v3 → v4

* Tách toàn bộ dòng `a / b` thành tool đơn (26 dòng Bảng 2 v3 → ~65 tools v4 có prefix nguồn).
* Thêm mới: `vs_*` 25 tools (auth/categories/terms/norms/company/trading/documents/reports/industry/market/nn/selftrading/liquidity/gics/currency/xnk),
  `vn_*` 16 (quote_history/index/equity_batch/trades/futures/reference/company/fundamentals/listing/retail/msn/forex/crypto/global),
  `yf_*` 9 (global/commo/yield/world/pins/oracle/regime/mega/alloc),
  `dnse_*` 10 (ohlc/latest/orderbook mới/foreign_rest mới/ws_snapshot/market_status/indices/foreign_flow/vn30f1m_live/working_dates),
  pure-read 10 (`symbol_lookup/market_snapshot/movers/sector/breadth/exchange/economic/corporate/source_status/candles_batch`).
* Xóa/sửa sai: `investor_flow`, `TCBS/vn-stock-sdk`, `feat:*`, `Vietstock gold`, `price_board` string, `mega_flows=DNSE` (thực chất Nasdaq+yf).
* Skills Bảng 1 giữ 58, cập nhật cột Tools gọi sang tên v4 + fix `money-flow`, `gold-vn`, `derivatives`, `brief-*`, `history`.
