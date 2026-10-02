# Tools Review — opentrading-mcp (worktree 2026-10-01, P14)

**Tổng: 135 tools unique · 126 READ_ONLY / 9 READ_WRITE · 6 presets**
(P5 enrich params → P6 descriptors → P7 17 tools mới → P8 SEPA legs → P10/P11 fixes → P12/P13 xóa tools chết → P14 macro HAR-session + storage + polymarket_event + planned_targets; xem Phụ lục cuối file)

| Preset | Tools | Cap | Modules |
|---|---|---|---|
| market | 65 (64 khi không có websearch key) | 75 | market(8), web, vn, vs, vs_bctc, vn_ext, yf, yf_world, dnse_tools, dnse_ext, crypto |
| scan | 47 | 60 | scan(6) + compute(20) + watchlist(12) + corp(9) |
| quant | 9 | 50 | quant |
| brief | 7 | 50 | brief |
| intel | 8 (9 khi có websearch key — web_search gate theo key) | 50 | intel(7) + web(1+1 key) |
| all | 135 (136 khi có websearch key) | không cap | 18 modules |

TIMEOUT_MATRIX (contract client): tools_list 30, market_snapshot 15, breadth_scan 15, vs_financial_values 60, yf_mega_flows 60, dnse_ohlc_history 60, quant_backtest 120, quant_factors 120, stock_screener 60, signals_screener_columns 30, watchlist_get 30, alert_check 30.

## 1. market.py — 8 tools (P14: market_overview mới)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| market_snapshot | Snapshot of VN market with provenance. Use when a broad market picture is needed. | symbols? (default VN30-30 mã, P14) | vnstock quote_batch; cache Redis TTL 60s |
| source_status | Health of every upstream plus TTL state. Use to debug stale data. | — | local health aggregator (Redis keys, JWT, env) |
| market_candles_batch | Batch OHLCV for symbols, one request per symbol. Use for multi-chart context. | symbols[] (cap 100, P7 nâng từ 50), days=30, summary=False, columns[]? | vnstock VCI→KBS per symbol; missing[] cho symbol lỗi; availability partial |
| symbol_lookup | Resolve company name to symbol, venue and sector. Use before any symbol-scoped call. | query, limit=10 (P5; P9 accent-insensitive: "hoa phat" → HPG) | vnstock Listing + Reference (NFD fold + Đ→D, stdlib) |
| market_movers | Top gainers, losers and volume leaders. Use for session pulse checks. | top_n=10 (P5) | snapshot local (universe hardcode VN30) |
| market_overview | One-call market context: bluechip quotes, movers, breadth, session. Use for briefs. | top_n=3 (P14: quotes leg retry ×2) | vnstock bluechip batch + DNSE WS session; legs degrade độc lập (partial) |
| breadth_scan | Advancers, decliners, ceiling and floor counts. Use to judge rally health. | — (P11: đếm case-insensitive Change/Exchange) | Vietstock getmarketprice + marketinfo |
| dnse_market_status | DNSE session state plus latest index snapshot. Use for open/close checks. | — | DNSE WS cache → DNSE REST trades/latest → unavailable |

## 2. web.py — 2 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| web_fetch | Fetch a URL and convert to markdown, text or html. Use for reading web content. | url, format=markdown, timeout_seconds=30 | direct httpx browser-UA; CF 403 retry UA "opencode"; cap 5MB |
| web_search | Search the web via Exa/Parallel providers. Use for up-to-date information. | query, num_results=8, livecrawl=fallback, search_type=auto | Exa hoặc Parallel (WEBSEARCH_PROVIDER / hash query); ẨN khỏi tools/list khi thiếu key |

## 3. vn.py — 6 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| vn_quote_history | Daily candles for a VN symbol, VCI then KBS fallback. Use for any price history. | symbol, days=365, summary=False, columns[]? | vnstock Quote VCI→KBS tự fallback |
| vn_equity_quote_batch | One-request price board for many symbols. Use for snapshots and movers. | symbols[], summary=False, columns[]? | vnstock Market.equity(list).quote() |
| vn_listing | Full symbol list with company names. Use for universe and lookup. | — | vnstock Listing().all_symbols() |
| vn_fundamentals | Ratios and statements via vnstock Fundamental and Finance. Use for quick valuation. | symbol, period=year | vnstock Fundamental + Finance |
| vn_retail_gold | SJC and ring gold buy/sell from BTMC retail. Use for local gold premium. | — (P11: fetch https trực tiếp 15s + fallback vnstock; lib http treo) | BTMC JSON trực tiếp → vnstock Retail fallback |
| vn_retail_fx | VCB USD buy/sell rates. Use for currency conversion context. | — | vnstock Retail VCB |

