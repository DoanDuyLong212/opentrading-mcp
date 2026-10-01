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

## Bảng 1 — Skills v4 (11 nhóm × 59 skills, Descriptor = frontmatter SKILL.md)

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
| web | `web-research` | Search the web first, then fetch results recursively until done. Use when facts beyond cutoff or local data are needed. | `web_search, web_fetch` | Exa/Parallel (paid) + direct HTTP (free) |
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
| `dnse_orderbook` | `symbol, depth?=3` | `GET /price/{sym}/quotes/latest` → fallback `/quotes` → `{bids,asks}` cắt theo depth (`providers/dnse.py:144`) | live, không cache | — |
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

## Bảng 2b — Web research (mirror opencode 1:1, không qua 8010)

| Tool | Parameters | Làm giống opencode như nào | TTL/cache | Fallback |
|---|---|---|---|---|
| `web_fetch` | `url, format?=markdown\|text\|html, timeout_seconds?≤120` | `webfetch.ts`: browser UA + `Accept` theo format → cap 5MB (header+body) → CF 403-challenge retry UA thật → ảnh trả attachment base64 → HTML→markdown (turndown atx/fenced) / HTML→text (bỏ script/style) | không (live) | — |
| `web_search` | `query, num_results?=8, livecrawl?=fallback, search_type?=auto` | `websearch.ts + mcp-websearch.ts`: POST JSON-RPC `tools/call` tới Exa (`web_search_exa`, key nhúng URL) / Parallel (`web_search`, Bearer) → parse JSON trực tiếp + dòng `data:` SSE → timeout 25s die | không (live) | provider còn lại (qua `WEBSEARCH_PROVIDER`) |

Chọn provider: env `WEBSEARCH_PROVIDER=exa\|parallel` → không có thì hash query chẵn/lẻ (thay checksum sessionID vì MCP stateless — điểm thích ứng duy nhất). Không key nào → `web_search` bị gạt khỏi `tools/list` (giống `registry.ts:293`). Preset: `intel` + `market` (`server.py:47-58`, remote chạy preset `market`). Skill kèm: `web-research` (search trước → fetch từng kết quả → đệ quy theo link → bám redirect khác host).

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

## Changelog v4 → v5

* Web research mirror opencode 1:1: `providers/webfetch.py` (no key) + `providers/websearch.py` (Exa/Parallel, `WEBSEARCH_PROVIDER`, hash-query A/B thay checksum session) + `tools/web.py` (`web_fetch` luôn hiện, `web_search` gạt khỏi list khi thiếu key) + skill `web-research` + preset `intel` (59 skills, Bảng 2b mới).
* Deps mới: `markdownify`, `beautifulsoup4`. Quy ước tên: `web_fetch`/`web_search` theo rule `snake_case` repo (opencode gốc là `webfetch`/`websearch`).

## Phụ lục A — Descriptor từng tool: tên · descriptor · params · quyền · data source (v2, 2026-09-24)

> Cách đọc: LLM nhìn thấy 4 thứ qua `tools/list` — **tên**, **descriptor** (docstring dòng đầu), **params** (signature trừ `ctx`), **quyền** (`annotations`). Cột **Data source** là logic chạy thật ở `providers/` (LLM không thấy). Trích từ code `main @ 1b97c88` + verified runtime. Quyền: `RO` = READ_ONLY (`readOnlyHint=true, idempotentHint=true`), `RW` = READ_WRITE (`readOnlyHint=false, destructiveHint=false, idempotentHint=true`). Preset chứa tool ghi ở tiêu đề từng mục. Envelope mọi tool: `{data, provenance{source, as_of UTC, timezone: Asia/Ho_Chi_Minh}, warnings[], availability: available|empty|stale|partial|unavailable}`.
>
> Fallback tự động (tool tự gọi nguồn khác khi nguồn chính chết): `vn_quote_history`/`insider_trading` (VCI→KBS), `money_flow` (DNSE WS→Vietstock), `sentiment_score` (Groq→heuristic), watchlist/alert (PG→file JSON), `news_market`+`brief_build` (Vietstock→GDELT), `web_fetch` (UA retry), `geo_intel`/`event_stats` (retry 1 lần), DNSE orderbook (path `/quotes/latest`→`/quotes`). Tool còn lại fail → envelope `unavailable` graceful.

### market.py → preset `market`, `all` — 7 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `market_snapshot` | Snapshot of VN market with provenance. Use when a broad market picture is needed. | `symbols: list[str] \| None = None` | RO | vnstock `equity_quote_batch` + `yf_global_indices`; cache Redis TTL 60s (fallback memory) |
| `source_status` | Health of every upstream plus TTL state. Use to debug stale data. | — | RO | local: JWT Vietstock + Redis keys + env check |
| `market_candles_batch` | Batch OHLCV for symbols, one request per symbol. Use for multi-chart context. | `symbols: list[str], days: int = 30, summary: bool = False, columns: list[str] \| None = None` | RO | vnstock VCI→KBS per symbol; cap 50 + warning khi cắt; lỗi vào `missing[]`, availability `partial` |
| `symbol_lookup` | Resolve company name to symbol, venue and sector. Use before any symbol-scoped call. | `query: str` | RO | vnstock `Listing.all_symbols` + `Reference` |
| `market_movers` | Top gainers, losers and volume leaders. Use for session pulse checks. | `top_n: int = 10` | RO | snapshot local (universe VN30 hardcode) |
| `breadth_scan` | Advancers, decliners, ceiling and floor counts. Use to judge rally health. | — | RO | Vietstock `getmarketprice` + `marketinfo` |
| `dnse_market_status` | DNSE session state plus latest index snapshot. Use for open/close checks. | — | RO | DNSE WS cache → DNSE REST `/price/VN30F1M/trades/latest` → unavailable |

