# Parity: vnstock v4 baseline (parity_v4_2026-11-08) vs current adapter, 2026-11-09

Values compared, not shapes. Candles: closes matched by date, tolerance 0.5 %. Ratios: P/E, P/B, ROE, EPS, BVPS on shared periods, tolerance 1 %.

| Probe | Status | Detail |
|---|---|---|
| quote_history_FPT | match | 60 shared days; worst 2026-08-12: v4 64.36 vs v6 64.36 (0.00 %) |
| quote_history_VCB | match | 60 shared days; worst 2026-08-12: v4 59.7 vs v6 59.7 (0.00 %) |
| quote_history_SSI | match | 60 shared days; worst 2026-08-12: v4 20.22 vs v6 20.22 (0.00 %) |
| quote_history_VNINDEX | match | 60 shared days; worst 2026-08-12: v4 1793.18 vs v6 1793.18 (0.00 %) |
| equity_ohlcv_FPT | match | 30 shared days; worst 2026-09-28: v4 63.7 vs v6 63.7 (0.00 %) |
| index_ohlcv_VNINDEX | match | 30 shared days; worst 2026-09-28: v4 1780.68 vs v6 1780.68 (0.00 %) |
| futures_ohlcv_VN30F1M | match | 30 shared days; worst 2026-10-15: v4 1847 vs v6 1839.8 (0.39 %) |
| crypto_ohlv_BTCUSDT | expected DIFF (unit VND -> USDT) | 30 shared days; v4/v6 median ratio 25,540 = USD/VND, so v4 was VND-denominated and gen 6 is USDT |
| forex_ohlcv_USDVND | match | 30 shared days; worst 2026-11-06: v4 25580 vs v6 25680 (0.39 %) |
| global_index_USA30 | match | 30 shared days; worst 2026-09-28: v4 51481.5 vs v6 51481.5 (0.00 %) |
| listing_symbols | match | 50/50 baseline symbols present; names equal for 1/50; e.g. ATG: v4 'CTCP ATG Planet' vs v6 'Công ty Cổ phần ATG Planet'; v6 lists 1516 symbols in total |
| reference_equity_HOSE | match | 50/50 baseline symbols present; exchange equal for 50/50; v6 lists 801 rows for the exchange |
| equity_trades_FPT | match | window 14:27:51-14:28:13 (+1 s clock skew): v4 22,200 vs v6 22,400 shares (0.9 %); by price 50.9: v4 17,900 vs v6 18,100, 51: v4 4,300 vs v6 4,300 |
| equity_ratios_FPT | match | 20 values on 4 periods; worst trailing_eps 2024: v4 5703.67 vs v6 5704 (0.01 %) |
| equity_ratios_VCB | match | 20 values on 4 periods; worst trailing_eps 2025: v4 4542.23 vs v6 4542 (0.01 %) |
| equity_ratios_SSI | match | 20 values on 4 periods; worst p_b 2024: v4 1.91 vs v6 1.9 (0.52 %) |
| equity_fundamentals_FPT | match | pe/roe/eps/bvps/period agree |
| msn_fx_gold | expected DIFF (spot -> futures) | USDVND v4 25580.0 vs v6 25580.0; gold: v4 MSN SPOT 4065.63 vs v6 COMEX FUTURES 4074.9 |
| equity_quote_batch | match | 4 symbols x 8 fields; all equal |
| cashflow_FPT_quarter | not_configured | ProviderUnavailable: vnstock cash flow statement: no source configured (only fhsc/fmp/tcbs serve it; fhsc and fmp were discontinued) |
| company_info_FPT | not_configured | ProviderUnavailable: vnstock company profile: no source configured (only fhsc/fmp/tcbs serve it; fhsc and fmp were discontinued) |
| insider_trading_FPT | not_configured | ProviderUnavailable: vnstock insider trading: no source configured (only fhsc/fmp/tcbs serve it; fhsc and fmp were discontinued) |
| corp_events_FPT | not_configured | ProviderUnavailable: vnstock corporate events: no source configured (only fhsc/fmp/tcbs serve it; fhsc and fmp were discontinued) |

Totals: expected DIFF (spot -> futures) 1, expected DIFF (unit VND -> USDT) 1, match 17, not_configured 4