## 4. vs.py — 8 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| vs_auth_status | Vietstock JWT state and expiry. Use before any paid BCTC call. | — | Vietstock session (env → seed → login) |
| vs_financeinfo | Free-mirror statements, 12 quarters or years. Use when JWT is absent. | symbol, period=quarter | Vietstock /data/financeinfo mirror |
| vs_market_price | Live board snapshot from Vietstock. Use as secondary quote source. | — | Vietstock /data/getmarketprice |
| vs_market_index | Index closes with 1M and YTD change. Use for index context. | — | Vietstock GetMarketIndexVNData |
| vs_nn_flow | Foreign investor buy/sell chart. Use to cross-check DNSE WS flows. | days=90 (P10: gửi selectType/code/type/isRealTime) | Vietstock KQGDGiaoDichNDTNNChart (tail N điểm) |
| vs_categories | Macro indicator catalogue (~60 categories). Use before indicator queries. | — | Vietstock Macro GetIndicatorCategoryData |
| vs_indicator_data | Macro series for a category and term type. Use for GDP, CPI, trade context. | category_id, term_type_id=3, to_date default today (P10; paid package) | Vietstock Macro (không gói → RequestUpgradeAccount) |
| vs_trading_info | Ceiling, floor, room, EPS, BVPS, PE, PB per symbol. Use for reference snapshot. | symbol | Vietstock /company/tradinginfo |

## 5. vs_bctc.py — 12 tools (P12 xóa 3, P13 xóa news_search, P15 xóa vs_financial_values)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| vs_financial_terms | Report term catalogue (annual, Q1-Q4, H1, 9M). Use before BCTC value queries. | — | Vietstock GetListReportTerm |
| vs_financial_norms | 190+ BCTC line items for a business type. Use to resolve norm ids. | btype=1 | Vietstock BCTC_GetChiTieuForTable |
| vs_company_info | Company names, exchange and description. Use for profiles. | symbol | Vietstock BCTC_CompanyByCodes |
| vs_overview_trading | EPS, BVPS, PE, PB, ROEA/ROAA snapshot. Use for valuation inputs. | symbol | Vietstock GetStockDeal_OverviewTrading |
| vs_documents | Filings and disclosures with links. Use for corporate actions. | symbol | Vietstock /data/GetDocument |
| vs_industry_tree | GICS industry tree. Use before sector mapping. | — | Vietstock GetTreeViewIndustryGICS |
| vs_industry_heatmap | Live sector heatmap. Use for intraday rotation. | — | Vietstock GetHeatmapGICS |
| vs_selftrading | Prop-desk flow chart. Use alongside foreign flows. | — (P10: cùng shape selectType/code/type) | Vietstock KQGDGiaoDichTuDoanhChart |
| vs_gics_index | GICS index closes with foreign flow. Use for sector context. | group=1 (P10 mới: 1/2/3) | Vietstock GetGICSIndexMain {type} |
| vs_currency | Reference FX table. Use as fallback FX source. | — | Vietstock GetCurrency |
| vs_market_info | Per-exchange board row: index, breadth, put-through. Use for 5s snapshots in hours. | exchange=HOSE (P10 đổi từ symbol) | Vietstock /data/marketinfo {type 1/2/3} |
| vs_xnk_detail | Import/export by country. Use for trade structure (termType 2). | direction=xk, to_date default today (P10; paid package) | Vietstock Macro listID 64/65 |