### web.py → preset `market` + `intel` — 2 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `web_fetch` | Fetch a URL and convert to markdown, text or html. Use for reading web content. | `url: str, format: str = "markdown", timeout_seconds: int = 30` | RO | direct httpx browser-UA, cap 5MB; CF 403 → retry UA "opencode"; HTML→markdownify/BS4 |
| `web_search` | Search the web via Exa/Parallel providers. Use for up-to-date information. | `query: str, num_results: int = 8, livecrawl: str = "fallback", search_type: str = "auto"` | RO | Exa hoặc Parallel (env `WEBSEARCH_PROVIDER` hoặc hash query chẵn/lẻ); **ẨN khỏi tools/list khi thiếu key** |

### vn.py → preset `market` — 6 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `vn_quote_history` | Daily candles for a VN symbol, VCI then KBS fallback. Use for any price history. | `symbol: str, days: int = 365, summary: bool = False, columns: list[str] \| None = None` | RO | vnstock `Quote(VCI→KBS)` tự fallback; `summary` = `{count,last,high,low}` thay candles |
| `vn_equity_quote_batch` | One-request price board for many symbols. Use for snapshots and movers. | `symbols: list[str], summary: bool = False, columns: list[str] \| None = None` | RO | vnstock `Market.equity(list).quote()` 1 request |
| `vn_listing` | Full symbol list with company names. Use for universe and lookup. | — | RO | vnstock `Listing.all_symbols()` |
| `vn_fundamentals` | Ratios and statements via vnstock Fundamental and Finance. Use for quick valuation. | `symbol: str, period: str = "year"` | RO | vnstock `Fundamental.ratio` + `Finance` |
| `vn_retail_gold` | SJC and ring gold buy/sell from BTMC retail. Use for local gold premium. | — | RO | vnstock `Retail.gold(btmc)` SJC/NHẪN |
| `vn_retail_fx` | VCB USD buy/sell rates. Use for currency conversion context. | — | RO | vnstock `Retail.exchange_rate()` VCB |

### vs.py → preset `market` — 8 tools (Vietstock)

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `vs_auth_status` | Vietstock JWT state and expiry. Use before any paid BCTC call. | — | RO | Vietstock session: env `VIETSTOCK_COOKIE_LOGIN` → seed session.json → login Email/Password |
| `vs_financeinfo` | Free-mirror statements, 12 quarters or years. Use when JWT is absent. | `symbol: str, period: str = "quarter"` | RO | Vietstock `POST /data/financeinfo` (mirror free, 12 kỳ) |
| `vs_market_price` | Live board snapshot from Vietstock. Use as secondary quote source. | — | RO | Vietstock `POST /data/getmarketprice` |
| `vs_market_index` | Index closes with 1M and YTD change. Use for index context. | — | RO | Vietstock `GeneralMarket_GetMarketIndexVNData` |
| `vs_nn_flow` | Foreign investor buy/sell chart. Use to cross-check DNSE WS flows. | — | RO | Vietstock `KQGDGiaoDichNDTNNChart` |
| `vs_categories` | Macro indicator catalogue (~60 categories). Use before indicator queries. | — | RO | Vietstock `Macro/GetIndicatorCategoryData` |
| `vs_indicator_data` | Macro series for a category and term type. Use for GDP, CPI, trade context. | `category_id: int, term_type_id: int = 3` | RO | Vietstock `Macro/GetReportDataByIDs` (termTypeID 1-8) |
| `vs_trading_info` | Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot. | `symbol: str` | RO | Vietstock `POST /company/tradinginfo` |

### vs_bctc.py → preset `market` — 17 tools (Vietstock trả phí + GICS)

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `vs_financial_terms` | Report term catalogue (annual, Q1-Q4, H1, 9M). Use before BCTC value queries. | — | RO | Vietstock `GetListReportTerm` (ReportTermId 1,2,3,4,5,9,12) |
| `vs_financial_norms` | 190+ BCTC line items for a business type. Use to resolve norm ids. | `btype: int = 1` | RO | Vietstock `BCTC_GetChiTieuForTable` (btype 1 CTCP/2 CK/3 Bank/5 BH) |
| `vs_financial_values` | Paid BCTC values matrix (norms x 3y x 5 terms). Use for statements. | `symbol: str, btype: int = 1, years: int = 3` | RO | Vietstock `BCTC_LoadReportData_Async` (JWT bắt buộc) |
| `vs_company_info` | Company names, exchange and description. Use for profiles. | `symbol: str` | RO | Vietstock `BCTC_CompanyByCodes` |
| `vs_overview_trading` | EPS, BVPS, PE, PB, ROEA/ROAA snapshot. Use for valuation inputs. | `symbol: str` | RO | Vietstock `GetStockDeal_OverviewTrading` + tradinginfo |
| `vs_documents` | Filings and disclosures with links. Use for corporate actions. | `symbol: str` | RO | Vietstock `POST /data/GetDocument` |
| `vs_reports_search` | Analyst reports search. Use for external views on a name. | `symbol: str = ""` | RO | Vietstock `CompanyReportSearch` categoryId=2 |
| `vs_industry_tree` | GICS industry tree. Use before sector mapping. | — | RO | Vietstock `GetTreeViewIndustryGICS` |
| `vs_stock_industry` | Companies under a GICS industry node. Use for peer universes. | `industry_id: int` | RO | Vietstock `GetBusinessTypeIDCompanyByGICS` |
| `vs_industry_heatmap` | Live sector heatmap. Use for intraday rotation. | — | RO | Vietstock `GetHeatmapGICS` (live) |
| `vs_selftrading` | Prop-desk flow chart. Use alongside foreign flows. | — | RO | Vietstock `KQGDGiaoDichTuDoanhChart` |
| `vs_top_liquidity` | Most liquid names per index. Use for liquidity screens. | `index: str = "VNINDEX"` | RO | Vietstock `GetTopStockLiquidity` |
| `vs_gics_index` | GICS index closes with foreign flow. Use for sector context. | — | RO | Vietstock `GetGICSIndexMain` |
| `vs_currency` | Reference FX table. Use as fallback FX source. | — | RO | Vietstock `GetCurrency` |
| `vs_market_info` | Compact market line per symbol. Use for 5s snapshots in hours. | `symbol: str = ""` | RO | Vietstock `POST /data/marketinfo` |
| `vs_news_search` | Vietstock article search. Use for catalyst lookup. | `query: str` | RO | `dc.vietstock.vn SearchArticleNewAsync` (không cần cookie) |
| `vs_xnk_detail` | Import/export by country. Use for trade structure (termType 2). | `direction: str = "xk"` | RO | Vietstock macro listID 64 (XK)/65 (NK), termType 2 |

