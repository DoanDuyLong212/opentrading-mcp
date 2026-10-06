# Verify đợt 1 — round2 (06/10/2026 chiều)

Chạy lại 12 câu sau fix, transcripts: `runs/round2/<ID>.json`.
Registry: **156 tools** (switch_preset đã xóa). Server: Render bản mới (descriptors + coerce).

## Kết quả

| ID | Round 1 | Round 2 | Fix verified |
|---|---|---|---|
| F08 | PARTIAL (switch_preset) | 6 tools đúng, 0 preset, text 1760 ch | ✅ #2 |
| F09 | FAIL (preset-loop trắng) | load_skill → news_symbol + sentiment_score, text 2262 ch | ✅ #2 |
| S12 | PASS | PASS (85s) | ✅ no-regression |
| S07 | PARTIAL (validation ×3) | 0 validation-fail (coerce chạy) | ✅ #5 |
| F11 | PARTIAL (validation + rỗng) | dnse_orderbook + vn_trades + vn30f1m_live, 0 fail, text 1377 ch | ✅ #5 |
| S09 | PARTIAL (4 tools bịa) | 0 hallucination, toàn tools thật | ✅ #3 |
| S13 | PARTIAL (vn_crypto_ohlcv sai) | backtest_strategies ×6 + seasonality, không quant_backtest/crypto | ✅ #6 |
| S16 | FAIL (crypto VND ×6) | crypto_spot + crypto_derivs trước, ohlcv chỉ cho leg VND | ✅ #6 |
| S24 | PASS- (thử sai nguồn) | vn_quote_history + chart_render, không detour | ✅ #6 |
| W1 | PASS- (preset ×2) | đủ 6 tools prompt, 0 preset | ✅ #2 |
| W4 | PASS | tool spread tốt + gọi cả tools mồ côi (dnse_foreign_flow, vs_nn_flow, vs_industry_heatmap) | ✅ + coverage |
| W5 | FAIL | spread tốt hơn, 0 preset/hallucination — nhưng vẫn CHƯA gọi quant_risk (leg 1 prompt) | ⚠️ cải thiện, chưa đạt |

## Metric

- `switch_preset` calls: 8/43 → **0/12**
- Hallucinated tools: 7 → **0**
- Validation fails: 4+ → **0** (còn 2 transient HTTP 500 Render, tự hồi)
- Timeouts 300s: vẫn còn (S07/S09/S13/W1/W4/W5) — sang đợt 2 (#1)
- W5/quant_risk: còn miss — đợt 2 hoặc siết risk_check prompt