## 6. vn_ext.py — 10 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| vn_index_ohlcv | Index bars for VN tickers. Use for index history and breadth. | symbol=VNINDEX, count=100, summary=False, columns[]? | vnstock Market.index VCI |
| vn_equity_ohlcv | Equity bars via Market API. Use as OHLCV alternative to quotes. | symbol, count=100, summary=False, columns[]? | vnstock Market.equity VCI |
| vn_futures_ohlcv | Futures bars. Use for derivatives backtest input. | symbol=VN30F1M, count=100, summary=False, columns[]? | vnstock Market.futures |
| vn_forex_ohlcv | FX bars. Use for currency context. | pair=USDVND, count=30 | vnstock Market.forex |
| vn_crypto_ohlv | Crypto bars. Use for digital-asset regime reads. | symbol=BTCUSDT, count=30 | vnstock Market.crypto |
| vn_global_index | Global index bars. Use as yfinance fallback. | symbol=USA30, count=30 | vnstock Market.index scope=global |
| vn_reference | ICB reference by exchange, group or industry. Use for universe construction. | exchange=HOSE (P11: list_by_exchange source KBS có cột exchange) | vnstock Reference KBS (HOSE 757/HNX 396/UPCOM 818), filter local |
| vn_company | Profile, holders and officers. Use for company research. | symbol | vnstock Company VCI |
| vn_msn_fx_gold | USDVND and XAUUSD via MSN. Use for gold-basis math. | — | vnstock explorer.msn |
| vn_trades | Tick-level matched trades. Use for microstructure reads. | symbol, limit=20 | vnstock Market.equity.trades |

## 7-8. yf.py (3) + yf_world.py (6)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| yf_global_indices | 9 global benchmarks, 2d daily. Use for overnight context. | — | yfinance GLOBAL_9; worker loop pump TTL 300s |
| yf_commodities | Gold, oil, metals, BTC, VND and dollar index. Use for input-cost context. | — | yfinance COMMO_13 |
| yf_yield_curve | US 2Y/10Y and inversion flag. Use for rates and regime context. | — | yfinance ^TNX + 2YY=F |
| yf_world_indices | 24 world benchmarks. Use for global breadth. | — | yfinance batch download |
| yf_oracle_markets | 40 markets in 6 groups with 30d stats. Use for cross-asset state. | — | yfinance ~40 ticker 1mo |
| yf_regime_assets | 7 regime drivers with 2y history. Use for RISK-ON/OFF calls. | — | yfinance 2y + rule classify |
| yf_mega_flows | Mega-cap leader flows. Use to follow global smart money. | — | yfinance 15 mega-cap + Nasdaq-style screener |
| yf_alloc_history | Long allocation history per asset. Use for regime backtests. | asset=GC, timeframe=1d | yfinance 5y |
| yf_market_pins | 5-day pins for world majors plus VN watchlist. Use for brief headers. | — | yfinance world majors |

## 9-10. dnse_tools.py (4) + dnse_ext.py (5, P13 xóa foreign_rest)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| dnse_ohlc_history | Paginated futures/index bars via cursor. Use for VN30F1M backtest input. | symbol=VN30F1M, resolution=15, bar_type=derivative, from_date=2018-08-01, summary=False, columns[]? | DNSE REST /price/ohlc HMAC |
| dnse_latest_trade | Latest match price and totals per symbol. Use for realtime fallback. | symbols[] | DNSE REST /price/{s}/trades/latest |
| dnse_foreign_flow | Net foreign flow from WS cache. Use as primary smart-money read. | — | DNSE WS foreign.* qua Redis (fallback chỉ ra warning: vs_nn_flow) |
| dnse_ws_snapshot | Raw worker snapshot for symbols. Use to debug realtime staleness. | symbols[]? | Redis mcp:market:dnse_ws_snapshot:{sym} TTL 30s (worker publish) |
| dnse_orderbook | Bid/ask depth. Use for microstructure reads. | symbol, depth=3 | DNSE REST quotes/latest → fallback /quotes |
| dnse_indices | Index snapshots from WS cache. Use for live index reads. | — | DNSE WS market_index.* Redis (fallback ra warning: vs_market_index) |
| dnse_vn30f1m_live | VN30F1M 1m bars aggregated to 15m with session remap. Use for intraday. | — | DNSE REST 1m (7 ngày) → local agg 15m remap 14:30→14:45 |
| dnse_working_dates | Trading calendar. Use for session planning. | — | DNSE REST /market/working-dates |
| exchange_calendar | HOSE/HNX/UPCOM hours, ATO/ATC, T+ settlement. Use for mechanics. | — | static local |