### vn_ext.py → preset `market` — 10 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `vn_index_ohlcv` | Index bars for VN tickers. Use for index history and breadth. | `symbol: str = "VNINDEX", count: int = 100, summary: bool = False, columns: list[str] \| None = None` | RO | vnstock `Market.index(VCI).ohlcv` |
| `vn_equity_ohlcv` | Equity bars via Market API. Use as OHLCV alternative to quotes. | `symbol: str, count: int = 100, summary: bool = False, columns: list[str] \| None = None` | RO | vnstock `Market.equity(VCI).ohlcv` |
| `vn_futures_ohlcv` | Futures bars. Use for derivatives backtest input. | `symbol: str = "VN30F1M", count: int = 100, summary: bool = False, columns: list[str] \| None = None` | RO | vnstock `Market.futures.ohlcv` |
| `vn_forex_ohlcv` | FX bars. Use for currency context. | `pair: str = "USDVND", count: int = 30` | RO | vnstock `Market.forex.ohlcv` |
| `vn_crypto_ohlv` | Crypto bars. Use for digital-asset regime reads. | `symbol: str = "BTCUSDT", count: int = 30` | RO | vnstock `Market.crypto.ohlcv` |
| `vn_global_index` | Global index bars. Use as yfinance fallback. | `symbol: str = "USA30", count: int = 30` | RO | vnstock `Market.index(scope=global)` |
| `vn_reference` | ICB reference by exchange. Use for universe construction. | `exchange: str = "HOSE"` | RO | vnstock `Reference.equity.list` — fail-closed khi schema thiếu exchange key |
| `vn_company` | Profile, holders and officers. Use for company research. | `symbol: str` | RO | vnstock `Company(VCI).info/shareholders/officers` |
| `vn_msn_fx_gold` | USDVND and XAUUSD via MSN. Use for gold-basis math. | — | RO | vnstock `explorer.msn Quote.history` |
| `vn_trades` | Tick-level matched trades. Use for microstructure reads. | `symbol: str, limit: int = 20` | RO | vnstock `Market.equity.trades` |

### yf.py + yf_world.py → preset `market` — 9 tools (yfinance)

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `yf_global_indices` | 9 global benchmarks, 2d daily. Use for overnight context. | — | RO | yfinance GLOBAL_9 (`^GSPC,^IXIC,^DJI,^N225,^HSI,000001.SS,^KS11,^GDAXI,^FTSE`) |
| `yf_commodities` | Gold, oil, metals, BTC, VND and dollar index. Use for input-cost context. | — | RO | yfinance COMMO_13 (`GC=F...VND=X,DX-Y.NYB`) |
| `yf_yield_curve` | US 2Y/10Y and inversion flag. Use for rates and regime context. | — | RO | yfinance `^TNX` + `2YY=F` |
| `yf_world_indices` | 24 world benchmarks. Use for global breadth. | — | RO | yfinance batch download 2d |
| `yf_oracle_markets` | 40 markets in 6 groups with 30d stats. Use for cross-asset state. | — | RO | yfinance ~40 ticker 1mo |
| `yf_regime_assets` | 7 regime drivers with 2y history. Use for RISK-ON/OFF calls. | — | RO | yfinance 2y (`^GSPC,^VIX,DX-Y.NYB,^TNX,BTC-USD,GC=F,CL=F`) + rule local |
| `yf_mega_flows` | Mega-cap leader flows. Use to follow global smart money. | — | RO | yfinance 15 mega-cap leaders |
| `yf_alloc_history` | Long allocation history per asset. Use for regime backtests. | `asset: str = "GC", timeframe: str = "1d"` | RO | yfinance 5y |
| `yf_market_pins` | 5-day pins for world majors plus VN watchlist. Use for brief headers. | — | RO | yfinance world majors 5d |

### dnse_tools.py + dnse_ext.py → preset `market` — 10 tools (DNSE)

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `dnse_ohlc_history` | Paginated futures/index bars via cursor. Use for VN30F1M backtest input. | `symbol: str = "VN30F1M", resolution: int = 15, bar_type: str = "derivative", from_date: str = "2018-08-01", summary: bool = False, columns: list[str] \| None = None` | RO | DNSE REST `GET /price/ohlc` HMAC (v2026-05-07) |
| `dnse_latest_trade` | Latest match price and totals per symbol. Use for realtime fallback. | `symbols: list[str]` | RO | DNSE REST `/price/{s}/trades/latest` |
| `dnse_foreign_flow` | Net foreign flow from WS cache. Use as primary smart-money read. | — | RO | Redis `mcp:market:dnse_ws_snapshot:*` (worker DNSE WS publish TTL 30s); chết → unavailable + warning hướng `vs_nn_flow` |
| `dnse_ws_snapshot` | Raw worker snapshot for symbols. Use to debug realtime staleness. | `symbols: list[str] \| None = None` | RO | Redis worker snapshot (flag `stale` ngoài giờ) |
| `dnse_orderbook` | Bid/ask depth. Use for microstructure reads. | `symbol: str, depth: int = 3` | RO | DNSE REST `/price/{s}/quotes/latest` → fallback `/quotes` |
| `dnse_foreign_rest` | Per-symbol foreign trading. Use when WS cache is cold. | `symbol: str` | RO | DNSE REST `/price/{s}/foreign-trading` |
| `dnse_indices` | Index snapshots from WS cache. Use for live index reads. | — | RO | Redis WS `market_index.*` (warning hướng `vs_market_index`) |
| `dnse_vn30f1m_live` | VN30F1M 1m bars aggregated to 15m with session remap. Use for intraday. | — | RO | DNSE REST 1m (7 ngày) → aggregate 15m local, remap `14:30→14:45` |
| `dnse_working_dates` | Trading calendar. Use for session planning. | — | RO | DNSE REST `/market/working-dates` |
| `exchange_calendar` | HOSE/HNX/UPCOM hours, ATO/ATC, T+ settlement. Use for mechanics. | — | RO | static local (không upstream) |

