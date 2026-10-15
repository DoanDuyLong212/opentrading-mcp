| Tool | Lần 1 (không cache) | Lần 2 (Redis hit) |
|---|---|---|
| alert_check | 0.0s | 0.0s |
| alert_list | 0.0s | 0.0s |
| analyst_consensus | 0.78s | 0.05s |
| assets_rotation | 0.9s | 0.07s |
| backtest_strategies | 2.46s | 0.05s |
| block_trades | 3.43s | 0.05s |
| breadth_scan | 0.16s | 0.05s |
| company_events | 0.29s | 0.19s |
| compare_assets | 1.27s | 0.05s |
| compare_equities | 13.02s | 0.05s |
| corporate_calendar | 0.26s | 0.08s |
| correlation_matrix | 2.55s | 0.05s |
| crypto_derivs | 7.26s | 0.08s |
| crypto_spot | 1.03s | 0.07s |
| cycle_chains | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| cycle_seasonality | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| cycle_stats_check | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| cycle_tet | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| cycle_trough_events | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| cycle_turning | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| cycle_yearly | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| distribution_count | 0.91s | 0.06s |
| dividends_splits | 0.31s | 0.06s |
| dnse_foreign_flow | 0.18s | 0.33s |
| dnse_indices | 0.23s | 0.05s |
| dnse_latest_trade | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) |
| dnse_market_status | 0.26s | 0.05s |
| dnse_ohlc_history | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) |
| dnse_orderbook | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) |
| dnse_vn30f1m_live | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) |
| dnse_working_dates | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) |
| economic_calendar | 0.27s | 0.05s |
| event_calendar_vn | 8.42s | 0.14s |
| event_stats | FAIL (TimeoutError: ) | FAIL (unavailable: gdelt throttled, retry later) |
| evidence_bundle | 0.0s | 0.0s |
| exchange_calendar | 0.1s | 0.09s |
| financial_detail | 0.65s | 0.05s |
| financial_ratios | 0.35s | 0.05s |
| financial_statements | 1.25s | 0.15s |
| fireant_thread | 0.47s | 0.05s |
| fred_series | FAIL (unavailable: FRED_API_KEY is not set) | FAIL (unavailable: FRED_API_KEY is not set) |
| futures_basis | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) | FAIL (unavailable: DNSE_API_KEY/DNSE_SECRET are not set) |
| g_asset_check | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| g_asset_corr | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| g_asset_outlook | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| g_asset_phase | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| g_asset_seasonality | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| geo_intel | FAIL (unavailable: gdelt throttled, retry later (retry-after-gdelt)) | FAIL (unavailable: gdelt throttled, retry later (retry-after-gdelt)) |
| holders | 1.03s | 0.07s |
| insider_trading | 5.25s | 0.05s |
| ipo_calendar_vn | 0.57s | 0.05s |
| macro_events_vn | 2.89s | 0.05s |
| market_candles_batch | 0.5s | 0.09s |
| market_movers | 3.04s | 0.11s |
| market_overview | 2.9s | 0.07s |
| market_snapshot | 14.18s | 0.88s |
| money_flow | 0.15s | 0.06s |
| news_market | 0.2s | 0.09s |
| news_symbol | 0.37s | 1.21s |
| peer_compare | 5.73s | 0.05s |
| quant_factors | 3.43s | 0.08s |
| quant_risk | 0.07s | 0.06s |
| run_get | 0.0s | 0.0s |
| runs_list | 0.0s | 0.0s |
| sbv_rates | 11.31s | 0.11s |
| seasonality | 2.13s | 0.08s |
| sector_performance | 6.06s | 0.15s |
| sentiment_score | 3.25s | 0.08s |
| signals_screener_columns | 0.11s | 0.05s |
| signals_technical | 6.18s | 0.08s |
| stock_forensic | 8.46s | 0.05s |
| stock_overview | 3.45s | 0.08s |
| symbol_lookup | 5.44s | 0.05s |
| symbol_resolve | 0.21s | 0.05s |
| vn_asset_anchors | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| vn_asset_chains | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| vn_asset_check | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| vn_asset_seasonality | FAIL (unavailable: DATABASE_URL not configured) | FAIL (unavailable: DATABASE_URL not configured) |
| vn_company | 0.27s | 0.06s |
| vn_crypto_ohlcv | 1.46s | 0.07s |
| vn_crypto_ohlv | 0.06s | 0.05s |
| vn_equity_ohlcv | 1.08s | 0.08s |
| vn_equity_quote_batch | 5.45s | 0.1s |
| vn_forex_ohlcv | 0.96s | 0.05s |
| vn_fundamentals | 2.25s | 0.09s |
| vn_futures_ohlcv | 6.25s | 0.05s |
| vn_global_index | 0.68s | 0.06s |
| vn_index_ohlcv | 1.33s | 0.05s |
| vn_listing | 0.22s | 0.11s |
| vn_msn_fx_gold | 1.11s | 0.05s |
| vn_quote_history | 0.99s | 0.11s |
| vn_reference | 0.55s | 0.31s |
| vn_retail_fx | 5.6s | 0.05s |
| vn_retail_gold | 1.25s | 0.05s |
| vn_trades | 0.4s | 0.05s |
| vs_auth_status | 0.0s | 0.0s |
| vs_categories | 0.46s | 0.18s |
| vs_company_info | 0.19s | 0.05s |
| vs_currency | 0.14s | 0.07s |
| vs_documents | 0.23s | 0.08s |
| vs_financeinfo | 0.78s | 0.16s |
| vs_financial_norms | 0.49s | 0.11s |
| vs_financial_terms | 0.29s | 0.07s |
| vs_gics_index | 0.14s | 0.07s |
| vs_indicator_data | FAIL (unavailable: pass indicator (GDP/CPI/XK) or category_id (see vs_catego) | FAIL (unavailable: pass indicator (GDP/CPI/XK) or category_id (see vs_catego) |
| vs_industry_heatmap | 3.71s | 0.57s |
| vs_industry_tree | 0.4s | 0.13s |
| vs_market_index | 0.16s | 0.06s |
| vs_market_info | 0.16s | 0.07s |
| vs_market_price | 0.14s | 0.05s |
| vs_nn_flow | 0.15s | 0.06s |
| vs_overview_trading | 0.15s | 0.07s |
| vs_selftrading | 0.14s | 0.07s |
| vs_trading_info | 0.16s | 0.05s |
| vs_xnk_detail | 0.4s | 0.15s |
| watchlist_get | 0.0s | 0.0s |
| watchlist_list | 0.0s | 0.0s |
| world_fear_greed | 6.11s | 0.1s |
| world_prediction_odds | 22.96s | 0.06s |
| yf_alloc_history | 0.44s | 0.05s |
| yf_commodities | 0.46s | ~0.05s (loop 60s, đo riêng) |
| yf_global_indices | 0.6s | ~0.05s (loop 60s, đo riêng) |
| yf_market_pins | 1.51s | 0.05s |
| yf_mega_flows | 0.92s | 0.05s |
| yf_oracle_markets | 1.86s | 0.1s |
| yf_regime_assets | 0.52s | 0.05s |
| yf_world_indices | 2.2s | 0.05s |
| yf_yield_curve | FAIL (unavailable: yfinance + FRED both failed: FRED_API_KEY is not set) | FAIL (unavailable: yfinance + FRED both failed: FRED_API_KEY is not set) |