## 11. scan.py — 6 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| stock_screener | Screen universe by valuation and quality. Use when hunting candidates. | filters{}?, max_pe?, min_roe?, limit=20, technical={rsi_lt,rsi_gt,above_sma20,below_sma20}? (P7 U1 stage-3) | vnstock Listing + equity_fundamentals enrich (semaphore 5, 10s/symbol) + local apply_filters + technical stage trên candidates |
| signals_screener_columns | Screener column catalog (valuation/quality/universe/price). Use to build filters. | group?, search? | local catalog (close/change_pct/sector/industry/index non-filterable) |
| signals_technical | Full technicals rating from local candles (daily only). Use for timing entries. | symbol, interval="1D" (khác 1D → warning), indicators[]? (P6: rsi14/macd/sma20/recommend/patterns/support/resistance; P8 thêm rs_vs_bench/pos_52w/sma150) | vnstock candles (250d) + VNINDEX benchmark best-effort → pandas RSI/Stoch/CCI/ADX/MACD/MOM/AO/EMA/SMA/SMA150/VWMA/Hull/BB/ATR + patterns(doji/hammer/engulfing) + support/resistance 20d + RS spread 63d + pos_52w + recommend |
| sector_performance | GICS heatmap rows. Use for sector rotation reads. | level=1 | Vietstock GetHeatmapGICS |
| money_flow | Compose foreign flow: DNSE WS then Vietstock cross-check. Use for smart money. | — (P10 + P12b: fallback dùng nn_flow_chart có params, không còn {}) | DNSE WS → Vietstock NN chart → unavailable |
| alert_check | Evaluate price/RSI rules against live quotes. Use for live watch. | rules[{symbol,metric,op,threshold}] | metric price: vnstock quote; rsi14: vnstock candles → technicals local; cross state Redis TTL 3600 |

## 12. compute.py — 20 tools (P14: -macro_reports/-mega_flows/-foreign_flow/-oracle_health, +snapshot_history)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| stock_forensic | Beneish M-Score (7 chỉ số, partial) + Piotroski F 6/8 từ full detail (P15 rewrite, live FPT M=-2.06). Use for earnings-quality flags. | symbol, detail?, periods_n=4 | KQKD/CDKT detail (DSRI/GMI/AQI/SGI/SGAI/LVGI/TATA; CFO thiếu khi LCTT rỗng) → local tính |
| snapshot_history | Daily-snapshot history saved by the worker (P14 MỚI). Use for data that vanishes. | kind (13 kinds), days=90 | PG daily_snapshots (worker 17:15 VN/ngày) |
| valuation_run | PER/PB ensemble with DCF-lite. Use for fair-value ranges. | symbol, btype=1 | vs_overview + vn quote → local |
| fred_series | FRED observations. Use for US macro context. | series_id, limit=60 | FRED API (FRED_API_KEY) |
| world_macro_country | WorldBank series per country. Use for global GDP/CPI/debt context. | iso3, indicator | WorldBank v2 |
| world_fear_greed | Crypto fear/greed index. Use for risk-appetite reads. | — | alternative.me |
| sentiment_score | Crowd sentiment from Fireant posts, Groq-scored. Use for hype risk. | symbol (P12b: chịu body list trần + heuristic khi thiếu Groq) | Fireant → Groq (fallback heuristic likes) |
| insider_trading | Insider deals via vnstock Company. Use for informed-flow reads. | symbol, limit=10 | vnstock Company VCI→KBS |
| stock_overview | Trading info plus company profile. Use for quick dossiers. | symbol | vs_trading_info + vs_overview + vn_company |
| company_events | Classified disclosures and corporate actions. Use for event calendars. | symbol | vs_documents + company |
| financial_statements | Mirror statements alias (v3 compat). Use for statement reads. | symbol, period=quarter | vs_financeinfo |
| financial_ratios | Overview plus vnstock ratios merged. Use for ratio screens. | symbol | vs_overview + vn_fundamentals |
| peer_compare | Head-to-head overview rows. Use when picking tickers. | symbol, peers[] | overview batch cap 6 |
| signals_scan | Donchian-20d breakout scan (P14: universe/exchange/max_symbols≤300). Use to hunt momentum across the market. | universe?, exchange?, max_symbols≤300 | vn_reference pool + quote_history từng mã + progress + truncated |
| pattern_match | Self-similarity of return windows by correlation. Use for analogies. | symbol, lookback=60 | vnstock candles local correlation |
| event_stats | GDELT event counts for a query. Use for base-rate checks. | query | GDELT (retry 1 lần) |
| compare_assets | Cross-asset last prices via yfinance. Use for allocation reads. | assets[] cap 10 | yfinance |
| runs_list | Local run registry. Use to resume analysis sessions. | — | data/runs.jsonl (MCP_RUNS_FILE) |
| run_get | Local run registry fetch. Use to inspect past outputs. | run_id | data/runs.jsonl |
| doctor | Local self-check: env keys present, package versions. Use before handoff. | — | local |