### scan.py → preset `scan` — 6 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `stock_screener` | Screen universe by valuation and quality. Use when hunting candidates. | `filters: dict \| None = None, max_pe: float \| None = None, min_roe: float \| None = None, limit: int = 20` | RO | vnstock Listing + `equity_fundamentals` enrich (gather semaphore 5, 10s/symbol) + local `apply_filters` |
| `signals_technical` | Full technicals rating from local candles (daily only). Use for timing entries. | `symbol: str, interval: str = "1D"` (≠1D → warning) | RO | vnstock candles → `providers/technicals.py` pandas: RSI14 Wilder, Stoch, CCI20, ADX14, MACD, MOM10, AO, EMA/SMA, VWMA, Hull9, BB, ATR14, recommend vote |
| `signals_screener_columns` | Screener column catalog (valuation/quality/universe/price). Use to build filters. | `group: str \| None = None, search: str \| None = None` | RO | local catalog `providers/screener.py` (close/change_pct/sector/industry/index non-filterable) |
| `sector_performance` | GICS heatmap rows. Use for sector rotation reads. | `level: int = 1` | RO | Vietstock `GetHeatmapGICS` |
| `money_flow` | Compose foreign flow: DNSE WS cache first, Vietstock cross-check. | — | RO | DNSE WS cache → Vietstock `KQGDGiaoDichNDTNNChart` → unavailable |
| `alert_check` | Evaluate price/RSI rules against live quotes. Use for live watch. | `rules: list[dict]` (`{symbol, metric: price\|rsi14, op: >,>=,<,<=,cross_up,cross_down, threshold}`) | RO | metric price: vnstock quote; rsi14: candles → technicals local; cross-state Redis TTL 3600s; unknown op → legacy `>` (giữ compat) |

### compute.py → preset `scan` — 24 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `stock_forensic` | M-Score and Piotroski from mirror statements. Use for earnings-quality flags. | `symbol: str` | RO | Vietstock mirror → tính local (M-Score/Piotroski) |
| `valuation_run` | PER/PB ensemble with DCF-lite. Use for fair-value ranges. | `symbol: str, btype: int = 1` | RO | vs_overview + vn quote → local |
| `fred_series` | FRED observations. Use for US macro context. | `series_id: str, limit: int = 60` | RO | FRED API (`FRED_API_KEY`) |
| `world_macro_country` | WorldBank series per country. Use for global GDP/CPI/debt context. | `iso3: str, indicator: str` | RO | WorldBank v2 API |
| `world_fear_greed` | Crypto fear/greed index. Use for risk-appetite reads. | — | RO | alternative.me `/fng/` |
| `sentiment_score` | Crowd sentiment from Fireant posts, Groq-scored. Use for hype risk. | `symbol: str` | RO | Fireant `/posts` → Groq LLM; Groq chết → heuristic likes clamp ±1 |
| `insider_trading` | Insider deals via vnstock Company. Use for informed-flow reads. | `symbol: str, limit: int = 10` | RO | vnstock Company VCI→KBS tự fallback |
| `stock_overview` | Trading info plus company profile. Use for quick dossiers. | `symbol: str` | RO | vs_trading_info + vs_overview + vn_company |
| `company_events` | Disclosures and corporate actions. Use for event calendars. | `symbol: str` | RO | vs_documents + company |
| `financial_statements` | Mirror statements alias (v3 compat). Use for statement reads. | `symbol: str, period: str = "quarter"` | RO | vs_financeinfo |
| `financial_ratios` | Overview plus vnstock ratios merged. Use for ratio screens. | `symbol: str` | RO | vs_overview + vn_fundamentals |
| `peer_compare` | Head-to-head overview rows. Use when picking tickers. | `symbol: str, peers: list[str]` | RO | overview batch (cap 6 peers) |
| `signals_scan` | Donchian breakout scan over VN30 names. Use to hunt momentum. | `limit: int = 10` | RO | vnstock candles VN30 (hardcode 10 mã) → local Donchian 20d |
| `pattern_match` | Self-similarity of return windows by correlation. Use for analogies. | `symbol: str, lookback: int = 60` | RO | vnstock candles → local correlation |
| `signals_trade_log` | Local trade log. Use for label building. | — | RO | file `trade_log.json` → `data/trade_log.json` |
| `macro_reports` | Research PDFs metadata. Use for report discovery. | `symbol: str = ""` | RO | Vietstock CompanyReport |
| `mega_flows` | Alias of yf_mega_flows (Nasdaq/global, not DNSE). Use for global flows. | — | RO | yfinance |
| `foreign_flow` | Alias of dnse_foreign_flow (primary). Use for smart-money reads. | — | RO | Redis WS cache |
| `oracle_health` | Alias of source_status. Use for health checks. | — | RO | local |
| `event_stats` | GDELT event counts for a query. Use for base-rate checks. | `query: str = "stock market"` | RO | GDELT API (retry 1 lần sau 10s) |
| `compare_assets` | Cross-asset last prices via yfinance. Use for allocation reads. | `assets: list[str]` (cap 10) | RO | yfinance |
| `runs_list` | Local run registry. Use to resume analysis sessions. | — | RO | file `data/runs.jsonl` (env `MCP_RUNS_FILE`) |
| `run_get` | Fetch one run by id. Use to inspect past outputs. | `run_id: str` | RO | file runs.jsonl |
| `doctor` | Local self-check: env keys present, package versions. Use before handoff. | — | RO | local |

