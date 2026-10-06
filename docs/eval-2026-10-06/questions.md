# Eval ăn khớp skills + tools — 06/10/2026 (nhánh MCP-server, Render bản mới)

Chạy headless: `bun /tmp/ot-eval/run.ts` (tự `mcp.start()` → đủ 139 remote + 16 local).
Model: nvidia `deepseek-ai/deepseek-v4.1-flash` (rẻ). Mỗi câu: verdict routing + tools + budget + provenance + trung thực.

## S. 26 skills — 1 câu/skill

| ID | Câu hỏi | Skill mong đợi | Tools chính kỳ vọng | Pass |
|---|---|---|---|---|
| S01 | Phân tích toàn diện FPT | phan-tich-chuyen-sau-1-ma | symbol_resolve → sub-skills → evidence_bundle + chart_render (Step 2b) | verdict 3 cột + có chart |
| S02 | Đọc BCTC FPT quý gần nhất, có dấu hiệu thao túng không | co-ban-chuyen-sau | financial_detail/statements + stock_forensic | M-Score + F-score + số |
| S03 | Địa chính trị tuần này có gì đáng lo cho thị trường | danh-gia-tinh-hinh-chinh-tri-toan-cau | event_stats/geo_intel | ≥4 mục có prob |
| S04 | Căng thẳng Trung Đông ảnh hưởng giá dầu và vàng thế nào | danh-gia-tinh-hinh-xung-dot | event_stats + compare_assets | 5 mục + số dầu/vàng |
| S05 | FPT sắp ra BCTC, đánh giá setup trước giờ G | danh-gia-truoc-bctc | company_events + valuation_run + scenario_simulate | grade + 6 leg |
| S06 | Kinh tế Mỹ hiện tại thế nào, lãi suất ra sao | danh-gia-vi-mo-quoc-te | fred_series + world_macro_country | 5 mục + curve |
| S07 | Đánh giá vĩ mô VN: CPI, GDP, lãi suất, tỷ giá | danh-gia-vi-mo-viet-nam | vs_indicator_data + sbv_rates | 6 mục + quý gần nhất |
| S08 | Phản biện giúp tôi luận điểm mua VCB lúc này | devil-advocate | (tự lập luận, ít tool) | ≥3 rủi ro cụ thể, không gọi tool tràn lan |
| S09 | VCB hiện tại đắt hay rẻ, vùng giá hợp lý bao nhiêu | dinh-gia-chuyen-sau | valuation_run + peer_compare | UPSIDE/DOWNSIDE % |
| S10 | Fed tháng tới cắt hay giữ lãi suất | du-doan-fed | world_prediction_odds | prob ≥2 kịch bản + lịch FOMC |
| S11 | Polymarket đang đặt cược gì về kinh tế Mỹ | du-doan-polymarket | world_prediction_odds | ≥5 event + liquidity/end-date |
| S12 | Giải thích cổ tức là gì | explain-term | (không tool data) | định nghĩa đúng, KHÔNG gọi tool data |
| S13 | Backtest chiến lược mua RSI dưới 30 trên HPG | kiem-chien-luoc-backtest | backtest_strategies (KHÔNG quant_backtest) | baseline + best/worst + caveat |
| S14 | Kiểm tra nhanh nguồn dữ liệu nào đang sống | kiem-tra-nguon-du-lieu | source_status + auth_status/doctor | bảng upstream + hướng fix |
| S15 | Phân tích kỹ thuật VCB, có breakout không | ky-thuat-chuyen-sau | signals_technical + market_candles_batch | RSI/MACD + khung 1D/1W |
| S16 | Thị trường crypto hôm nay sao, funding thế nào | nhip-dap-crypto | crypto_spot + crypto_derivs | 4 mục, funding rỗng không chết batch |
| S17 | Vàng SJC đang đắt hơn thế giới bao nhiêu | phan-tich-vang-ty-gia | vn_retail_gold + compare_assets | premium % + 2 driver |
| S18 | So sánh VCB BID CTG, ngân hàng nào tốt nhất | so-sanh-cung-nganh | compare_equities/peer_compare | bảng ≥3 mã + 1 dòng luận chọn |
| S19 | Tin đồn về VCB trên Fireant đang nói gì | phan-tich-sentiment | sentiment_score + fireant_thread | điểm + nhãn + ≥3 quotes |
| S20 | CTCK tuần này khuyên mua mã gì | tim-co-hoi-bao-cao-ctck | analyst_consensus (+PDF) | bảng ≥5 dòng có upside % |
| S21 | Tin mới nhất về Hòa Phát | tim-kiem-tin-tuc | news_symbol | ≥3 tin có provenance |
| S22 | Tin thế giới hôm nay có gì nóng | tin-tuc-nong-quoc-te | news_market/gdelt | ≥5 headline + reaction định lượng |
| S23 | Tin chứng khoán Việt Nam hôm nay | tin-tuc-nong-viet-nam | news_market + fireant | ≥5 headline + provenance |
| S24 | Vẽ biểu đồ nến VCB 30 phiên | ve-bieu-do-ky-thuat | vn_quote_history + chart_render | hình nến màu + verdict ≤3 câu |
| S25 | Biên độ giá sàn HOSE là bao nhiêu | vn-market-basics | (không tool data) | ±7%, KHÔNG gọi tool data |
| S26 | Bất ổn chính trị Thái Lan ảnh hưởng gì tới VN | bat-on-quoc-gia | geo_intel + event_stats | 4 mức verdict + evidence URL |

