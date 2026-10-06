# Bộ câu hỏi test skill `ky-thuat-chuyen-sau` (S15 — skill phức tạp, 06-10-2026)

Chạy headless: `bun src/core/chat.ts "<câu>"` hoặc qua eval runner. Kỳ vọng chung:
`signals_technical` trụ cột (≤3 calls), khung đúng (1D/1W/1M), provenance + as_of,
verdict có hướng dẫn hành động (kịch bản tăng/giảm), không vượt budget 8.

| ID | Câu hỏi | Kỳ vọng chính |
|---|---|---|
| T01 | "Phân tích kỹ thuật VCB khung ngày" | signals_technical 1D; RSI/MACD/ADX + verdict tăng/giảm |
| T02 | "HPG có breakout không" | breakout check: giá vs kháng cự 20d + volume; không breakout thì nói rõ |
| T03 | "FPT đang higher-high hay lower-low" | cấu trúc sóng HH/LL từ swing highs/lows; khung 1D |
| T04 | "VCB khung tuần sao rồi" | signals_technical interval=1W; trend tuần |
| T05 | "Đọc băng giá HPG giúp tôi" | đọc băng: hỗ trợ/kháng cự + zone giá; không cần tool data thêm |
| T06 | "FPT Ichimoku thế nào" | Ichimoku: Tenkan/Kijun/Cloud + giá vs cloud |
| T07 | "Sóng Elliott VCB đang sóng mấy" | Elliott swing count (proxy heuristic); nói rõ heuristic |
| T08 | "VCB 1D vs 1W khung nào tốt hơn cho mua" | so 2 khung: 2 calls signals_technical; verdict đồng thuận/phân kỳ |
| T09 | "ADX VCB bao nhiêu, trend mạnh không" | 1 call; ADX + DI; trend mạnh/yếu theo ngưỡng 20-25 |
| T10 | "HPG MACD crossover chưa" | MACD line/signal + histogram; crossover mới nhất |
| T11 | "VCB RSI bao nhiêu, có oversold không" | 1 call; RSI 30/70 ngưỡng; oversold/overbought đúng nghĩa |
| T12 | "Phân tích kỹ thuật MSN + vẽ nến" | signals_technical + chart_render local (Step 2b pipeline) |

## Tiêu chí pass
- Routing: load ky-thuat-chuyen-sau ngay, không dispatch sang phan-tich-chuyen-sau-1-ma.
- Tools: signals_technical là trụ cột; chart/candle khi user hỏi vẽ (chart_render local).
- Verdict: có hướng dẫn hành động (kịch bản tăng/giảm + điều kiện), không chỉ liệt kê chỉ số.
- Provenance: mỗi số kèm nguồn + as_of; không bịa số khi tool unavailable.