## 13. quant.py — 4 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| quant_backtest | Buy-and-hold backtest with costs over available history. Use for baseline stats. | symbol, cost_bps=10.0, strategy=buy_hold (label), slippage_bps=5.0, benchmark=VNINDEX (P5) | vnstock candles → local |
| quant_risk | Sharpe, max drawdown and win rate from a return series. Use to gate models. | returns[], periods_per_year=252 (252/52/12) (P5) | thuần local |
| quant_factors | Momentum, volatility and drawdown factors from candles. Use to expand features. | symbol=VCB, lookback=60 (P5) | vnstock candles → local |
| scenario_simulate | Apply a price shock to latest close and report P/L per 1000 shares. Use for sizing. | scenario, symbol=VCB, shock_pct=-5.0 | vnstock candles → local |
| correlation_matrix | Pairwise Pearson correlation of daily returns. Use for diversification reads. | symbols[] cap 8, days=90 (P7 mới) | vnstock candles, inner-join dates (walkback + date_note khi t day-only) |
| seasonality | Rolling-window return stats per calendar month. Use for seasonal bias. | symbol, window=21 (5–63) (P7 mới) | vnstock 400d candles → local buckets |
| backtest_strategies | Rule-based backtests beyond buy-and-hold. Use to compare timing rules. | symbol, strategy=sma_cross (sma_cross/momentum/buy_hold), fast=10, slow=30, cost_bps=10.0 (P7 mới) | vnstock 365d → local engine (trades đếm entries, fee in+out/flip) |
| portfolio_optimize | Long-only weights by rule. Use for allocation starting points. | symbols[] cap 8, objective=max_sharpe (equal/inv_vol/max_sharpe), days=180 (P7 mới) | numpy-only (không scipy): closed-form clip long-only + fallback equal, kèm ann_vol/sharpe_proxy |
| param_sweep | Grid-search strategy lookbacks, ranked by net return. Use to avoid overfit picks. | symbol, strategy=sma_cross, fast_range[]?, slow_range[]? (product cap 30) (P7 mới) | vnstock 365d → local grid |

## 14. brief.py — 5 tools
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| brief_build | Compose morning brief from news, odds and calendars. Use at session start. | scope=vn (vn/world), date? ISO, calendars=False (P7 U5: True → thêm sbv/macro/ipo sections) | fear_greed + Vietstock news → GDELT + categories + world pins |
| news_market | Market news: Vietstock first, GDELT fallback. Use for catalyst checks. | limit=10, sources? (gdelt = bỏ Vietstock) (P5) | Vietstock dc → GDELT |
| news_symbol | Symbol news via Vietstock search. Use to verify rumors. | symbol, limit=10, sources? (P5) | Vietstock dc (không fallback) |
| economic_calendar | Macro series catalogue as event proxy. Use for data-availability checks. | scope=vn, limit=20 (P5) | vs_categories (scope≠vn → empty) |
| corporate_calendar | Disclosures feed as corporate actions. Use for dividend/meeting scans. | symbol?=VCB, limit=20 (P5) | Vietstock GetDocument |
| sbv_rates | SBV policy and interbank rates, scraped static page. Use for rate regime. | — (P7 mới) | scrape sbv.gov.vn (static, hiếm đổi) |
| macro_events_vn | NSO release listings with reference and next dates. Use for data calendar. | — (P7 mới) | scrape nso.gov.vn (gso.gov.vn đã chết; full-year schedule nằm trong PDF) |