### watchlist.py → preset `scan` — 12 tools (MỚI v5: P4)

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `watchlist_create` | Create a named watchlist. Use to start tracking a symbol group. | `name: str` | **RW** | Postgres `watchlists` (psycopg, connect_timeout 5) → fallback file `data/watchlists.json` (atomic tmp+replace) |
| `watchlist_list` | List all watchlists with their symbols. Use to recall tracking state. | — | RO | PG/file |
| `watchlist_get` | Get one watchlist's symbols by id. Use before quoting a saved set. | `list_id: int` | RO | PG/file |
| `watchlist_add` | Add symbols (deduped, uppercase) to a watchlist. Use to track more. | `list_id: int, symbols: list[str]` | **RW** | PG/file |
| `watchlist_remove` | Remove symbols from a watchlist. Use to trim tracking. | `list_id: int, symbols: list[str]` | **RW** | PG (transaction + `= ANY(%s)`, fail → raise KHÔNG fallback file) |
| `watchlist_delete` | Delete a watchlist and its items (cascade). Use to clean up. | `list_id: int` | **RW** | PG/file |
| `watchlist_update` | Rename a watchlist. Use sparingly; names are unique labels. | `list_id: int, name: str` | **RW** | PG/file (duplicate name → warning "already exists") |
| `alert_create` | Create a stored alert rule (input to alert_check). Use for live watch. | `symbol: str, op: str = ">", threshold: float = 0.0, metric: str = "price"` | **RW** | PG/file `alert_rules`; validate op ∈ {>,>=,<,<=,cross_up,cross_down} — invalid → không lưu |
| `alert_list` | List stored alert rules (active and paused). Use before alert_check. | — | RO | PG/file |
| `alert_delete` | Delete a stored alert rule by id. Use to clean up alerts. | `rule_id: int` | **RW** | PG/file |
| `alert_pause` | Pause a stored alert rule (active=false). Use to silence alerts. | `rule_id: int` | **RW** | PG/file |
| `alert_resume` | Resume a paused alert rule (active=true). Use to re-enable alerts. | `rule_id: int` | **RW** | PG/file |

### quant.py → preset `quant` — 4 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `quant_backtest` | Buy-and-hold backtest with costs over available history. Use for baseline stats. | `symbol: str, cost_bps: float = 10.0` | RO | vnstock candles → local backtest |
| `quant_risk` | Sharpe, max drawdown and win rate from a return series. Use to gate models. | `returns: list[float]` | RO | thuần local (statistics) |
| `quant_factors` | Momentum, volatility and drawdown factors from candles. Use to expand features. | `symbol: str = "VCB"` | RO | vnstock candles → local |
| `scenario_simulate` | Apply a price shock to latest close and report P/L per 1000 shares. Use for sizing. | `scenario: str, symbol: str = "VCB", shock_pct: float = -5.0` | RO | vnstock candles → local |

### brief.py → preset `brief` — 5 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `brief_build` | Compose morning brief from news, odds and calendars. Use at session start. | `scope: str = "vn"` (vn\|world) | RO | fear_greed + Vietstock news → GDELT fallback + vs_categories + world pins |
| `news_market` | Market news: Vietstock first, GDELT fallback. Use for catalyst checks. | `limit: int = 10` | RO | Vietstock dc.vietstock.vn → GDELT → unavailable |
| `news_symbol` | Symbol news via Vietstock search. Use to verify rumors. | `symbol: str, limit: int = 10` | RO | Vietstock dc (không fallback) |
| `economic_calendar` | Macro series catalogue as event proxy. Use for data-availability checks. | `scope: str = "vn"` (≠vn → empty + warning) | RO | vs_categories |
| `corporate_calendar` | Disclosures feed as corporate actions. Use for dividend/meeting scans. | `symbol: str \| None = None` (default "VCB") | RO | Vietstock GetDocument |

### intel.py → preset `intel` — 6 tools

| Tool | Descriptor (client thấy) | Params | Quyền | Data source |
|---|---|---|---|---|
| `world_prediction_odds` | Prediction-market odds via jina proxy to Gamma, then direct. Use for Fed/macro odds. | `query: str \| None = None` | RO | jina `r.jina.ai` → Gamma API direct (Kalshi/Manifold chưa implement) |
| `geo_intel` | Geopolitical coverage via GDELT. Use when geopolitics threatens markets. | `topic: str \| None = None` | RO | GDELT API (retry 1 lần) |
| `assets_rotation` | Cross-asset 1y momentum classes into RISK-ON/OFF. Use for allocation reads. | — | RO | yfinance 2y → local rule classify |
| `compare_equities` | Head-to-head overview rows and momentum. Use when picking tickers. | `symbols: list[str]` (cap 4) | RO | vs_overview + vn quote |
| `evidence_bundle` | Lock weighted conclusion by evidence bundle. Use last for final verdict. | `claim_ids: list[str]` | RO | local (không upstream) |
| `oracle_meta` | Aggregator snapshot plus source health. Use for dashboard meta. | — | RO | yf_market_pins + source_status |

> Ghi chú gating: `web_search` chỉ xuất hiện khi có `EXA_API_KEY`/`PARALLEL_API_KEY` → market = 68/69, intel = 7/8, all = 125/126 khi không có key. Đếm chuẩn: **126 tools unique · 117 RO / 9 RW · market 69/70 · scan 42/50 · quant 4 · brief 5 · intel 8/50 · all 126**. `ctx: AnyContext` bị FastMCP loại khỏi schema nên không liệt kê ở cột Params.

## Phụ lục — Descriptor review 2026-09-30 (bản v5)

Descriptor LLM thấy = tên function + docstring (dòng đầu là "làm gì + Use...", phần sau giải
thích params) + signature (FastMCP tự loại `ctx`). Logic thật ở `providers/` — LLM không thấy.

### Lỗi đã tìm thấy và đã sửa (toàn bộ 126 tools, 17 file `tools/*.py`)

