"""Search hints published as ``_meta["anthropic/searchHint"]`` on every tool.

Harnesses that defer tools behind a search (Claude Code ToolSearch, OpenTrading
tool_search) match these words in addition to the name and description. Each
hint adds Vietnamese terms without diacritics plus English synonyms the
description does not already use. Keep each under 80 characters.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

SEARCH_HINT_KEY = "anthropic/searchHint"
MAX_HINT_CHARS = 80

HINTS: dict[str, str] = {
    # market
    "market_snapshot": "bang gia VN30 gia hien tai realtime | price board quotes now",
    "source_status": "tinh trang nguon du lieu loi cham | data source health stale",
    "market_candles_batch": "nen nhieu ma cung luc lich su gia | multi symbol candles prices",
    "symbol_lookup": "tim ma co phieu theo ten cong ty | ticker search company name",
    "symbol_resolve": "ma tai san vang usd bitcoin la gi | resolve any asset code",
    "market_movers": "top tang giam manh khoi luong | gainers losers active",
    "breadth_scan": "do rong thi truong ma tang giam tran san | breadth advance decline",
    "market_overview": "tong quan thi truong hom nay | market summary today pulse",
    "dnse_market_status": "phien giao dich mo dong cua | session open closed status",
    "distribution_count": "dem phien phan phoi oneil ftd | distribution days count follow through",
    # vn
    "vn_quote_history": "lich su gia nen ngay tuan thang co phieu | price history daily candles",
    "vn_equity_quote_batch": "bang gia nhieu ma gia khop | quotes many tickers board",
    "vn_listing": "danh sach ma niem yet toan thi truong | all listed tickers universe",
    "vn_fundamentals": "chi so tai chinh bctc nhanh | ratios statements quick valuation",
    "vn_retail_gold": "gia vang SJC nhan mua ban | gold price retail",
    "vn_retail_fx": "ty gia USD Vietcombank mua ban | exchange rate dollar",
    # vs
    "vs_auth_status": "dang nhap Vietstock token het han | login token expiry",
    "vs_financeinfo": "bao cao tai chinh quy nam | financial statements quarterly annual",
    "vs_market_price": "bang gia Vietstock gia khop | quotes board secondary",
    "vs_market_index": "chi so VNINDEX HNX tang truong | index performance ytd",
    "vs_nn_flow": "khoi ngoai mua ban rong theo ngay | foreign net buy sell daily",
    "vs_categories": "danh muc chi so vi mo GDP CPI | macro indicator list",
    "vs_indicator_data": "du lieu vi mo GDP CPI lam phat ty gia | macro data inflation",
    "vs_trading_info": "gia tran san room ngoai EPS PE | ceiling floor foreign room",
    "vs_financial_terms": "ky bao cao quy nam | report periods",
    "vs_financial_norms": "chi tieu bctc ma so | statement line items ids",
    "vs_company_info": "thong tin doanh nghiep gioi thieu | company profile about",
    "vs_overview_trading": "giao dich theo ngay khoi ngoai tu doanh | daily trading deals",
    "vs_documents": "cong bo thong tin tai lieu | disclosures filings documents",
    "vs_industry_tree": "cay nganh phan loai GICS | industry classification",
    "vs_industry_heatmap": "ban do nhiet nganh trong phien | sector heatmap intraday",
    "vs_selftrading": "tu doanh cong ty chung khoan mua ban | proprietary trading flow",
    "vs_gics_index": "chi so nganh dong tien ngoai | sector index foreign flow",
    "vs_currency": "bang ty gia tham chieu | fx rates table",
    "vs_market_info": "thong tin san HOSE HNX thoa thuan | exchange board putthrough",
    "vs_xnk_detail": "xuat nhap khau theo quoc gia | trade exports imports",
    # vn_ext
    "vn_index_ohlcv": "lich su chi so VNINDEX VN30 nen | index history candles",
    "vn_equity_ohlcv": "lich su gia co phieu nen phut | stock bars intraday",
    "vn_futures_ohlcv": "phai sinh hop dong tuong lai nen | derivatives futures bars",
    "vn_forex_ohlcv": "lich su ty gia ngoai te | currency history",
    "vn_crypto_ohlv": "tien so bitcoin lich su gia | crypto price history",
    "vn_crypto_ohlcv": "tien so bitcoin nen lich su gia | crypto candles history",
    "vn_global_index": "chi so the gioi INX COMP USA30 Dow | world index history symbols",
    "vn_reference": "danh sach ma theo san nhom nganh | tickers by exchange group",
    "vn_company": "ho so cong ty co dong ban lanh dao | profile shareholders officers",
    "vn_msn_fx_gold": "ty gia USDVND vang the gioi | usd vnd gold xau",
    "vn_trades": "khop lenh tung giao dich tick | tick trades matched",
    # yf
    "yf_global_indices": "chi so the gioi My chau A qua dem | world indices overnight",
    "yf_commodities": "hang hoa dau vang kim loai | commodities oil metals",
    "yf_yield_curve": "loi suat trai phieu My dao nguoc | treasury yields inversion",
    # yf_world
    "yf_world_indices": "24 chi so toan cau | global indices breadth",
    "yf_oracle_markets": "tai san lien thi truong 30 ngay | cross asset markets stats",
    "yf_regime_assets": "rui ro risk on off tai san dan dat | regime drivers",
    "yf_mega_flows": "co phieu von hoa lon My dong tien | megacap leaders flows",
    "yf_alloc_history": "lich su dai han vang dau BTC | long history allocation",
    "yf_market_pins": "bien dong 5 ngay chi so lon | five day moves majors",
    # dnse
    "dnse_ohlc_history": "lich su nen phai sinh VN30F1M chi so | futures index bars",
    "dnse_latest_trade": "gia khop moi nhat realtime | last trade price",
    "dnse_foreign_flow": "khoi ngoai vn30f1m futures mua ban rong | foreign net flow futures scope",
    "dnse_ws_snapshot": "du lieu thoi gian thuc tho kiem tra | realtime raw debug",
    "dnse_orderbook": "so lenh du mua du ban | order book depth bid ask",
    "dnse_indices": "chi so trong phien VNINDEX VN30 | live index levels",
    "dnse_vn30f1m_live": "phai sinh VN30F1M trong phien 15 phut | futures intraday",
    "dnse_working_dates": "lich ngay giao dich ngay nghi | trading days holidays",
    "exchange_calendar": "gio giao dich ATO ATC thanh toan T+2 | trading hours rules",
    # crypto
    "crypto_spot": "tien so gia bitcoin binance | crypto spot prices",
    "crypto_derivs": "funding open interest don bay tien so | crypto futures leverage",
    # scan
    "stock_screener": "loc co phieu theo PE ROE tieu chi | stock screen filter",
    "signals_screener_columns": "cot tieu chi bo loc | screener fields list",
    "signals_technical": "phan tich ky thuat RSI MACD MA | technical indicators",
    "sector_performance": "hieu suat nganh xoay vong | sector rotation performance",
    "money_flow": "dong tien khoi ngoai tong hop | foreign flow composite smart money",
    "alert_check": "kiem tra canh bao gia RSI | check price alerts",
    # compute
    "stock_forensic": "gian lan bctc chat luong loi nhuan | accounting fraud quality score",
    "valuation_run": "dinh gia gia tri hop ly DCF | fair value intrinsic",
    "fred_series": "vi mo My lai suat FED | us macro rates",
    "world_macro_country": "vi mo quoc gia GDP no cong | country macro worldbank",
    "world_fear_greed": "tam ly so hai tham lam | fear greed sentiment",
    "sentiment_score": "tam ly dam dong mang xa hoi | crowd social sentiment",
    "insider_trading": "giao dich noi bo lanh dao | insider deals",
    "stock_overview": "tong quan co phieu PE PB hien tai | stock summary current multiples",
    "company_events": "su kien doanh nghiep co tuc hop DHCD | corporate events",
    "financial_statements": "bao cao tai chinh can doi ket qua kinh doanh | income balance cash",
    "financial_ratios": "chi so tai chinh theo ky ROE PE cuoi ky | ratios by period",
    "peer_compare": "so sanh cung nganh chi so cuoi ky | peers comparison",
    "signals_scan": "co phieu breakout dot pha | momentum breakout scan",
    "pattern_match": "mau hinh tuong tu lich su | similar pattern analog",
    "snapshot_history": "du lieu da luu theo ngay | stored daily snapshots",
    "event_stats": "thong ke su kien tin tuc | news event counts",
    "compare_assets": "so sanh tai san gia | compare assets prices",
    "runs_list": "lich su phan tich da chay | saved runs",
    "run_get": "xem lai ket qua phan tich | saved run detail",
    "doctor": "kiem tra cau hinh may chu | server self check config",
    # corp
    "dividends_splits": "co tuc chia tach co phieu | dividend history split",
    "holders": "co dong lon to chuc so huu | shareholders ownership",
    "event_calendar_vn": "lich co tuc DHCD niem yet | dividend meeting calendar",
    "block_trades": "giao dich thoa thuan lo lon | block trades putthrough",
    "analyst_consensus": "khuyen nghi gia muc tieu cong ty chung khoan | analyst target price",
    "ipo_calendar_vn": "lich IPO dau gia phat hanh | ipo auctions",
    "futures_basis": "chenh lech phai sinh co so | futures basis premium",
    "planned_targets": "ke hoach kinh doanh doanh thu loi nhuan | business plan targets",
    "financial_detail": "bctc chi tiet tung chi tieu | detailed statements line items",
    # watchlist
    "watchlist_create": "tao danh muc theo doi | new watchlist",
    "watchlist_list": "danh sach danh muc theo doi | list watchlists",
    "watchlist_get": "xem danh muc theo doi | show watchlist",
    "watchlist_add": "them ma vao danh muc | add to watchlist",
    "watchlist_remove": "bo ma khoi danh muc | remove from watchlist",
    "watchlist_delete": "xoa danh muc theo doi | delete watchlist",
    "watchlist_update": "doi ten danh muc | rename watchlist",
    "alert_create": "tao canh bao gia | new price alert",
    "alert_list": "danh sach canh bao | list alerts",
    "alert_delete": "xoa canh bao | delete alert",
    "alert_pause": "tam dung canh bao | pause alert",
    "alert_resume": "bat lai canh bao | resume alert",
    # quant
    "quant_backtest": "kiem dinh chien luoc mua giu | backtest buy hold",
    "quant_risk": "rui ro sharpe sut giam toi da | risk metrics drawdown",
    "quant_factors": "nhan to dong luong bien dong | momentum volatility factors",
    "scenario_simulate": "kich ban gia giam lai lo | shock scenario pnl",
    "correlation_matrix": "tuong quan giua cac ma | correlation diversification",
    "seasonality": "tinh mua vu theo thang | seasonal monthly returns",
    "event_study": "phan ung gia quanh su kien tin | abnormal return event window",
    "backtest_strategies": "kiem dinh chien luoc giao cat MA | strategy backtest sma",
    "portfolio_optimize": "toi uu danh muc phan bo ty trong | portfolio weights allocation",
    "param_sweep": "toi uu tham so chien luoc | parameter grid search",
    # brief
    "brief_build": "ban tin sang tom tat thi truong | morning brief",
    "news_market": "tin tuc thi truong chung khoan | market news",
    "news_symbol": "tin tuc ve ma co phieu tin don | stock news rumors",
    "fireant_thread": "binh luan bai viet fireant nha dau tu | social post replies",
    "economic_calendar": "danh muc chi so vi mo | macro series catalogue",
    "sbv_rates": "lai suat ngan hang nha nuoc lien ngan hang | central bank rates",
    "macro_events_vn": "lich cong bo so lieu vi mo CPI | macro release dates",
    "corporate_calendar": "cong bo thong tin doanh nghiep | company disclosures feed",
    # intel
    "world_prediction_odds": "xac suat thi truong du doan Fed | prediction market odds",
    "polymarket_event": "chi tiet su kien du doan | prediction event detail",
    "geo_intel": "dia chinh tri chien tranh xung dot | geopolitics conflict",
    "assets_rotation": "xoay vong tai san risk on off | asset rotation regime",
    "compare_equities": "so sanh co phieu dong luong | compare stocks momentum",
    "evidence_bundle": "chot ket luan bang chung | evidence verdict",
    "oracle_meta": "tong hop trang thai nguon | aggregator status",
    # cycle (PG tables)
    "cycle_stats_check": "do tuoi bang thong ke chu ky nhom nganh | sector cycle tables freshness",
    "cycle_seasonality": "mua vu nhom nganh theo thang thong ke chu ky | sector monthly seasonal",
    "cycle_chains": "luan chuyen nganh nhom nay manh nhom kia tang theo | sector rotation lead lag",
    "cycle_turning": "dinh day chi so theo nam | yearly index peaks troughs",
    "cycle_tet": "hieu ung tet nguyen dan truoc sau | lunar new year effect",
    "cycle_yearly": "lai lo nhom nganh theo nam xep hang thong ke chu ky | sector yearly returns",
    "cycle_trough_events": "nhom nganh dan dat chay truoc sau day thi truong | sector leads",
    "cycle_stats_refresh": "cap nhat du lieu bang chu ky | refresh cycle cache",
    "cycle_stats_finalize": "tinh lai bang chu ky | recompute cycle tables",
    "vn_asset_check": "do tuoi bang chu ky tai san viet nam | vn asset cycle tables freshness",
    "vn_asset_seasonality": "chu ky mua vu tai san viet nam vang usd btc | vn assets monthly",
    "vn_asset_anchors": "lai tiet kiem trai phieu chenh sjc | deposit yields spreads",
    "vn_asset_chains": "tai san dan dat btc dau brent | cross asset leads",
    "vn_asset_refresh": "cap nhat tai san viet nam | refresh vn assets",
    "g_asset_check": "do tuoi bang chu ky tai san toan cau | global asset cycle freshness",
    "g_asset_seasonality": "mua vu tai san toan cau etf | global etf monthly",
    "g_asset_phase": "pha chu ky kinh te toan cau suy thoai lop tai san | nber phase returns",
    "g_asset_corr": "tuong quan co phieu trai phieu | stock bond correlation",
    "g_asset_outlook": "nhan dinh quy lon phan bo | bank fund outlook",
    "g_asset_refresh": "cap nhat tai san toan cau | refresh global assets",
    # web
    "web_fetch": "doc trang web lien ket | read url page",
    "web_search": "tim kiem internet tin moi | internet search",
    # vn_predictions (sub-backend: daily distribution forecasts, Neon shared PG)
    "vn_predictions_check": "do tuoi bang du bao ngay | daily predictions freshness",
    "vn_predictions_latest": "du bao 12 thang moi nhat | latest 12m distribution forecasts",
    "vn_predictions_sparkline": "bien dong du bao theo ngay | daily forecast sparkline",
    "vn_screener_check": "do tuoi bang tin hieu screener | screener signals freshness",
    "vn_screener_top": "top ma co xac suat cham +20% trong 20 phien | top touch probability stocks",
    # vn_reversal (sub-backend Stage D: DAY/DINH reversal signals, Neon shared PG)
    "vn_reversal_check": "do tuoi bang tin hieu mua ban | buy sell signals freshness",
    "vn_reversal_signals": "tin hieu mua ban hom nay | today buy sell reversal signals",
    "vn_reversal_dashboard": "dashboard nganh dem day dinh theo ro | sector bottom top counts",
    "vn_reversal_history": "lich su xac suat day dinh cua ma | per symbol reversal history",
    "vn_screener_symbol": "lich su tin hieu cham cua mot ma | per-symbol touch signal history",
    "vnindex_scenarios_check": "do tuoi bang kich ban VNINDEX | vnindex scenarios freshness",
    "vnindex_scenarios_latest": "kich ban VNINDEX | up mid down scenarios",
    "vnindex_scenarios_history": "chuoi kich ban VNINDEX | vnindex scenario sparkline",
    "vnindex_risk_heads": "canh bao rui roi cham xuong | vnindex downside risk heads",
}


def search_meta(tool: str) -> dict[str, Any]:
    """``_meta`` for one tool: its search hint, or nothing."""
    hint = HINTS.get(tool)
    return {SEARCH_HINT_KEY: hint} if hint else {}


def apply_search_hints(server: FastMCP) -> None:
    """Publish each registered tool's hint in its ``_meta`` (kept with any meta it has)."""
    for tool in server._tool_manager.list_tools():
        hint = search_meta(tool.name)
        if hint:
            tool.meta = {**(tool.meta or {}), **hint}