## 15. intel.py — 7 tools (P14: +polymarket_event)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| world_prediction_odds | Polymarket odds via jina proxy to Gamma, then direct. Use for Fed/macro odds. | query? (title/slug/desc), tag? (tag_slug), limit (P14: outcomes+prob_pct, sort vol24h) | Gamma /events (jina-first) |
| polymarket_event | One Polymarket event detail by slug (every market + odds). Use to drill in. | slug (P14 mới) | Gamma /events?slug= + markets outcomes/prices |
| geo_intel | Geopolitical coverage via GDELT. Use when geopolitics threatens markets. | topic? | GDELT (retry 1) |
| assets_rotation | Cross-asset 1y momentum classes into RISK-ON/OFF. Use for allocation reads. | — | yfinance 2y → local rule |
| compare_equities | Head-to-head overview rows and momentum. Use when picking tickers. | symbols[] cap 4 | vs_overview + vn quote |
| evidence_bundle | Lock weighted conclusion by evidence bundle. Use last for final verdict. | claim_ids[] | local |
| oracle_meta | Aggregator snapshot plus source health. Use for dashboard meta. | — | yf pins + source_status |

## 16. watchlist.py — 12 tools (MỚI, P4)
| Tool | Descriptor | Params | Annotations | Source |
|---|---|---|---|---|
| watchlist_create | Create a named watchlist. Use to start tracking a symbol group. | name | READ_WRITE | Postgres → fallback file data/watchlists.json (atomic) |
| watchlist_list | List all watchlists with their symbols. Use to recall tracking state. | — | READ_ONLY | PG/file |
| watchlist_get | Get one watchlist's symbols by id. Use before quoting a saved set. | list_id | READ_ONLY | PG/file |
| watchlist_add | Add symbols (deduped, uppercase) to a watchlist. Use to track more. | list_id, symbols[] | READ_WRITE | PG/file |
| watchlist_remove | Remove symbols from a watchlist. Use to trim tracking. | list_id, symbols[] | READ_WRITE | PG (transaction, không fallback khi fail) |
| watchlist_delete | Delete a watchlist and its items (cascade). Use to clean up. | list_id | READ_WRITE | PG/file |
| watchlist_update | Rename a watchlist. Use sparingly; names are unique labels. | list_id, name | READ_WRITE | PG/file |
| alert_create | Create a stored alert rule (input to alert_check). Use for live watch. | symbol, op=">", threshold=0.0, metric="price" | READ_WRITE | PG/file; validate op ∈ {>,>=,<,<=,cross_up,cross_down} |
| alert_list | List stored alert rules (active and paused). Use before alert_check. | — | READ_ONLY | PG/file |
| alert_delete | Delete a stored alert rule by id. Use to clean up alerts. | rule_id | READ_WRITE | PG/file |
| alert_pause | Pause a stored alert rule (active=false). Use to silence alerts. | rule_id | READ_WRITE | PG/file |
| alert_resume | Resume a paused alert rule (active=true). Use to re-enable alerts. | rule_id | READ_WRITE | PG/file |

## Data source map tóm tắt (fallback)
- **DNSE WS** (worker pump Redis TTL 30s): dnse_foreign_flow, dnse_ws_snapshot, dnse_indices, dnse_market_status(tầng 1) — money_flow tự fallback → Vietstock
- **DNSE REST** (HMAC): ohlc_history, latest_trade, orderbook, foreign_rest, vn30f1m_live, working_dates — market_status fallback REST
- **vnstock VCI→KBS**: quote_history (tự fallback), quote_batch, listing, fundamentals, reference, company, trades, futures/forex/crypto/global ohlcv, retail gold/fx, MSN
- **Vietstock**: toàn bộ vs_* (mirror free + BCTC JWT + GICS + macro), news dc.vietstock.vn, forensic/valuation/overview trong compute
- **yfinance**: yf_*, assets_rotation, mega_flows, compare_assets
- **FRED / WorldBank / GDELT / Fireant / Groq / alternative.me**: fred_series, world_macro_country, geo_intel + event_stats + news fallback, sentiment, fear_greed
- **jina → Gamma**: world_prediction_odds
- **Exa/Parallel**: web_search (ẩn khi thiếu key)
- **PG → file JSON**: watchlist/alert store (mới)
- **Redis → memory**: cache snapshot, WS cache đọc, alert cross-state