**Critical (5)**
- `dnse_ohlc_history`: docstring có ghi chú dev "do not remove" — đã viết lại descriptor chuẩn, giữ logic.
- `money_flow`: thiếu mệnh đề Use — thêm "Use for smart money" + mô tả `symbols` (default ["VNINDEX"], fallback Vietstock NN).
- `alert_check`: không mô tả schema `rules` — thêm `{symbol, threshold, metric 'price'|'rsi14', op '>'|'gt'|'>='|'gte'|'<'|'lt'|'<='|'lte'|'cross_up'|'cross_down'}`.
- `stock_screener filters`: thêm format `{field: [min,max]}` (None = unbounded), chuỗi = equality cho symbol/exchange, dùng `signals_screener_columns` để tra field.
- `evidence_bundle`: mô tả rõ `claim_ids` (claim cần lock) vs `calc_ids` (calculation hỗ trợ, `[]` nếu không có).
- `runs_list id` vs `run_get run_id`: tách rõ — `id` filter substring trong list, `run_id` exact id lấy 1 run.

**Major (~45 tools thiếu enum/format) — đã bổ sung**
- `dnse_ohlc_history`: resolution 1/5/15/30/60 phút, bar_type 'derivative'/'index', dates ISO, summary `{symbol,count,last,high,low}`, columns t/o/h/l/c/v.
- `valuation_run`: btype 1 tổng hợp/2 CK/3 NH/5 bảo hiểm; method 'auto'|'dcf'|'per'|'pb'|'ev'|'ensemble'.
- `vs_indicator_data`: termTypeID map (1 Ngày/2 Tháng/3 Quý/4 Năm/5 YTD/6 MoM/7 YoY/8 QoQ).
- `vs_financial_values`: tids (1 năm đủ, 2-4 Q1-Q3, 5 Q4, 9 H1, 12 9M).
- `vs_financeinfo`/`financial_statements`: period 'quarter' (12 quý) | 'year'; statement section 'KQKD'/'CDKT'.
- `vn_fundamentals`: period 'year'|'quarter'; report_type 'ttm'|'latest'.
- `signals_technical`: indicators (rsi14, macd, sma20, recommend...), omit = full set; interval ≠ '1D' được nhận nhưng bỏ qua (daily only).
- `quant_backtest`: strategy chỉ là label (engine buy-and-hold); cost/slippage bps trừ 2 chiều ×2.
- `quant_risk`: periods_per_year 252 ngày/52 tuần/12 tháng.
- `scenario_simulate`: shock_pct %, âm = giảm (vd -5.0).
- `compare_assets`: timeframe '1d'(2d/1d)|'1wk'(3mo/1wk)|'1mo'(1y/1d); assets tối đa 10.
- `yf_alloc_history`: asset GC|VND|BTC|OIL|SILVER|COFFEE (lệch → GC), timeframe 1d|1wk, trả 60 điểm/5y.
- `yf_oracle_markets`: groups crypto/metals/energy/agri/bonds_fx/index.
- `market_snapshot`: as_of chỉ là label ghi vào `requested_as_of`, data luôn latest.
- `breadth_scan`: exchange HOSE/HNX/UPCOM, bị bỏ qua + warning khi rows không có venue.
- `brief_build`: scope 'vn'|'world', date ISO (ghi nguyên).
- `economic_calendar`: chỉ 'vn', khác → empty + warning; không phải calendar thật (dates → `dnse_working_dates`).
- `web_search`: num_results (8), livecrawl 'fallback'|'preferred', search_type 'auto'|'fast'|'deep', context_max_chars.
- `web_fetch`: format 'markdown'|'text'|'html', timeout_seconds 30.
- `alert_create`: metric 'price'|'rsi14'; op '>'|'>='|'<'|'<=' (nhận 'gt'/'gte'/'lt'/'lte').
- `dnse_orderbook`: depth levels mỗi bên (3); `dnse_indices`: symbols default VNINDEX+VN30; `dnse_vn30f1m_live`: bars = số nến 15m cuối.
- Batch tools (`dnse_latest_trade`, `market_candles_batch`, `vn_quote_history`, `vn_equity_quote_batch`, `vn_index/equity/futures_ohlcv`, `vn_forex/crypto/global`): chuẩn hóa mô tả summary `{count,last,high,low}` / `{count,symbols}` và columns giữ field.
- Còn lại: `insider_trading limit`, `signals_scan limit`, `run_get run_id exact`, `dnse_orderbook depth`, `market_movers top_n`, `symbol_lookup limit`, `vs_market_info symbol '' = cả board`, `vs_stock_industry industry_id từ vs_industry_tree`, `sector_performance level/top_n`, `pattern_match lookback`, `signals_trade_log days/side`, `event_stats limit`, `peer_compare peers ≤5`, `world_prediction_odds limit/status/tag`, `geo_intel limit/days`, `news_market/news_symbol sources='gdelt'`, `macro_reports limit`.

### Disambiguation (đã thêm câu phân biệt vào descriptor)
- Flows ×5: `dnse_foreign_flow` primary WS · `vs_nn_flow` cross-check · `foreign_flow` alias của dnse · `mega_flows` alias yf (global, không phải DNSE) · `money_flow` composite (WS → Vietstock fallback).
- News ×3: `news_symbol` pre-scoped symbol · `vs_news_search` free-text engine (dùng cho topic) · `news_market` overview.
- Disclosures ×3: `company_events` phân loại theo kind · `corporate_calendar` raw feed · `vs_documents` filings kèm link.
- Calendars ×4: `dnse_working_dates` ngày giao dịch thật · `exchange_calendar` mechanics tĩnh (giờ, ATO/ATC, T+) · `economic_calendar` proxy catalogue (không phải calendar) · `corporate_calendar` sự kiện DN.
- Reports ×2: `macro_reports` thư viện macro/strategy · `vs_reports_search` analyst notes theo symbol.
- Statements ×3: `vs_financeinfo` gốc · `financial_statements` alias v3 (wraps vs_financeinfo) · `vn_fundamentals` vnstock ratios+statements.

### Verify
- `uv run pytest tests/ -q --ignore=tests/contract/test_verify_matrix.py` → **175 passed**.
- `ruff check` + `ruff format --check` (17 file tools) → sạch. `mypy src/opentrading_mcp/tools/` → 0 issue.
- Local `list_tools()` preset `all` → **125 tools** (web_search gate theo key), 0 tool thiếu descriptor; 14 chuỗi disambiguation đều OK trong descriptor live.