## W. 6 workflows (slash-command MCP prompt)

| ID | Câu hỏi | WF mong đợi | Tools chính kỳ vọng |
|---|---|---|---|
| W1 | /morning_briefing | morning_briefing | brief_build + market_overview + breadth_scan |
| W2 | /ticker_analysis VCB | ticker_analysis | skill điều phối S01, verdict đủ mục |
| W3 | /pre_earnings FPT | pre_earnings | 6 leg + grade |
| W4 | /sector_rotation | sector_rotation | sector_performance + money_flow |
| W5 | /risk_check VCB 100tr | risk_check | quant_risk + scenario_simulate |
| W6 | /ai_detect FPT | ai_detect | stock_forensic + signals_technical |

## F. Fallback — không skill nào khớp, ép đi tools trực tiếp (bổ sung chống gọi dư/gọi sai)

| ID | Câu hỏi | Kỳ vọng tool ĐÚNG | Cấm kỵ (gọi là fail) |
|---|---|---|---|
| F01 | Bây giờ là mấy giờ (giờ VN)? | current_time (local) | gọi bất kỳ tool remote nào |
| F02 | Tìm trên web xem giá cà phê robusta hôm nay bao nhiêu | web_search (local) | gọi remote thay vì local |
| F03 | Đọc giúp tôi nội dung trang https://example.com | web_fetch (local) | bịa nội dung khi fetch lỗi |
| F04 | Liệt kê các phiên chat đã lưu của tôi | session_list (local) | gọi runs_list (server-share) |
| F05 | Kiểm tra sức khỏe hệ thống | doctor_local trước (harness), doctor server sau nếu cần | chỉ gọi doctor mà bỏ doctor_local |
| F06 | Tạo watchlist cá nhân tên bank gồm VCB CTG | watchlist_local_create + watchlist_local_add | dùng watchlist_create remote |
| F07 | So sánh nhanh VCB HPG MSN cùng lúc cho đỡ chờ | spawn_subagent HOẶC batch trực tiếp (ghi nhận cách làm) | gọi lẻ từng mã nối tiếp 3 lần |
| F08 | Vẽ đường giá VCB vs HPG 3 tháng gần nhất | chart_compare (local) | fetch lại data đã có trong context |
| F09 | Nạp skill phan-tich-sentiment rồi phân tích VCB | load_skill rồi làm theo | bỏ qua load_skill, tự chế workflow |
| F10 | VCB có đáng mua không | phan-tich-chuyen-sau-1-ma (routing rộng) | trả lời chung chung không tool |
| F11 | Depth orderbook VN30F1M hiện tại thế nào | dnse_orderbook + chart_depth | retry liên tục khi ngoài giờ (rỗng là đúng) |

Tổng: 26 + 6 + 11 = **43 câu**.