## 17. corp.py — 9 tools (7 P7 + planned_targets + financial_detail, P14 revive)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| dividends_splits | Cash dividends and share issues/splits. Use for payout history. | symbol, region=vn (vn/world), limit=20 | vn: vnstock Company.events() (DIV cash, ISS bonus/private) + flags is_cash_dividend/is_share_issue; world: yfinance actions (lọc dividends>0 hoặc splits≠0/1) |
| holders | Shareholder and institutional holder tables. Use for ownership reads. | symbol, region=vn, kind=all (major/institutional/mutualfund/all, world only) | vn: vnstock shareholders; world: yfinance major/institutional/mutualfund holders |
| event_calendar_vn | Vietstock corporate-action calendar. Use for dividend/meeting/listing dates. | event=dividends (dividends/listings/meetings → typeID 1/2/5), symbol?, limit=20 | Vietstock /data/eventstypedata (không có earnings-dates); /Date(ms)/ parse theo giờ VN |
| block_trades | Matched vs negotiated put-through splits per day. Use for dark-pool-style reads. | symbol, from_date?/to_date? ISO (default 30d), limit=30 | Vietstock /data/gettradingresult (MT_* khớp lệnh vs PT_* thỏa thuận + pt_pct/totals) |
| analyst_consensus | Analyst ratings and price targets parsed from report titles. Use for street views. | symbol?, limit=30 | scrape Vietstock /bao-cao-phan-tich (rating MUA/BÁN... + target từ title; vs_reports_search API chết 404) |
| ipo_calendar_vn | HNX auction calendar plus announcement fallback. Use for upcoming supply. | — | scrape HNX lich-dau-gia (thường rỗng) + tin-cong-bo; verify=False (cert HNX) + warning tls-unverified |
| futures_basis | VN30F1M price minus VN30 spot. Use for premium/discount reads. | — (P12b: futures rớt về ohlc 15m khi trades/latest rỗng; spot chịu keys thô) | DNSE latest_trade → ohlc fallback − vnstock VN30 spot (KHÔNG OI) |
| planned_targets | Business-plan targets (CTKH: planned revenue/profit by year). Use as expectation anchor. | symbol, years=3 (P15 revive, session-gated) | Vietstock CTKH chain (norms → periods → values YearPeriods shape); dormant khi gate chặn |
| financial_detail | FULL detailed statements, every line item per period. Use for deep BCTC reads. | symbol, statement=KQKD/CDKT/LCTT/TM/BCTT, periods_n (P15 revive) | Vietstock /data/* chain object-array keys + permission filter; rows {norm_id, name, values} |

## 18. crypto.py — 2 tools (MỚI, P7)
| Tool | Descriptor | Params | Source |
|---|---|---|---|
| crypto_spot | Binance spot 24h tickers. Use for crypto price and volume reads. | symbols[] cap 10 (mọi spelling BTCUSDT/BTC-USDT/...) | Binance public /ticker/24hr (không key; array JSON cấm space) |
| crypto_derivs | Binance futures funding, OI and long/short ratios. Use for leverage reads. | symbols[] cap 5 | Binance fapi funding/OI/account-LSR/taker-ratio (forceOrders cần key → bỏ liquidations); per-symbol error không fail batch |

## Phụ lục P12 — Removed (commit ac99396, deploy 2026-10-01)
| Tool | Lý do xóa | Thay thế live |
|---|---|---|
| vs_reports_search | Route `CompanyReportSearch` 404 mọi params (cả code 8010 cũng fail) | `analyst_consensus`, `macro_reports` (revived qua scrape) |
| vs_stock_industry | `model: []` mọi IndustryID level 1–3, cả `_post` lẫn `_post_json` | `vs_industry_tree` + `vs_industry_heatmap` |
| vs_top_liquidity | Body rỗng mọi params, kể cả trong phiên | `market_movers` |

## Phụ lục P13 — Removed (worktree, chưa deploy)
| Tool | Lý do xóa | Thay thế live |
|---|---|---|
| vs_news_search | dc route chết (`No HTTP resource`); `news_symbol`/`news_market` cùng provider (dùng `sources='gdelt'`) | `news_market` + `sources='gdelt'` |
| dnse_foreign_rest | Endpoint từ chối mọi range from/to (400), WS flow là primary | `dnse_foreign_flow` (prod worker), `money_flow` |

## Phụ lục P15 — Removed + revive (worktree)
| Tool | Lý do | Thay thế live |
|---|---|---|
| vs_financial_values | Gói JWT giới hạn số kỳ (Package_Permission) — rows luôn rỗng | `vs_financeinfo` (mirror), `financial_detail` (P15 revive, số thật) |
| signals_trade_log | Local log trống, không ai ghi | `runs_list`/`run_get` |
| financial_detail | REVIVE P15: object-array form keys + permission filter → LIVE 138 số thật (FPT doanh thu/chi phí từng quý) | — |

## Phụ lục P5–P6 (params + descriptors, đã ghi chi tiết trong skills_check.md)
- **P5** (commit 7dcc77e): enrich params toàn bộ 126 tools (defaults backward-compat + 6 files contract tests `test_p5_*`, 65 tests). Ví dụ: quant thêm strategy/slippage_bps/benchmark, periods_per_year, lookback; scan thêm indicators/filters/max_pe/min_roe; brief thêm sources/scope/limit/date; intel thêm limit/status/tag/days/metrics/calc_ids.
- **P6** (commit 258d634): viết lại descriptors — enum/format/đơn vị cho ~45 tools + disambiguation 6 nhóm overlap (flows ×5, news ×3, disclosures ×3, calendars ×4, reports ×2, statements ×3). Xóa dev-note trong dnse_ohlc_history; schema rules cho alert_check/alert_create.
- **P8** (commit c8a9ddc): 6 prompts (ai_detect, risk_check, pre_earnings v2 thay v1, + refresh 3 cũ); `technicals.compute` thêm sma150/rs_vs_bench/pos_52w (signals_technical fetch VNINDEX best-effort).
- **P10** (commit 1027287, deploy 2026-10-01): required POST fields — nn/selftrading/gics/marketinfo sống lại live (reverse-engineer bundles finance.vietstock.vn); macro toDate=today để nhận message permission thật; liquidity giữ unavailable trung thực.
- **P11** (commit 4c91136, deploy 2026-10-01): breadth đếm Change hoa; reference qua KBS source; vàng BTMC https trực tiếp; financial_detail mới (chain free, chờ nâng tier). 258 tests passed.
- **P15** (worktree): macro Standard-pack LIVE (GDP 504 rows tới Q2/26, CPI 1839, XK 2941, XNK 3675) qua HAR-session replay + term-type đúng; planned_targets fix YearPeriods-shape (FPT KH 58,580/75,400 live); stock_forensic M-Score/Piotroski đầy đủ từ detail (FPT M=-2.06, HPG -2.24, VCB partial); polymarket sort vol24h + tag_slug (Fed 73.5% live); OHLCV interval 1D/1W/1M; snapshots PG 13 kinds + worker 17:15 + snapshot_history; DB riêng `opentrading_mcp`.
- **P9** (commit 17e1155, deploy 2026-10-01): honest-availability — news error-payload → unavailable; lookup không dấu; foreign errorCode → unavailable (endpoint từ chối mọi range); BCTC package-limit → unavailable + hint mirror; industry model-list + empty. Nguyên tắc: không bao giờ available-kèm-garbage.

## Docs vs code (skills_check.md Bảng 3) — chưa implement so docs
- Kalshi → Manifold fallback cho odds (chỉ jina→Gamma)
- PG read-only / 8010 fallback cho OHLCV, macro, BCTC (Fireant chain)
- RSS fallback news (chỉ có Vietstock→GDELT)
- OpenBB fallback global/macro
- jina/webgia SJC fallback vàng
- TTL cache: chỉ market_snapshot (60s) + worker loops dùng thật; odds TTL 2700s định nghĩa nhưng world_prediction_odds không dùng