## Phụ lục — P7 tools mới 2026-09-30 (review MCP tài chính ngoài, 142 tools)

Nguồn đối chiếu: Alpha Vantage official, FMP 250+ tools, EODHD 72, Finnhub 15,
Unusual Whales 200+, Equibles 95, Alpaca 65, yfinance-mcp 30, QuantConnect 64,
CCXT official, OpenBB MCP. Chỉ lấy cái VN làm được; bỏ options/Greeks/GEX/IV
(không có listed options), short interest (cấm bán khống), 13F/congressional,
transcripts, ESG (không tương đương VN).

### Tools mới (17) + prompts/resources

| Tool | Học từ | Nguồn | Preset |
|---|---|---|---|
| `dividends_splits` | yfinance-mcp get_dividends/splits | vnstock `Company.events()` (DIV/ISS) / yfinance actions | scan (corp) |
| `holders` | yfinance-mcp holders ×3 | vnstock shareholders / yfinance major/institutional/mutualfund | scan (corp) |
| `correlation_matrix` | QC-mcp | local, inner-join dates (walkback khi t day-only) | quant |
| `seasonality` | UW seasonality | local, rolling-window theo tháng | quant |
| `backtest_strategies` | QuantConnect | local sma_cross/momentum/buy_hold (quant_backtest vẫn buy-hold) | quant |
| `portfolio_optimize` | QC-mcp portfolio | numpy-only equal/inv_vol/max_sharpe long-only heuristic (xem quyết định scipy) | quant |
| `param_sweep` | QC create_optimization | local grid ≤30 combos | quant |
| `crypto_spot` | CCXT get_tickers | Binance public `/ticker/24hr` (không key) | market (crypto) |
| `crypto_derivs` | UW flow-style | Binance fapi funding/OI/LSR/taker-ratio (forceOrders cần key → thay taker) | market (crypto) |
| `market_overview` | FMP get_market_context | composite quotes+movers+breadth+session, legs degrade độc lập | market |
| `event_calendar_vn` | AV/EODHD calendars | Vietstock `eventstypedata` (1 dividends/2 listings/5 meetings; không có earnings-dates) | scan (corp) |
| `block_trades` | UW dark pool (tương tự chức năng) | Vietstock `gettradingresult` MT_* vs PT_* thỏa thuận | scan (corp) |
| `analyst_consensus` | yfinance price_targets | scrape Vietstock titles (rating+target; vs_reports_search API chết 404) | scan (corp) |
| `ipo_calendar_vn` | AV/EODHD IPO calendar | HNX lich-dau-gia + fallback tin-cong-bo (verify=False, cert HNX) | scan (corp) |
| `futures_basis` | UW futures | DNSE F1M − VN30 spot (DNSE không có field OI — đã probe SDK schema) | scan (corp) |
| `sbv_rates` | EODHD treasury | scrape sbv.gov.vn static (policy + interbank) | brief |
| `macro_events_vn` | EODHD economic events | scrape NSO (gso.gov.vn đã chết → nso.gov.vn; CPI section.item spans) | brief |
| prompts ×4 | UW/EODHD/Tiingo | morning_briefing, ticker_analysis, pre_earnings, sector_rotation | mọi preset |
| resources ×4 | EODHD embedded docs | catalog/tools (live), term-types, exchanges, gics | mọi preset |

### Nâng cấp tools cũ (U1–U5)
- U1 `stock_screener` + `technical` stage-3 (rsi_lt/gt, above/below_sma20) trên candidates.
- U2 `market_snapshot` giữ nguyên + tool mới `market_overview` (tránh đổi contract).
- U3 `technicals.compute` + patterns (doji/hammer/engulfing) + support/resistance 20d.
- U4 `money_flow` descriptor cross-ref `block_trades` (khác granularity, không gộp code).
- U5 `brief_build` + `calendars: bool = False` (thêm sbv/macro/ipo khi bật).
- Bulk cap `market_candles_batch` 50→100 (test P1 cập nhật theo).

### Quyết định kỹ thuật (ghi để khỏi đào lại)
- **Bỏ scipy**: `uv add` kẹt resolver ở cây dep vnstock (cả khi pin); optimize dùng numpy-only.
- **Bỏ pypdf**: cùng nguyên nhân; `disclosure_fulltext` drop (chỉ còn metadata/link ở vs_documents).
- **Bỏ**: `earnings_dates` (eventstypedata không có loại này), OI (không tồn tại), liquidations
  (forceOrders 401 cần key), paper_trade (user chốt không làm), live execution (chờ duyệt riêng).
- **Không đụng**: Dockerfile/pyproject/cli Phase 0-2, `vs_reports_search` (chết upstream nhưng giữ
  contract unavailable trung thực), preset caps cũ trừ market 70→75, scan 50→60.
- Env quirk: `t` của vnstock v4 chỉ là ngày-trong-tháng → tools quant dùng ISO khi có,
  fallback business-day walkback + `date_note` trong output.
- HNX cần `verify=False` (cert chain) + warning `tls-unverified`; Binance array phải không-space.

### Verify P7
- `pytest tests/ -q --ignore=verify_matrix` → **217 passed** (175 cũ + 42 mới).
- `ruff check` + `format --check` sạch (trừ drift có sẵn test_p2/p4 không đụng).
- `mypy`: sạch trừ `pandas-stubs` pre-existing ở technicals.py:13.
- Live `list_tools()`: market 71 · scan 49 · quant 9 · brief 5→7 · intel 7 · **all 142**,
  0 thiếu descriptor; Binance/Vietstock/HNX/NSO/SBV đã probe live thành công.

## Phụ lục — P8 prompts AI-detect + risk + pre-earnings-v2 (2026-09-30)

Đổi hướng theo chốt: chỉ breakout (bỏ BCD/ranking), 8010 tham khảo-only (không tools
nối 8010), P5 risk_check và triết lý grading pre-earnings đã duyệt.

### 8010 reference (không copy code, không nối mạng)
- SEPA = Breakout Model 2 (`research_team/signals/breakout.py`, `model_2.pkl`):
  gate `is_breakout==1` trên Redis features → predict_proba → giữ iff ≥0.85 → PG.
- BCD = Model 1 (`bcd.py`, `model_1.pkl`): gate `breakdown==1` → điểm B/C + breakdown.
- Ranking = super_stock LightGBM (`/api/super-stock/scores`, prob_x2, precision@k=20).
- Không port được (cần pickle + Redis feature store + PG 8010) → prompt mô phỏng
  heuristic + descriptor ghi rõ "no ML probability".

### Prompts (6, trong `prompts.py`)
- `ai_detect(symbol?)` mới: 5 legs (trend template / contraction / breakout confirm /
  fundamentals / flow) → STRONG(≥4)/WATCH/REJECT. Không symbol → signals_scan rồi
  validate từng hit. Không tool mới.
- `risk_check(symbols, side, size_vnd)` mới: quant_risk → scenario_simulate scale size →
  correlation → forensic → events blackout → valuation → GO/HALF/NO-GO + size + unknowns.
- `pre_earnings` THAY v1: reliability grading A/B/C 6 chân + unknowns (không đặt
  surprise level vì VN không có EPS consensus).
- Refresh giữ tên: `morning_briefing` (+market_overview, futures_basis),
  `ticker_analysis` (+forensic/insider/consensus), `sector_rotation` (+basis/ipo).

### Upgrades tool cho SEPA legs (pure-local, 0 upstream mới)
- `technicals.compute(benchmark=)`: + `rs_vs_bench` (spread 63d, pct points, None khi
  <20 điểm chung), + `pos_52w` (vị trí trong biên 250d, flat → 0.5), + `sma150`.
- `signals_technical`: fetch VNINDEX 250d best-effort (fail → warning, RS=None).

### Verify P8 (live 2026-09-30)
- pytest 229 passed (217 + 12 mới); ruff + format sạch; mypy chỉ 4 lỗi pre-existing.
- Live: 142 tools, 6 prompts, 4 resources. VCB legs thật: dưới sma50/150/200,
  adx 11.81, RS −1.89, pos_52w 0.21 → REJECT đúng rubric.

## Phụ lục P14 — macro thật + storage + tối ưu (2026-10-01 tối)

### Điều tra macro (bạn đúng, tôi đã sửa kết luận)
- **Standard pack LẤY ĐƯỢC vĩ mô VN đầy đủ** — bằng chứng replay HAR full-cookie:
  GDP(73,tt3) 504 rows tới Q2/2026 · CPI(15,tt7+sub2) 1,839 · XK(38,tt2) 2,941 ·
  XNK theo nước(64/65,tt2) 3,675 · FX(55,tt1) 75. "Yêu cầu nâng cấp" trước đó là
  do **session-gate** (CookieLogin đơn + session mới bị chặn; full cookie-jar trình duyệt
  + token postData thì được) và **termTypeID sai** (GDP tt=2 → đúng là tt=3).
- Fix: `providers/vietstock.py` thêm **HAR-session mode** (`har_client()`): ưu tiên env
  `VIETSTOCK_COOKIE_HEADER`+`VIETSTOCK_PAGE_TOKEN` → parse `docs/*.har` (file, không commit).
  `macro_report_data()` pipe-parser (DataStructure 16 cột → name/group/period/year/value/unit).
- `vs_indicator_data` + `vs_xnk_detail` wire xong, **live xanh** (số thật).
- CTKH/planned_targets: provider xong, live đang **session-rejected** (302) — dormant
  trung thực, chờ env cookie mới từ trình duyệt.
- GetStockByGICS replay flaky → skip.

### Storage theo ngày (quyền DB của bạn)
- 8010 retire → **DB mới `opentrading_mcp`** trong PG 15432 (không đụng db cũ); `dbinit`
  idempotent 6 bảng (watchlists/items, alert_rules, mcp_auth_tokens, mcp_tool_usage
  schema (user,tool,day,count,total_ms), **daily_snapshots(date,kind,payload JSONB)**).
- Watchlist `_pg()` auto-ensure; **write-fallback file** khi SQL lỗi (đúng docs).
- Worker thêm **`snapshot_loop`** (17:15 VN/ngày): `snapshot_once()` best-effort 12 kinds —
  live 10/12 ok (vn30_quotes transient db-down, tự hồi ngày sau).
- Tool mới **`snapshot_history(kind, days)`** đọc lịch sử (fix bug JSONB-list).

### Tối ưu catalog (a/b/d/e đã duyệt)
- Xóa: `macro_reports` (gộp analyst_consensus) + 3 alias `mega_flows/foreign_flow/oracle_health`.
- Thêm: `polymarket_event(slug)` (odds đầy đủ outcomes+prob_pct) + `planned_targets` +
  `snapshot_history`; `world_prediction_odds` nâng cấp (query cả slug/description, tag
  Polymarket thật, sort vol24h).
- `market_snapshot` default **VN30-30 mã**; `market_overview` retry ×2; `signals_scan`
  `universe/exchange/max_symbols≤300` + progress + truncated.
- `news_symbol` default-path **GDELT fallback** (dc chết).
- pre_earnings prompt leg-4 đổi thành expectation anchor = planned_targets.
- Catalog: **136 tools** (market 66 · scan 47 · quant 9 · brief 7 · intel 8 · all 136; web_search ẩn khi thiếu key).

### Env checklist Render (bạn làm trên Dashboard)
- `VIETSTOCK_COOKIE_HEADER` + `VIETSTOCK_PAGE_TOKEN` (từ HAR trình duyệt mới nhất) — mở macro/CTKH.
- `FRED_API_KEY` (có trong Trading_Agents .env), `DATABASE_URL` (Render PG),
  `REDIS_URL`, `MCP_BEARER_TEAM`, `DNSE_API_KEY/DNSE_SECRET`, `VIETSTOCK_COOKIE_LOGIN` (JWT 31/10).
