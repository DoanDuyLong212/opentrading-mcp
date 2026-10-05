# SKILLS.md — Gộp toàn bộ skills của harness OpenTrading (để kiểm duyệt)

> Nguồn sự thật: repo **OpenTrading** `skills/<slug>/SKILL.md` (26 skills: 21 theo
> thiết kế `docs/skills-design-for-harness.md` rev.3 + 3 skill nền: devil-advocate,
> explain-term, vn-market-basics + 1 skill vẽ biểu đồ TUI: ve-bieu-do-ky-thuat
> + 1 skill kiểm tra nguồn: kiem-tra-nguon-du-lieu).
> File gộp này chỉ để ĐỌC/DUYỆT — chỉnh sửa
> phải làm trên từng file SKILL.md trong OpenTrading rồi gộp lại.
>
> **rev.3 (Phase A)**: đã XÓA 6 skills theo yêu cầu — `danh-gia-tinh-hinh-thi-truong`,
> `kiem-tra-rui-ro-vi-the`, `luan-chuyen-nganh-viet-nam`, `luan-chuyen-tai-san-toan-cau`,
> `san-loc-co-phieu`, `theo-doi-va-bao-thuc`. Cross-refs trong skills còn lại đã sửa.
>
> **Bản P17 (02-10-2026, MCP-server `89db45b`)** — skills chịu ảnh hưởng, đã cập nhật:
> `ky-thuat-chuyen-sau` (1W/1M + Ichimoku/swing/Elliott/Wyckoff),
> `kiem-chien-luoc-backtest` (rsi_meanrev + months/quarters + condition_symbol + `event_study`),
> `tim-co-hoi-bao-cao-ctck` (macro filter + đọc PDF),
> `tim-kiem-tin-tuc` + `phan-tich-sentiment` (`fireant_thread`, parser postID),
> `danh-gia-vi-mo-viet-nam` (macro filter), `phan-tich-chuyen-sau-1-ma` (`symbol_resolve`).
>
> **Bản rewrite 05-10-2026 (phương án A)** — viết lại toàn bộ 26 skills theo
> `SKILL-TEMPLATE.md` (chuẩn opencode `name+description`, body `Khi nào dùng / Workflow /
> Verdict / Chống tràn lan / Lỗi thường gặp / Bằng chứng live / Nghiệm thu`). Giữ nguyên
> full frontmatter harness (`activation/requires_tools/tool_budget/triggers/version/when_to_use`),
> bump patch `1.0.0→1.0.1`, `1.1.0→1.1.1`. `description` front-load keywords +
> `Dùng khi... Không dùng khi...` để opencode native (chỉ thấy name+description) routing đúng.
> Bằng chứng live 02-10-2026 giữ nguyên, không bịa số mới.

## Đặc tả frontmatter chung

| Field | Bắt buộc | Ý nghĩa |
|---|---|---|
| `name` | ✔ | slug kebab-case không dấu, ≤64 ký tự, trùng tên folder |
| `description` | ✔ | front-load keywords user hay nói; có "Dùng khi…/Không dùng khi…" + tên skill loại trừ (opencode chỉ thấy field này để routing) |
| `when_to_use` | ✔ (harness) | câu hỏi mẫu + loại trừ chi tiết, mirror vào body `Khi nào dùng` |
| `activation` | ✔ | `auto` (model nạp khi khớp) / `manual` (chỉ /skill <tên>, ví dụ kiem-tra-nguon-du-lieu) |
| `requires_tools` | khuyến khích | skill chỉ hiện trong catalog khi MỌI tool này có mặt (gate theo preset) |
| `tool_budget` | với skill thiết kế | số lần gọi tool tối đa mỗi run; harness chặn cứng 20/lượt; mirror vào `Chống tràn lan` |
| `triggers.keywords` | khuyến khích | pre-routing: khớp keyword → gợi ý skill ở reminder |
| `version` | ✔ | semver, rewrite 05-10-2026 bump patch |

## Bảng tổng quan

| # | Skill | Kích hoạt | Budget | Version | Tools yêu cầu (đã bỏ prefix mcp__) |
|---|---|---|---|---|---|
| 1 | `bat-on-quoc-gia` | auto | 6 | 1.0.1 | geo_intel |
| 2 | `co-ban-chuyen-sau` | auto | 9 | 1.0.1 | financial_detail |
| 3 | `danh-gia-tinh-hinh-chinh-tri-toan-cau` | auto | 8 | 1.0.1 | — |
| 4 | `danh-gia-tinh-hinh-xung-dot` | auto | 9 | 1.0.1 | event_stats |
| 5 | `danh-gia-truoc-bctc` | auto | 10 | 1.0.1 | company_events |
| 6 | `danh-gia-vi-mo-quoc-te` | auto | 10 | 1.0.1 | fred_series |
| 7 | `danh-gia-vi-mo-viet-nam` | auto | 12 | 1.1.1 | vs_indicator_data |
| 8 | `devil-advocate` | auto | — | 1.1.1 | — |
| 9 | `dinh-gia-chuyen-sau` | auto | 7 | 1.0.1 | valuation_run |
| 10 | `du-doan-fed` | auto | 8 | 1.0.1 | world_prediction_odds |
| 11 | `du-doan-polymarket` | auto | 6 | 1.0.1 | world_prediction_odds |
| 12 | `explain-term` | auto | — | 1.1.1 | — |
| 13 | `kiem-chien-luoc-backtest` | auto | 12 | 1.1.1 | quant_backtest |
| 14 | `kiem-tra-nguon-du-lieu` | manual | 12 | 1.0.1 | doctor |
| 15 | `ky-thuat-chuyen-sau` | auto | 8 | 1.1.1 | signals_technical |
| 16 | `nhip-dap-crypto` | auto | 6 | 1.1.1 | crypto_spot |
| 17 | `phan-tich-chuyen-sau-1-ma` | auto | 8 | 1.1.1 | stock_overview |
| 18 | `phan-tich-sentiment` | auto | 6 | 1.0.1 | sentiment_score |
| 19 | `phan-tich-vang-ty-gia` | auto | 10 | 1.1.1 | vn_retail_gold |
| 20 | `so-sanh-cung-nganh` | auto | 8 | 1.1.1 | compare_equities |
| 21 | `tim-co-hoi-bao-cao-ctck` | auto | 8 | 1.1.1 | analyst_consensus |
| 22 | `tim-kiem-tin-tuc` | auto | 10 | 1.1.1 | news_symbol |
| 23 | `tin-tuc-nong-quoc-te` | auto | 8 | 1.0.1 | news_market |
| 24 | `tin-tuc-nong-viet-nam` | auto | 9 | 1.0.1 | news_market |
| 25 | `ve-bieu-do-ky-thuat` | auto | 8 | 1.1.1 | chart_render (local) |
| 26 | `vn-market-basics` | auto | — | 1.1.1 | — |

---

## 1 · bat-on-quoc-gia
> File thật: `OpenTrading/skills/bat-on-quoc-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: bat-on-quoc-gia
description: Bất ổn quốc gia, ổn định, biểu tình, đảo chính, Thái Lan bất ổn gì. Dùng khi user hỏi độ ổn định/bất ổn của MỘT quốc gia cụ thể. Không dùng khi so sánh nhiều nước cùng lúc (tách mỗi nước 1 lượt skill này), bầu cử/chính sách toàn cầu (danh-gia-tinh-hinh-chinh-tri-toan-cau), chiến sự/xung đột vũ trang (danh-gia-tinh-hinh-xung-dot).
when_to_use: "User hỏi bất ổn/ổn định của MỘT quốc gia cụ thể: Thái Lan đang bất ổn gì, đo độ ổn định Trung Quốc, biểu tình/đảo chính ở đâu đó. Không dùng khi: so sánh nhiều nước (CHỈ chạy lặp skill này mỗi nước 1 lượt), bầu cử/chính sách toàn cầu (danh-gia-tinh-hinh-chinh-tri-toan-cau), chiến sự/xung đột vũ trang cụ thể (danh-gia-tinh-hinh-xung-dot)."
activation: auto
requires_tools: [mcp__opentrading__geo_intel]
tool_budget: 6
triggers:
  keywords: [bất ổn, bất ổn quốc gia, biểu tình, đảo chính, ổn định, thái lan, bangladesh]
version: 1.0.1
```

# Bất ổn quốc gia

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user nêu tên MỘT quốc gia + hỏi bất ổn/ổn định/biểu tình/đảo chính.
- KHÔNG dùng khi:
  - So sánh nhiều nước (ví dụ "ASEAN") → CHỈ chạy lặp skill này, mỗi nước 1 lượt riêng.
  - Bầu cử/chính sách toàn cầu → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.
  - Chiến sự/xung đột vũ trang cụ thể + ảnh hưởng thị trường → dùng `danh-gia-tinh-hinh-xung-dot`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `geo_intel`(topic=tên nước tiếng Anh) + `event_stats`(query=tên nước tiếng Anh) | BẮT BUỘC, 2 calls SONG SONG, cùng upstream GDELT |
| 2 | `news_market`(sources=gdelt, lọc theo tên nước) | CHỈ chạy khi Wave 1 mỏng/thiếu tin, TUẦN TỰ sau Wave 1 |
| 3 (tùy chọn impact) | `yf_commodities` hoặc `assets_rotation` (1 call) | CHỈ chạy khi user hỏi rõ "ảnh hưởng thị trường" |

- Pre-flight: KHÔNG có.
- Thứ tự: Wave 1 SONG SONG → Wave 2 TUẦN TỰ (nếu cần) → Wave 3 TUẦN TỰ (nếu cần).

## Verdict

Format BẮT BUỘC — 1 dòng verdict + từng mục evidence:

1. **Verdict 4 mức (CHỈ chọn 1):** ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG.
2. **Căn cứ (mỗi mục 1 dòng + URL):**
   - Tần suất event GDELT (so với baseline chính query đó — run này là baseline, run sau so sánh).
   - Mức độ (keywords protest/conflict/coup trong titles).
   - Coverage nước láng giềng.
   - Transmission sang giá nếu Wave 3 chạy (dầu/vàng/rotation, đơn vị USD/oz hoặc % move).
3. **Provenance:** MỖI mục BẮT BUỘC 1 dòng evidence + URL nguồn.

## Chống tràn lan

- Budget: BẮT BUỘC ≤6 calls/run.
- Cap: CHỈ 1 nước/run; query tiếng Anh 1 lần + TỐI ĐA 1 biến thể.
- CẤM quét nhiều nước trong 1 run (user hỏi "ASEAN" → đề nghị tách từng nước).
- CẤM gọi chồng chéo `geo_intel` + `event_stats` quá 1 cặp query; CẤM chạy Wave 3 nếu user không hỏi impact.
- Quy tắc dừng: Wave 1 có đủ counts + titles → DỪNG, không chạy Wave 2.

## Lỗi thường gặp

1. GDELT rate-limit → retry TỐI ĐA 1 lần sau backoff (server đã cache 600s) → vẫn lỗi thì ghi trung thực "GDELT rate-limit, verdict dựa trên dữ liệu cũ".
2. Coverage mỏng (nước ít tin) → đây là KẾT QUẢ, KHÔNG phải lỗi → ghi chú trung thực "low-coverage ≠ stable", KHÔNG suy diễn thành ỔN ĐỊNH.
3. Query tiếng Việt rỗng → đổi sang query tiếng Anh 1 lần rồi chấp nhận kết quả.

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: `geo_intel("Vietnam")` + `event_stats("vietnam")` trả articles counts OK; pipeline EN-query thông.

## Nghiệm thu

- Input mẫu "Bất ổn Thái Lan" → output BẮT BUỘC 4 mức verdict + ≥3 evidence lines có URL, ≤6 calls.


---

## 2 · co-ban-chuyen-sau
> File thật: `OpenTrading/skills/co-ban-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: co-ban-chuyen-sau
description: "BCTC, báo cáo tài chính, cơ bản, lợi nhuận gộp, nợ phải trả, vốn chủ, M-Score, thao túng, cổ đông lớn, cổ tức, kế hoạch kinh doanh từng dòng 1 mã. Dùng khi user hỏi đọc BCTC, chất lượng lợi nhuận, M-Score/F-score, kế hoạch, sở hữu, insider, cổ tức (BCTC FPT có gì lạ, VCB có thao túng không). Không dùng khi: kỹ thuật RSI/MACD → ky-thuat-chuyen-sau; định giá fair value/PER → dinh-gia-chuyen-sau; so sánh nhiều mã → so-sanh-cung-nganh."
when_to_use: "Đọc BCTC 1 mã (BCTC FPT có gì lạ, VCB có dấu hiệu thao túng không, cổ đông lớn HPG, cổ tức, kế hoạch kinh doanh). Không dùng khi: hỏi kỹ thuật (RSI/MACD/breakout → ky-thuat-chuyen-sau), hỏi định giá fair value/PER/upside (→ dinh-gia-chuyen-sau), so sánh nhiều mã (→ so-sanh-cung-nganh), phân tích toàn diện 8 bước (→ phan-tich-chuyen-sau-1-ma)."
activation: auto
requires_tools: [mcp__opentrading__financial_detail]
tool_budget: 9
triggers:
  keywords: [bctc, báo cáo tài chính, cơ bản, lợi nhuận gộp, nợ phải trả, vốn chủ, m-score, thao túng, cổ đông lớn, cổ tức, kế hoạch kinh doanh]
version: 1.0.1
```

# Cơ bản chuyên sâu 1 mã

Phân tích THUẦN cơ bản 1 mã: BCTC từng dòng, chất lượng lợi nhuận (M-Score/F-score), kế hoạch, sở hữu, cổ tức.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi BCTC, chất lượng lợi nhuận, M-Score/thao túng, F-score, kế hoạch kinh doanh, cổ đông lớn, insider, cổ tức của 1 mã (`BCTC FPT có gì lạ`, `VCB có thao túng không`, `cổ đông lớn HPG`).
- Khi KHÔNG dùng:
  - Hỏi kỹ thuật (RSI, MACD, breakout, hỗ trợ/kháng cự) → `ky-thuat-chuyen-sau`.
  - Hỏi định giá (fair value, PER, upside) → `dinh-gia-chuyen-sau`.
  - So sánh 2-6 mã → `so-sanh-cung-nganh`.
  - Phân tích toàn diện 1 mã → `phan-tich-chuyen-sau-1-ma`.
  - Đọc báo cáo CTCK (không phải BCTC gốc) → `tim-co-hoi-bao-cao-ctck`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 0. Cửa JWT | `vs_auth_status` | JWT sống = được dùng `financial_detail`; JWT chết → nhánh mirror `vs_financeinfo`. GỌI TRỰC TIẾP, BẮT BUỘC đầu tiên. |
| 1. Lõi BCTC + chất lượng | `financial_detail` (statement=KQKD, periods_n=4) · `stock_forensic` (symbol) | Chạy song song 2 calls. GỌI TRỰC TIẾP. Aspect-gating: hỏi `chataluong` → CHỈ chạy Wave này rồi DỪNG. |
| 2. Trend + ratios (chọn) | `financial_statements` · `financial_ratios` · `vn_fundamentals` | Tối đa 3 calls. GỌI TRỰC TIẾP. Aspect-gating: CHỈ chạy khi user hỏi trend/ratios/toàn cảnh. |
| 3. Sở hữu/kế hoạch (chọn) | `planned_targets` · `holders` · `insider_trading` · `dividends_splits` | GỌI TRỰC TIẾP. Aspect-gating: hỏi `sohuu`/`cophieu`/`kehoach` → CHỈ chạy Wave này (+ Wave 1 nếu cần nền). |
| 4. Tham chiếu (chọn) | `vs_financial_norms` / `vs_financial_terms` / `vs_company_info` | CHỈ gọi khi cần giải thích norm_id/kỳ. GỌI TRỰC TIẾP. |

CẤM gọi chồng chéo: `vs_financeinfo` CHỈ là fallback khi JWT chết, CẤM dùng song song với `financial_detail`. CẤM gọi `vs_documents` ở skill này (đó là tool của `tim-co-hoi-bao-cao-ctck`). LCTT/CDKT CHỈ gọi khi user hỏi explicitly dòng tiền/bảng cân đối (qua param `statement`), CẤM tự mở rộng.

## Verdict

BẮT BUỘC đủ các mục, mỗi mục ghi số + trend + provenance:

1. Chất lượng tăng trưởng: DT/LN 4 quý + trend QoQ/YoY + biên (`provenance: financial_detail`).
2. Ratios chủ chốt (`provenance: financial_ratios` / `vn_fundamentals`).
3. M-Score + F-score + red flags (`provenance: stock_forensic`).
4. So với kế hoạch: vượt/hụt % (`provenance: planned_targets`).
5. Cấu trúc sở hữu + thay đổi insider (`provenance: holders` / `insider_trading`).
6. Chính sách cổ tức (`provenance: dividends_splits`).
7. Kết luận 1 câu: CƠ BẢN TỐT/TRUNG BÌNH/YẾU + 3 rủi ro lớn nhất.

Thiếu leg nào → ghi rõ `thiếu leg X vì Y`, CẤM bịa số lấp chỗ trống.

## Chống tràn lan

- Budget ≤9 calls nhà. Aspect nào mới chạy leg đó: `chataluong` CHỈ Wave 1; `sohuu` CHỈ Wave 3.
- Cap: CHỈ 1 mã/lần; Wave 2 tối đa 3 calls.
- Quy tắc dừng: đủ M/F + 4 quý cho câu hỏi hẹp (`BCTC có gì lạ`) thì DỪNG, CẤM mở Wave 3–4.
- Reuse legs: skill `danh-gia-truoc-bctc` reuse leg của skill này qua aspect, CẤM gọi lại `financial_*` chồng chéo khi đã có số.

## Lỗi thường gặp

- Bank m_partial (SGAI null do LCTT rỗng — VCB live) → ghi `M không kết luận`, CẤM gán M=0.
- `financial_detail` periods vượt gói → rows rỗng + warning → degrade sang `vs_financeinfo` 1 lần duy nhất, ghi rõ fallback.
- `financial_statements` warning `statement not found, returning all pages` = đặc trưng v3-compat → đọc trang trong data, CẤM abort.
- `vn_company` chậm ~30s khi throttle → đặt cuối Wave, thiếu thì ghi thiếu, CẤM retry vô hạn.
- Partial data: leg nào rỗng → verdict partial + ghi nguồn thiếu, CẤM suy diễn số.

## Bằng chứng live (02-10-2026)

- FPT detail 25 norms × 138 số · M **−2.06**, F 2/6 · KH DT 61,850/75,400/58,580 · VCB holders SBV 74.8% · VCB cổ tức 450đ · insider empty là đúng data.

## Nghiệm thu

- `BCTC FPT có gì lạ` → Wave 1 (2 calls) đủ M/F + 4 quý.
- `Toàn cảnh cơ bản VPL` → ≤9 calls, không leg nào gọi 2 lần.


---

## 3 · danh-gia-tinh-hinh-chinh-tri-toan-cau
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-chinh-tri-toan-cau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-tinh-hinh-chinh-tri-toan-cau
description: Địa chính trị, rủi ro chính trị toàn cầu, bầu cử, chính sách Trump, căng thẳng quốc tế. Dùng khi user hỏi bản đồ rủi ro chính trị/bầu cử/chính sách nhiều nước. Không dùng khi xung đột vũ trang cụ thể (danh-gia-tinh-hinh-xung-dot), bất ổn 1 nước (bat-on-quoc-gia), chỉ xin odds thuần (du-doan-polymarket), Fed chuyên biệt (du-doan-fed).
when_to_use: "User hỏi địa chính trị tuần này, bầu cử Brazil/Mỹ, rủi ro chính sách, căng thẳng quốc tế dạng bản đồ nhiều sự kiện. Không dùng khi: xung đột vũ trang cụ thể + ảnh hưởng thị trường (danh-gia-tinh-hinh-xung-dot), bất ổn 1 nước (bat-on-quoc-gia), chỉ xin odds không cần tin (du-doan-polymarket), Fed chuyên biệt (du-doan-fed)."
activation: auto
tool_budget: 8
triggers:
  keywords: [địa chính trị, bầu cử, chính trị, chính sách trump, căng thẳng quốc tế, rủi ro chính trị]
version: 1.0.1
```

# Đánh giá tình hình chính trị toàn cầu

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi bản đồ rủi ro chính trị toàn cầu, bầu cử, chính sách, căng thẳng quốc tế (nhiều sự kiện, cần ghép odds + tin).
- KHÔNG dùng khi:
  - Xung đột vũ trang cụ thể (Trung Đông/Biển Đông) → dùng `danh-gia-tinh-hinh-xung-dot`.
  - Bất ổn 1 nước (Thái Lan...) → dùng `bat-on-quoc-gia`.
  - Chỉ xin odds/bảng Polymarket thuần → dùng `du-doan-polymarket`.
  - Fed cắt/giữ thuần → dùng `du-doan-fed`.
- Lưu ý thiết kế: skill tổ chức cross-ref, KHÔNG có home tool riêng (không phải vi phạm).

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 (odds + intel) | `world_prediction_odds`(tag=fed/politics/elections theo câu hỏi) + `geo_intel`(topic) | 2 calls SONG SONG |
| 2 (drill-down) | `polymarket_event`(slug top 1-2) + `event_stats`(query) | 2 calls SONG SONG, TUẦN TỰ sau Wave 1; CHỈ drill event thật sự liên quan |
| 3 (xác minh tin) | `news_market`(sources=gdelt) + `web_fetch`(1-2 nguồn chính thức trong tin) | TUẦN TỰ sau Wave 2; `web_fetch` CHỈ 1-2 URL chính thức |

- Pre-flight: KHÔNG có.
- Thứ tự: Wave 1 SONG SONG → Wave 2 SONG SONG → Wave 3 TUẦN TỰ.

## Verdict

Format BẮT BUỘC — bản đồ rủi ro 4–6 mục, mỗi mục gồm:

1. **Sự kiện:** tên + bối cảnh 1 dòng.
2. **Xác suất:** prob_pct từng outcome (đơn vị %) + end-date.
3. **Độ tin odds:** volume 24h + liquidity (đơn vị USD; <50k thì cờ "odds kém tin").
4. **Tin GDELT xác nhận:** 1 dòng + URL.
5. **Market-impact nếu có:** kênh truyền dẫn + URL.
6. **Provenance:** MỖI mục BẮT BUỘC event URL + tin URL.

## Chống tràn lan

- Budget: BẮT BUỘC ≤8 calls/run.
- Cap: odds đã sort vol24h → CHỈ lấy top 5, CẤM kéo cả 20 events.
- `polymarket_event` CHỈ cho event THẬT SỰ liên quan câu hỏi, TỐI ĐA 2 slugs/run.
- CẤM gọi chồng chéo `geo_intel` + `event_stats` + `news_market` cùng query quá 1 vòng.
- Quy tắc dừng: đủ 4 mục có prob + tin xác nhận → DỪNG, không mở thêm drill-down.

## Lỗi thường gặp

1. GDELT rate-limit (đã gặp live) → backoff 20s → retry TỐI ĐA 1 lần → vẫn lỗi thì ghi trung thực "thiếu tin GDELT, verdict chỉ dựa trên odds".
2. Gamma proxy chậm → tool tự fallback direct, chờ 1 lần → cả 2 đường chết thì ghi "không có odds", CẤM bịa xác suất.
3. Odds stale (end-date qua) → lọc `end > today`, loại event hết hạn.

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: Fed October 2026: "no change" 74.5% (volume 24h ~2.6M USD) · Brazil presidential event OK.

## Nghiệm thu

- Input mẫu "Rủi ro chính trị toàn cầu" → output ≥4 mục có prob_pct + provenance event URL.


---

## 4 · danh-gia-tinh-hinh-xung-dot
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-xung-dot/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-tinh-hinh-xung-dot
description: Xung đột, chiến tranh, chiến sự Trung Đông Biển Đông leo thang, dầu hay vàng lên. Dùng khi user hỏi 1 cuộc xung đột vũ trang cụ thể + ảnh hưởng thị trường. Không dùng khi chính trị bầu cử rộng (danh-gia-tinh-hinh-chinh-tri-toan-cau), bất ổn 1 nước không chiến sự (bat-on-quoc-gia), odds thuần (du-doan-polymarket).
when_to_use: "User hỏi Trung Đông, Biển Đông, chiến sự X ảnh hưởng gì thị trường, leo thang ra sao. Không dùng khi: chính trị/bầu cử rộng không chiến sự (danh-gia-tinh-hinh-chinh-tri-toan-cau), bất ổn 1 nước dạng biểu tình/đảo chính (bat-on-quoc-gia), chỉ xin odds không cần tin (du-doan-polymarket)."
activation: auto
requires_tools: [mcp__opentrading__event_stats]
tool_budget: 9
triggers:
  keywords: [xung đột, chiến tranh, biển đông, trung đông, leo thang, dầu hay vàng lên, chiến sự]
version: 1.0.1
```

# Đánh giá tình hình xung đột

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user nêu 1 xung đột/chiến sự cụ thể + hỏi cường độ, leo thang, giá đã phản ánh, kênh truyền dẫn, hàm ý vị thế.
- KHÔNG dùng khi:
  - Chính trị/bầu cử rộng → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.
  - Bất ổn 1 nước (biểu tình/đảo chính, chưa thành chiến sự) → dùng `bat-on-quoc-gia`.
  - Chỉ xin odds thuần → dùng `du-doan-polymarket`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 (cường độ) | `geo_intel`(topic xung đột) + `event_stats`(query) | BẮT BUỘC, 2 calls SONG SONG; từ khóa THỬ cả tiếng Việt lẫn Anh |
| 2 (giá phản ánh) | `yf_commodities`(dầu + vàng) + `assets_rotation` | 2 calls SONG SONG, TUẦN TỰ sau Wave 1 |
| 3 (leo thang + xác minh) | `world_prediction_odds`(từ khóa cuộc chiến) + `web_search`/`web_fetch` | TUẦN TỰ sau Wave 2; `web_fetch` CHỈ 1-2 nguồn |

- Pre-flight: KHÔNG có.
- Thứ tự: Wave 1 SONG SONG → Wave 2 SONG SONG → Wave 3 TUẦN TỰ.

## Verdict

Format BẮT BUỘC — đủ 5 mục:

1. **Cường độ:** event counts GDELT trend (đơn vị counts + trend tăng/giảm) + URL.
2. **Giá đã phản ánh chưa:** dầu/vàng move vs baseline (đơn vị USD/thùng, USD/oz, % move) + URL.
3. **Kênh truyền dẫn:** energy → inflation → rates, 1–2 dòng + URL.
4. **Xác suất leo thang:** odds prob_pct (đơn vị %) + end-date + URL event.
5. **Hàm ý vị thế:** đánh giá cushion/size trong `danh-gia-truoc-bctc` leg 6 trước khi hành động (KHÔNG khuyến nghị mua/bán trực tiếp).

## Chống tràn lan

- Budget: BẮT BUỘC ≤9 calls/run.
- Cap: CHỈ 1 topic/call; từ khóa TỐI ĐA 2 lần thử ("biển đông" → "south china sea") rồi chấp nhận "ít coverage".
- CẤM gọi chồng chéo `geo_intel` + `event_stats` quá 1 cặp query/topic.
- CẤM mở rộng sang nhiều cuộc chiến trong 1 run; user hỏi rộng thì đề nghị tách từng xung đột.
- Quy tắc dừng: Wave 1 có counts + Wave 2 có giá dầu/vàng → đủ verdict cơ bản, Wave 3 chỉ khi cần odds.

## Lỗi thường gặp

1. GDELT rỗng với từ khóa tiếng Việt → chuyển English query là ĐẶC TRƯNG data, KHÔNG phải lỗi → ghi chú trung thực "query VN rỗng, dùng EN query X", retry TỐI ĐA 1 lần EN.
2. `yf_commodities` thiếu phiên mới → dùng phiên gần nhất có + ghi rõ date, CẤM bịa giá hiện tại.
3. Odds không có market cho cuộc chiến → ghi "không có odds", KHÔNG thay bằng nhận định riêng.

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: `geo_intel("Vietnam")` trả articles · `event_stats("vietnam")` articles >0 · gold 4,195 USD/oz cùng phiên.

## Nghiệm thu

- Input mẫu "Xung đột X ảnh hưởng gì" → output đủ 5 mục verdict, có số dầu/vàng phiên gần nhất.


---

## 5 · danh-gia-truoc-bctc
> File thật: `OpenTrading/skills/danh-gia-truoc-bctc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-truoc-bctc
description: "trước BCTC, sắp ra báo cáo, pre-earnings, công bố lợi nhuận, setup BCTC, grade A/B/C từ 6 leg sự kiện-trend-thao túng-kỳ vọng-positioning-đệm. Dùng khi mùa BCTC cận kề user hỏi đánh giá setup (FPT sắp ra báo cáo có nên mua). Không dùng khi: phân tích mã thường → phan-tich-chuyen-sau-1-ma; BCTC đã công bố cần đọc số → co-ban-chuyen-sau; hỏi kỹ thuật lẻ → ky-thuat-chuyen-sau."
when_to_use: "Mùa BCTC cận kề, BCTC chưa ra (FPT sắp ra báo cáo, đánh giá setup trước BCTC). Không dùng khi: phân tích mã thường (→ phan-tich-chuyen-sau-1-ma), BCTC đã công bố cần đọc số (→ co-ban-chuyen-sau), hỏi định giá lẻ (→ dinh-gia-chuyen-sau)."
activation: auto
requires_tools: [mcp__opentrading__company_events]
tool_budget: 10
triggers:
  keywords: [trước bctc, sắp ra báo cáo, pre earnings, công bố lợi nhuận, setup bctc]
version: 1.0.1
```

# Đánh giá trước BCTC

Đánh giá setup trước BCTC: grade A/B/C từ 6 leg (sự kiện, trend, thao túng, kỳ vọng, positioning, đệm). CẤM forecast KQKD.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: BCTC chưa ra và user hỏi setup trước BCTC (`FPT sắp ra báo cáo`, `đánh giá setup HPG trước BCTC`, `pre-earnings`).
- Khi KHÔNG dùng:
  - Phân tích mã thường (không gắn BCTC) → `phan-tich-chuyen-sau-1-ma`.
  - BCTC đã công bố, cần đọc số/M-Score → `co-ban-chuyen-sau`.
  - Hỏi kỹ thuật lẻ → `ky-thuat-chuyen-sau`.
  - Hỏi định giá lẻ → `dinh-gia-chuyen-sau`.

## Workflow (6 leg)

| Leg | Tools | Ghi chú |
|---|---|---|
| 1. Ngày | `company_events` + `event_calendar_vn` | Ngày BCTC dated hay rumor? GỌI TRỰC TIẾP. BẮT BUỘC đầu tiên — chưa rõ ngày thì các leg còn lại ghi `unknown ngày`. |
| 2. Trend | LOAD `co-ban-chuyen-sau` (aspect=baokao) | Reuse leg, CẤM gọi lại `financial_*` chồng chéo. DISPATCH/LOAD sub-skill, CẤM gọi trực tiếp. |
| 3. Thao túng | LOAD `co-ban-chuyen-sau` (aspect=chataluong) | Lấy M-Score/Piotroski. Reuse leg, CẤM gọi lại `stock_forensic` trực tiếp. |
| 4. Kỳ vọng | `planned_targets` + `analyst_consensus` + `news_symbol` + `sentiment_score` | Anchor = kế hoạch DN (VN không consensus EPS). GỌI TRỰC TIẾP. `sentiment_score` là heuristic. |
| 5. Positioning | `insider_trading` + `money_flow` + `block_trades` | Dòng tiền + nội bộ + thỏa thuận. GỌI TRỰC TIẾP. |
| 6. Đệm | LOAD `dinh-gia-chuyen-sau` + `scenario_simulate` (−5%) | Lấy đệm định giá + size gợi ý. Reuse sub-skill, CẤM gọi trực tiếp `valuation_run`. |

CẤM gọi chồng chéo: Leg 2–3–6 BẮT BUỘC reuse qua `co-ban-chuyen-sau` / `dinh-gia-chuyen-sau`, CẤM gọi trực tiếp `financial_detail` / `financial_statements` / `stock_forensic` / `valuation_run` tại skill này. Aspect-gating: leg nào cũng ghi rõ aspect reuse.

## Verdict

BẮT BUỘC format:

1. Grade **A/B/C** (rubric: A = ≥5 leg xanh + M-Score sạch + KH rõ; B = 4–5 leg; C = <4 leg hoặc M-Score đỏ > −1.78).
2. 1 dòng evidence/leg (6 dòng, mỗi dòng số + trend + provenance).
3. Size đề xuất (từ Leg 6 `scenario_simulate` −5%).
4. Unknowns tường minh (liệt kê điều chưa biết).
5. Kết luận 1 câu: grade + có nên giữ/mua trước BCTC + rủi ro lớn nhất.

CẤM forecast KQKD (CẤM đưa số DT/LN dự báo). `sentiment_score` heuristic CẤM tính là 1 leg xanh đầy đủ.

## Chống tràn lan

- Budget ≤10 calls nhà (reuse legs tính vào budget sub-skill, KHÔNG cộng dồn).
- Cap: CHỈ 1 mã/lần; 6 leg là trần, CẤM thêm leg thứ 7.
- Quy tắc dừng: đủ 6 leg evidence (kể cả partial) thì DỪNG, CẤM gọi thêm vòng tin/dòng tiền thứ hai.
- Reuse legs: Leg 2–3–6 BẮT BUỘC reuse, CẤM chạy lại tool gốc.

## Lỗi thường gặp

- BCTC đã ra rồi mà vẫn gọi skill này → DỪNG, chuyển sang `co-ban-chuyen-sau`, CẤM cố chấm grade.
- Không rõ ngày BCTC (Leg 1 rumor) → grade tối đa B + ghi unknowns, CẤM chấm A.
- `sentiment_score` âm/dương nhẹ → ghi đúng là heuristic, CẤM nâng thành leg xanh/đỏ.
- Partial data (thiếu positioning hoặc kỳ vọng) → verdict partial + unknowns, CẤM bịa số lấp leg.

## Bằng chứng live (02-10-2026, FPT)

- M **−2.06** sạch · F 2/6 · KH DT 61,850/75,400/**58,580** · thưởng CP 10:1 ex 21-09 · sentiment heuristic −0.25 · NN bán ròng · pt 0% phiên → grade B.

## Nghiệm thu

- `Đánh giá trước BCTC HPG` → có grade + 6 leg evidence + unknowns, ≤10 calls (reuse legs).


---

## 6 · danh-gia-vi-mo-quoc-te
> File thật: `OpenTrading/skills/danh-gia-vi-mo-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-vi-mo-quoc-te
description: Kinh tế Mỹ, kinh tế toàn cầu, suy thoái recession, đường cong lợi suất yield curve, risk-on risk-off, Fed bối cảnh. Dùng khi user hỏi chu kỳ/bối cảnh vĩ mô Mỹ/global, việc làm, GDP các nước, chế độ rủi ro. Không dùng khi vĩ mô Việt Nam (danh-gia-vi-mo-viet-nam), xác suất Fed cắt/giữ thuần odds (du-doan-fed).
when_to_use: "User hỏi kinh tế Mỹ/global: Fed ở mức bối cảnh (không phải odds), lợi suất, việc làm, GDP các nước, risk regime, so sánh VN-vs-global. Không dùng khi: vĩ mô Việt Nam chi tiết (danh-gia-vi-mo-viet-nam), xác suất Fed thuần túy (du-doan-fed)."
activation: auto
requires_tools: [mcp__opentrading__fred_series]
tool_budget: 10
triggers:
  keywords: [kinh tế mỹ, recession, suy thoái, đường cong lợi suất, yield curve, risk-on, risk-off, fed bối cảnh, kinh tế toàn cầu]
version: 1.0.1
```

# Đánh giá vĩ mô quốc tế

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi chu kỳ Mỹ (soft/hard landing), đường cong lợi suất, việc làm/GDP các nước, chế độ rủi ro toàn cầu, so sánh VN-vs-global.
- KHÔNG dùng khi:
  - Vĩ mô VN chi tiết (GDP/CPI/XNK/SBV) → dùng `danh-gia-vi-mo-viet-nam`.
  - Xác suất Fed cắt/giữ/tăng thuần odds + lịch FOMC → dùng `du-doan-fed`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 (chu kỳ Mỹ) | `fred_series`(DGS10) + `fred_series`(CPIAUCSL) + `yf_yield_curve` | 3 calls SONG SONG; FRED GỌI THEO TÊN chuẩn |
| 2 (chế độ rủi ro) | `yf_regime_assets` + `assets_rotation` + `world_macro_country`(VN/CHINA theo câu hỏi) | 3 calls SONG SONG, TUẦN TỰ sau Wave 1 |
| 3 (xác nhận toàn cầu) | `yf_global_indices` + `yf_commodities` + `world_fear_greed` | 3 calls SONG SONG, TUẦN TỰ sau Wave 2 |

- Pre-flight: KHÔNG có.
- Thứ tự: Wave 1 → Wave 2 → Wave 3 TUẦN TỰ từng Wave, trong mỗi Wave SONG SONG.

## Verdict

Format BẮT BUỘC — đủ 5 mục:

1. **Chu kỳ Mỹ:** soft/hard landing, dựa DGS10 + CPI + curve, đơn vị % lợi suất + % CPI + URL.
2. **Đường cong:** inverted hay không, chênh 10Y-2Y (đơn vị bps/%) + URL.
3. **Chế độ toàn cầu:** RISK-ON/OFF từ rotation/regime assets + URL.
4. **So VN-vs-global:** BẮT BUỘC 1 dòng so sánh GDP VN (cross-ref S3, đơn vị % WorldBank) vs global + URL.
5. **Biến số theo dõi:** liệt kê CPI Mỹ, jobs, lợi suất cần watch tiếp theo.

## Chống tràn lan

- Budget: BẮT BUỘC ≤10 calls/run.
- Cap: FRED series GỌI THEO TÊN; ≥3 series cùng lúc là dấu hiệu tràn lan → DỪNG.
- Nhóm `yf_*` TỐI ĐA 3 calls/Wave; CẤM gọi chồng chéo `yf_yield_curve` + `fred_series` quá 1 vòng.
- Quy tắc dừng: Wave 1 đủ DGS10 + CPI + curve → mới sang Wave 2; thiếu FRED key thì chuyển nhánh không-FRED (xem Lỗi).

## Lỗi thường gặp

1. FRED thiếu key → trả unavailable → chuyển nhánh không-FRED (dùng `yf_yield_curve` + `yf_global_indices`) + ghi chú trung thực "thiếu FRED, verdict thiếu series X".
2. Curve flaky (từng fail rồi tự hồi) → retry TỐI ĐA 1 lần sau backoff → vẫn fail thì BỎ, ghi chú "không có curve phiên này".
3. `world_macro_country` rỗng → thử đổi mã nước (VN/CHINA) 1 lần rồi chấp nhận "ít coverage".

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: US10Y 5.24% / 2Y 4.61%, không đảo chiều · WorldBank GDP VN 8.02% · fear/greed crypto 70-74 (tham lam).

## Nghiệm thu

- Input mẫu "Kinh tế Mỹ hiện tại" → output đủ 5 mục verdict, có curve + ≥2 series FRED có số.


---

## 7 · danh-gia-vi-mo-viet-nam
> File thật: `OpenTrading/skills/danh-gia-vi-mo-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-vi-mo-viet-nam
description: Vĩ mô Việt Nam, GDP, CPI, lạm phát, xuất nhập khẩu XNK, tỷ giá USDVND, lãi suất SBV, câu chuyện dẫn dắt thị trường. Dùng khi user hỏi số liệu/bối cảnh/lịch công bố vĩ mô VN. Không dùng khi vĩ mô Mỹ/toàn cầu (danh-gia-vi-mo-quoc-te), thao tác vàng-tỷ giá (phan-tich-vang-ty-gia), xác suất Fed thuần (du-doan-fed).
when_to_use: "User hỏi GDP/CPI/XNK Việt Nam, tỷ giá USDVND trong bối cảnh vĩ mô, lãi suất điều hành SBV, lịch công bố số liệu NSO, câu chuyện dẫn dắt thị trường VN. Không dùng khi: vĩ mô Mỹ/toàn cầu (danh-gia-vi-mo-quoc-te), thao tác vàng-tỷ giá chi tiết (phan-tich-vang-ty-gia)."
activation: auto
requires_tools: [mcp__opentrading__vs_indicator_data]
tool_budget: 12
triggers:
  keywords: [vĩ mô, GDP, CPI, lạm phát, xuất khẩu, nhập khẩu, lãi suất điều hành, sbv, xnk, cán cân, câu chuyện thị trường, dẫn dắt]
version: 1.1.1
```

# Đánh giá vĩ mô Việt Nam

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi số liệu VN (GDP/CPI/XK/NK), lãi suất SBV, tỷ giá USDVND bối cảnh vĩ mô, lịch công bố NSO, báo cáo vĩ mô CTCK, câu chuyện dẫn dắt thị trường VN.
- KHÔNG dùng khi:
  - Vĩ mô Mỹ/toàn cầu, Fed bối cảnh, risk regime → dùng `danh-gia-vi-mo-quoc-te`.
  - Xác suất Fed cắt/giữ thuần odds → dùng `du-doan-fed`.
  - Thao tác vàng-tỷ giá chi tiết → dùng `phan-tich-vang-ty-gia`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 (pre-flight) | `source_status` + `vs_auth_status` | BẮT BUỘC, 2 calls SONG SONG trước mọi Wave |
| 1 (data VN BẮT BUỘC) | `vs_categories`(tra id nếu cần) → `vs_indicator_data`(GDP 73 tt3) + `vs_indicator_data`(CPI 15 tt7 sub2) + `vs_indicator_data`(XK 38 tt2) + `vs_xnk_detail`(xk hoặc nk) | TUẦN TỰ: `vs_categories` trước, rồi các `vs_indicator_data` SONG SONG; cặp category/termType PHẢI ĐÚNG (sai là rows rỗng) |
| 2 (tin vĩ mô) | `news_market`(lọc vĩ mô/lãi suất/tỷ giá) + `macro_events_vn` + `economic_calendar` | 3 calls SONG SONG, nguồn Fireant/GDELT + NSO |
| 3 (báo cáo CTCK) | `analyst_consensus`(report_type=macro, limit=30) | CHỈ 1 call feed chung; lấy section pointers + dated reports (entry_kind); không có dated thì dùng số liệu gốc Wave 1 |
| 4 (data bổ sung) | `snapshot_history`(macro_curated) + `yf_yield_curve` + `sbv_rates` + `vn_retail_fx` | Mỗi thứ TỐI ĐA 1 call, SONG SONG; DXY kèm curve để xem bối cảnh hút vốn ngoại |
| 5 (lịch sự kiện) | `macro_events_vn`(NSO) + kỳ họp Fed/Mỹ (cross-ref `du-doan-fed`) | Lịch VN + lịch ngoại tác động VN |

## Verdict

Format BẮT BUỘC — đủ 6 mục + câu chuyện:

1. **Tăng trưởng:** GDP, ≥8 điểm cuối, đơn vị % yoy + URL/provenance.
2. **Lạm phát:** CPI, ≥8 điểm cuối, đơn vị % yoy + URL.
3. **Thương mại:** XK/NK/XNK-detail, đơn vị triệu USD + URL.
4. **Tỷ giá:** USDVND (đơn vị VND), SBV rates (tái cấp vốn/tái chiết khấu, đơn vị %) + URL.
5. **Lãi suất:** lãi suất điều hành SBV + bối cảnh hút vốn ngoại (curve/DXY) + URL.
6. **Điểm tích cực / tiêu cực + triển vọng tương lai.**
7. **Câu chuyện dẫn dắt thị trường + lịch sự kiện** (mỗi câu chuyện: sự kiện nào, ngày nào, tác động gì).

## Chống tràn lan

- Budget: BẮT BUỘC ≤12 calls/run.
- Cap: CHỈ 4–6 series vĩ mô; CẤM quét cả 60 categories.
- `vs_xnk_detail` CHỈ chọn 1 direction (xk hoặc nk) theo câu hỏi.
- `analyst_consensus` macro CHỈ 1 call feed chung, CẤM bắn theo từng từ khóa.
- CẤM gọi chồng chéo `macro_events_vn` quá 2 lần/run.

## Lỗi thường gặp

1. Thiếu HAR session → macro trả permission message → BẮT BUỘC ghi trung thực "macro cần session", fallback sang `snapshot_history`; CẤM diễn giải message permission thành dữ liệu.
2. `vs_indicator_data` rows rỗng → kiểm tra lại cặp category/termType (GDP 73/tt3, CPI 15/tt7/sub2, XK 38/tt2), retry TỐI ĐA 1 lần với id đúng → vẫn rỗng thì ghi "không có số liệu kỳ này".
3. Curve/DXY flaky → retry 1 lần sau backoff rồi bỏ, ghi chú thiếu bối cảnh.

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: GDP 504 rows tới Q2/2026 · CPI 1,839 · XK 2,941 · XNK-country 3,675 · SBV tái cấp vốn 4.5% / tái chiết khấu 3% · USDVND 25,970 · NSO lịch CPI tháng 8.

## Nghiệm thu

- Input mẫu "Vĩ mô VN" → output đủ 6 mục + câu chuyện dẫn dắt có lịch sự kiện, ≤12 calls.


---

## 8 · devil-advocate
> File thật: `OpenTrading/skills/devil-advocate/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: devil-advocate
description: "Phản biện, bear case, có nên giữ, đang nắm đang giữ cổ phiếu, rủi ro gì — người phản biện luận điểm đầu tư để chống thiên kiến xác nhận. Dùng khi user hỏi về mã họ đang nắm hoặc đã thích, xin ý kiến về luận điểm mua/giữ, hoặc yêu cầu phản biện trực tiếp. Không dùng khi: user chỉ hỏi định nghĩa thuật ngữ (dùng explain-term), hoặc xin phân tích kỹ thuật/định giá chi tiết (dùng ky-thuat-chuyen-sau, dinh-gia-chuyen-sau)."
when_to_use: Người dùng hỏi về mã họ đang nắm hoặc đã thích, xin ý kiến về một luận điểm mua/giữ, hoặc yêu cầu phản biện bear case / rủi ro gì. Không dùng để giải thích thuật ngữ hay vẽ chart.
activation: auto
triggers:
  keywords: [phản biện, bear case, có nên giữ, rủi ro gì, đang nắm, đang giữ]
version: 1.1.1
```

# Người phản biện (Devil's Advocate)

Vai trò của bạn là người phản biện. Người dùng thường hỏi về cổ phiếu họ đã mua hoặc đã thích — nhiệm vụ là chống thiên kiến xác nhận, KHÔNG phải chê bai hay kết luận thay.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user nói đang nắm/đang giữ một mã, hỏi có nên giữ không, rủi ro gì, xin bear case, hoặc yêu cầu phản biện luận điểm mua/giữ.
- Khi KHÔNG dùng: hỏi định nghĩa P/E, EPS, margin... (CHỈ dùng `explain-term`); xin chart/nến (CHỈ dùng `ve-bieu-do-ky-thuat`); hỏi cơ chế sàn/phiên/biên độ (CHỈ dùng `vn-market-basics`).

## Workflow (5 bước BẮT BUỘC)

| Bước | Việc làm | Ghi chú |
|---|---|---|
| 1 | Tóm tắt luận điểm user trong 1–2 câu | Xác nhận hiểu đúng trước khi phản biện; CẤM bóp méo luận điểm. |
| 2 | Liệt kê 3–5 lý do mạnh nhất khiến luận điểm có thể SAI | Phủ ngành, doanh nghiệp, định giá, vĩ mô, thanh khoản. |
| 3 | Với mỗi lý do, nêu dấu hiệu cụ thể cần theo dõi | Chỉ số/sự kiện nào cho thấy rủi ro đang xảy ra. |
| 4 | Nêu điều kiện phủ định | Sự kiện nào xảy ra thì luận điểm nên bị bỏ. |
| 5 | Giữ giọng trung lập | Không mỉa mai, CẤM kết luận mua/bán thay user. |

## Verdict (format BẮT BUỘC)

Luận điểm tóm tắt (1–2 câu) · 3–5 rủi ro + dấu hiệu theo dõi từng cái · điều kiện phủ định (khi nào nên bỏ luận điểm).

## Chống tràn lan + Cảnh báo BẮT BUỘC

- CHỈ phản biện luận điểm user đưa; CẤM lan sang định giá chi tiết hay khuyến nghị mua/bán cụ thể.
- Giọng trung lập; CẤM mỉa mai, CẤM kết luận thay người dùng.

## Lỗi thường gặp

- Chỉ khen theo user (xác nhận thiên kiến) → sai vai; BẮT BUỘC nêu 3–5 lý do có thể SAI.
- Phản biện chung chung không có dấu hiệu theo dõi → BẮT BUỘC mỗi rủi ro kèm 1 dấu hiệu cụ thể.
- Tự kết luận "nên bán" → CẤM; CHỈ đưa điều kiện phủ định để user tự quyết.

## Lưu ý

Skill nền lý luận, không gọi tool dữ liệu, không có số live cố định — CẤM bịa giá/chỉ số minh họa thành số thật; mọi số phải ghi rõ "ví dụ giả định" hoặc lấy từ skill phân tích.

## Nghiệm thu

Câu hỏi "đang giữ mã X, có nên giữ không" → tóm tắt 1–2 câu + 3–5 rủi ro có dấu hiệu + điều kiện phủ định, giọng trung lập.


---

## 9 · dinh-gia-chuyen-sau
> File thật: `OpenTrading/skills/dinh-gia-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: dinh-gia-chuyen-sau
description: "định giá, fair value, DCF, PER, PB, đắt hay rẻ, upside/downside, giá mục tiêu tự tính, valuation 1 mã. Dùng khi user hỏi mã đắt chưa, fair value bao nhiêu, định giá theo PER (FPT đắt chưa, VCB fair value). Không dùng khi: so sánh nhiều mã → so-sanh-cung-nganh; cơ bản thuần BCTC/M-Score → co-ban-chuyen-sau; kỹ thuật RSI → ky-thuat-chuyen-sau."
when_to_use: "Hỏi định giá 1 mã (FPT đắt chưa, VCB fair value bao nhiêu, định giá theo PER, upside còn bao nhiêu). Không dùng khi: so sánh nhiều mã (→ so-sanh-cung-nganh), cơ bản thuần BCTC/M-Score (→ co-ban-chuyen-sau), phân tích toàn diện (→ phan-tich-chuyen-sau-1-ma sẽ DISPATCH skill này)."
activation: auto
requires_tools: [mcp__opentrading__valuation_run]
tool_budget: 7
triggers:
  keywords: [định giá, fair value, dcf, per, đắt hay rẻ, upside, giá mục tiêu tự tính, valuation]
version: 1.0.1
```

# Định giá chuyên sâu 1 mã

Định giá 1 mã: vùng fair value (PER/PB/DCF-lite), so lịch sử, UPSIDE/DOWNSIDE %.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi định giá 1 mã (`FPT đắt chưa`, `VCB fair value`, `định giá theo PER`, `upside còn bao nhiêu`).
- Khi KHÔNG dùng:
  - So sánh nhiều mã → `so-sanh-cung-nganh`.
  - Cơ bản thuần (BCTC, M-Score, sở hữu) → `co-ban-chuyen-sau`.
  - Kỹ thuật thuần → `ky-thuat-chuyen-sau`.
  - Giá mục tiêu của CTCK (tổng hợp báo cáo sẵn có) → `tim-co-hoi-bao-cao-ctck` (CHỈ cross-ref để neo kỳ vọng, không thay thế định giá tự tính).

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Fair value lõi | `valuation_run` (symbol, method) · `vs_overview_trading` (symbol) | Chạy song song 2 calls. GỌI TRỰC TIẾP. `method` mặc định auto; CHỈ đổi method khi user khăng khăng. |
| 2. Neo lịch sử | `financial_ratios` (symbol) · `vn_quote_history` (symbol, days=365) | Tự tính PER/PB trung bình 2–3 năm. GỌI TRỰC TIẾP. |
| 3. Bối cảnh (chọn) | `yf_yield_curve` · `vs_trading_info` (symbol) | Lãi suất + trading info. GỌI TRỰC TIẾP. Bond context CHỈ khi mã PB-heavy (bank). |

CẤM gọi chồng chéo: DCF-lite trong `valuation_run` đã tính sẵn → CẤM tự dựng lại DCF. CẤM gọi `signals_technical` / `financial_detail` / `stock_forensic` trong skill này; cần chất lượng cơ bản thì cross-ref `co-ban-chuyen-sau`, CẤM gọi lại tool của skill đó.

## Verdict

BẮT BUỘC đủ các mục, mỗi mục ghi số + trend + provenance:

1. Giá hiện tại vs vùng fair: method nào dẫn, chênh bao nhiêu % (`provenance: valuation_run` + `vs_overview_trading`).
2. PER/PB hiện tại vs trung bình 2–3 năm tự tính (`provenance: financial_ratios` + `vn_quote_history`).
3. Rẻ/đắt vì sao: tăng trưởng + chất lượng (cross-ref `co-ban-chuyen-sau`) + lãi suất (leg Wave 3).
4. UPSIDE/DOWNSIDE % + độ tin (cao nếu 2 method đồng thuận).
5. Dòng neo kỳ vọng: upside theo target CTCK (`provenance: tim-co-hoi-bao-cao-ctck` cross-ref, CHỈ tham chiếu).
6. Kết luận 1 câu: ĐẮT/HỢP LÝ/RẺ + UPSIDE/DOWNSIDE %.

## Chống tràn lan

- Budget ≤7 calls. Cap: CHỈ 1 mã; 1 `method` per run (auto trừ khi user khăng khăng), CẤM chạy đủ method để câu giờ.
- Quy tắc dừng: có fair value + so lịch sử thì DỪNG; Wave 3 CHỈ chạy khi cần bối cảnh lãi suất (bank/PB-heavy).
- Reuse: skill `phan-tich-chuyen-sau-1-ma` và `danh-gia-truoc-bctc` reuse skill này, CẤM gọi ngược lại chúng từ đây.

## Lỗi thường gặp

- `method` sai enum → warning → về auto, CẤM retry method lạ.
- EPS âm (công ty lỗ) → per_pb vô nghĩa → nói thẳng `không đủ cơ sở định giá`, CẤM bịa fair value.
- Bank (đặc thù PB) → ưu tiên per_pb, ghi rõ lý do.
- Partial data: thiếu lịch sử giá → bỏ so lịch sử, verdict partial + ghi thiếu, CẤM suy diễn PER lịch sử.

## Bằng chứng live (02-10-2026)

- VCB per_pb @57,400 (2 method đồng thuận) · FPT per_pb @62,700 · US10Y 5.24% context · overview_trading VCB PE/PB/ROEA đủ.

## Nghiệm thu

- `FPT đắt chưa` → có UPSIDE % + so lịch sử 2 dòng, ≤7 calls.


---

## 10 · du-doan-fed
> File thật: `OpenTrading/skills/du-doan-fed/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: du-doan-fed
description: Fed, FOMC, cắt giảm lãi suất hay giữ, dot plot, xác suất Fed, lãi suất Mỹ. Dùng khi user hỏi xác suất/kịch bản Fed kỳ tới + hàm ý cho VN. Không dùng khi bối cảnh vĩ mô Mỹ chung không cần odds (danh-gia-vi-mo-quoc-te), odds chủ đề khác ngoài Fed (du-doan-polymarket).
when_to_use: "User hỏi Fed tháng tới cắt hay giữ, FOMC khi nào, dot plot ra sao, xác suất từng kịch bản + hàm ý VN. Không dùng khi: bối cảnh vĩ mô Mỹ chung không cần odds (danh-gia-vi-mo-quoc-te)."
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 8
triggers:
  keywords: [fed, fomc, cắt giảm lãi suất, dot plot, xác suất fed, lãi suất mỹ]
version: 1.0.1
```

# Dự đoán Fed

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi Fed kỳ tới (cắt/giữ/tăng), FOMC, dot plot, xác suất odds + đường cong + hàm ý VN.
- KHÔNG dùng khi:
  - Bối cảnh vĩ mô Mỹ chung (chu kỳ, việc làm, risk regime) không cần odds → dùng `danh-gia-vi-mo-quoc-te`.
  - Odds chủ đề ngoài Fed (bầu cử, BTC...) → dùng `du-doan-polymarket`.
  - Bản đồ rủi ro chính trị rộng → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 (odds Fed) | `world_prediction_odds`(query=fed) | BẮT BUỘC 1 call, đã sort vol24h — lấy event top |
| 2 (drill + macro) | `polymarket_event`(slug fed-decision-*) + `fred_series`(DGS10, thêm EFFR/DFII nếu cần) | 2 calls SONG SONG, TUẦN TỰ sau Wave 1 |
| 3 (curve + xác minh) | `yf_yield_curve` + `web_fetch`(fed.gov statement/nguồn chính thức trong odds) | 2 calls SONG SONG, TUẦN TỰ sau Wave 2; `web_fetch` CHỈ nguồn chính thức |

- Pre-flight: KHÔNG có.
- Thứ tự: Wave 1 → Wave 2 → Wave 3 TUẦN TỰ.

## Verdict

Format BẮT BUỘC — đủ 5 mục:

1. **Xác suất từng kịch bản:** cắt/giữ/tăng, mỗi kịch bản prob_pct (đơn vị %) + volume (USD) + end-date + URL event.
2. **Đường cong ám chỉ:** US10Y/2Y (đơn vị %) + inverted hay không + URL.
3. **Lịch FOMC kế tiếp:** ngày họp (đơn vị ngày/tháng) + nguồn fed.gov URL.
4. **Biến số theo dõi:** CPI Mỹ, jobs, đơn vị %/K jobs + URL.
5. **Hàm ý cho VN:** tỷ giá/lãi suất (cross-ref S3/S16), 1–2 dòng + URL.

## Chống tràn lan

- Budget: BẮT BUỘC ≤8 calls/run.
- Cap: CHỈ 1 event Fed chính (slug mới nhất, đã sort vol24h) — CẤM bắn 5 query biến thể.
- `fred_series` TỐI ĐA 3 series (DGS10 + EFFR/DFII); CẤM quét thêm series ngoài Fed.
- CẤM gọi chồng chéo `polymarket_event` quá 1 slug Fed/run.
- Quy tắc dừng: có prob ≥2 kịch bản + lịch họp → đủ verdict, Wave 3 chỉ để xác minh.

## Lỗi thường gặp

1. Odds stale (end-date qua) → lọc `end > today`, BỎ event hết hạn → retry 1 lần query fed mới.
2. Gamma chết cả proxy + direct → ghi rõ trung thực "không có odds", CẤM thay bằng nhận định riêng.
3. Curve flaky → retry TỐI ĐA 1 lần sau backoff rồi bỏ, ghi chú thiếu curve.

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: "Fed Decision in October 2026": Yes(no change) 74.5% / No 25.5%, volume24h 2.6M · curve US10Y 5.24% không đảo.

## Nghiệm thu

- Input mẫu "Fed tháng tới" → output prob ≥2 kịch bản + lịch họp + 1 dòng hàm ý VN.


---

## 11 · du-doan-polymarket
> File thật: `OpenTrading/skills/du-doan-polymarket/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: du-doan-polymarket
description: Polymarket, odds, xác suất, prediction market, bao giờ bitcoin, cá cược sự kiện, market nào đang nóng. Dùng khi user hỏi xác suất/odds theo chủ đề bất kỳ ngoài Fed chuyên biệt. Không dùng khi Fed chuyên biệt cần curve + FOMC (du-doan-fed), bản đồ chính trị rộng cần ghép tin (danh-gia-tinh-hinh-chinh-tri-toan-cau).
when_to_use: "User hỏi market nào đang nóng, odds bầu cử Mỹ, bao giờ BTC chạm 100k, xác suất sự kiện X theo Polymarket. Không dùng khi: Fed chuyên biệt cần curve/FOMC/hàm ý VN (du-doan-fed), bản đồ chính trị rộng cần ghép tin GDELT (danh-gia-tinh-hinh-chinh-tri-toan-cau)."
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 6
triggers:
  keywords: [polymarket, odds, xác suất, prediction market, bao giờ bitcoin, cá cược sự kiện]
version: 1.0.1
```

# Dự đoán Polymarket

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi odds/xác suất Polymarket theo chủ đề (kinh tế, bầu cử, crypto...), "market nào đang nóng", drill-down 1–2 events.
- KHÔNG dùng khi:
  - Fed chuyên biệt (cần curve + FOMC + hàm ý VN) → dùng `du-doan-fed`.
  - Bản đồ chính trị rộng cần ghép odds + tin GDELT → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 (quét odds) | `world_prediction_odds`(query hoặc tag, limit=10) | BẮT BUỘC 1 call, đã sort vol24h — tin dùng top |
| 2 (drill-down 1) | `polymarket_event`(slug — 1 event user quan tâm) | TUẦN TỰ sau Wave 1; drill outcomes đầy đủ |
| 3 (drill-down 2, chọn lọc) | `polymarket_event`(slug thứ 2) | CHỈ chạy khi user hỏi rõ event thứ 2; TỐI ĐA 2 drill-down/run |

- Pre-flight: KHÔNG có.
- Thứ tự: Wave 1 → Wave 2 → Wave 3 TUẦN TỰ; CẤM chạy Wave 2 + 3 song song.

## Verdict

Format BẮT BUỘC — bảng + cờ + kết luận:

1. **Bảng event:** mỗi dòng {title · prob_pct từng outcome (đơn vị %) · volume24h (USD) · liquidity (USD) · end-date (ngày) · URL event}.
2. **Cờ tin cậy BẮT BUỘC trên từng dòng:**
   - (1) liquidity thấp (<50k USD) → "odds kém tin".
   - (2) end-date đã qua → LOẠI khỏi bảng.
3. **Kết luận:** 1 câu "thị trường đặt cược X với xác suất Y" (đơn vị %).
4. **Provenance:** MỖI dòng BẮT BUỘC URL event.

## Chống tràn lan

- Budget: BẮT BUỘC ≤6 calls/run.
- Cap: drill-down TỐI ĐA 2 events/run — người dùng chọn, skill CẤM tự mở cả top-10.
- Query rỗng → ĐỔI tag TỐI ĐA 1 lần rồi kết luận "không có market cho chủ đề", DỪNG.
- CẤM gọi chồng chéo `world_prediction_odds` quá 2 query/run.
- Quy tắc dừng: Wave 1 đủ ≥5 events → DỪNG nếu user chỉ hỏi "đang nóng gì", không drill-down.

## Lỗi thường gặp

1. Jina proxy chậm → tool tự fallback direct (xem warnings) → chờ 1 lần, CẤM retry dồn dập.
2. Gamma chết cả 2 đường → trả unavailable → ghi rõ trung thực "không có odds", CẤM bịa xác suất.
3. Slug sai/không tồn tại → đổi slug top kế tiếp 1 lần rồi ghi "không drill được event X".

## Bằng chứng live (02-10-2026)

- GIỮ NGUYÊN từ bản cũ, không bịa số mới: Fed T10/2026 no-change 74.5% (vol 2.6M) · Brazil presidential detail OK · sort vol24h hoạt động.

## Nghiệm thu

- Input mẫu "Polymarket đang nóng gì về kinh tế" → output ≥5 events + cờ tin-cậy trên từng dòng.


---

## 12 · explain-term
> File thật: `OpenTrading/skills/explain-term/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: explain-term
description: "Là gì, nghĩa là gì, giải thích, khái niệm, thuật ngữ — giải thích một thuật ngữ chứng khoán tài chính (P/E, EPS, ROE, margin, ATO ATC, room ngoại, T+2) cho nhà đầu tư cá nhân bằng tiếng Việt đơn giản. Dùng khi user hỏi một chỉ số hoặc khái niệm là gì. Không dùng khi: phản biện luận điểm mua/giữ (dùng devil-advocate), phân tích mã cụ thể hay vẽ chart (dùng ky-thuat-chuyen-sau, ve-bieu-do-ky-thuat)."
when_to_use: Người dùng hỏi một thuật ngữ, chỉ số hoặc khái niệm là gì (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2…). Không dùng để phản biện hay phân tích mã.
activation: auto
triggers:
  keywords: [là gì, nghĩa là gì, giải thích, khái niệm, thuật ngữ]
version: 1.1.1
```

# Giải thích thuật ngữ

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2... là gì, nghĩa là gì, xin giải thích khái niệm/chỉ số.
- Khi KHÔNG dùng: xin phản biện mã đang nắm (CHỈ dùng `devil-advocate`); xin phân tích mã cụ thể (CHỈ dùng `ky-thuat-chuyen-sau` / `dinh-gia-chuyen-sau`); hỏi cơ chế sàn/phiên/lô (CHỈ dùng `vn-market-basics`).

## Workflow (5 bước BẮT BUỘC)

| Bước | Việc làm | Ghi chú |
|---|---|---|
| 1 | Định nghĩa trong một câu | Không dùng biệt ngữ khác chưa giải thích. |
| 2 | Công thức (nếu có) | Viết bằng chữ, CẤM tự thay số thật. |
| 3 | Ví dụ minh họa số tròn giả định | BẮT BUỘC ghi rõ "ví dụ giả định". |
| 4 | Cách dùng thực tế ở VN + 1 cái bẫy hay gặp | VD đọc P/E thấp ảo do lợi nhuận đột biến, margin call, room ngoại khóa... |
| 5 | Kết thúc bằng 1 câu hỏi gợi mở | Giúp user đào sâu (VD "bạn muốn xem P/E này so với ngành không?"). |

## Verdict (format BẮT BUỘC)

Định nghĩa 1 câu · công thức bằng chữ · ví dụ giả định (ghi rõ giả định) · cách dùng ở VN + bẫy hay gặp · 1 câu hỏi gợi mở.

## Chống tràn lan

- CHỈ giải thích 1 thuật ngữ/lượt; CẤM lan sang phân tích mã hay khuyến nghị mua/bán.
- Mọi số minh họa là số tròn giả định; CẤM lấy số giả định làm số thật.

## Lỗi thường gặp

- Định nghĩa bằng biệt ngữ khác khó hơn → BẮT BUỘC dùng tiếng Việt đơn giản, 1 câu.
- Quên ghi "ví dụ giả định" khiến user tưởng số thật → CẤM.
- Trả lời dài như giáo trình → giữ gọn, CHỈ 5 bước trên.

## Lưu ý

Skill nền kiến thức, không gọi tool dữ liệu, không có số live cố định — CẤM bịa giá/chỉ số hiện tại; khi cần số thật thì gọi skill phân tích tương ứng.

## Nghiệm thu

"P/E là gì" → định nghĩa 1 câu + công thức chữ + ví dụ giả định có ghi rõ + bẫy VN + 1 câu hỏi gợi mở.


---

## 13 · kiem-chien-luoc-backtest
> File thật: `OpenTrading/skills/kiem-chien-luoc-backtest/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: kiem-chien-luoc-backtest
description: 'backtest, kiểm chứng chiến lược, SMA cross, RSI quá bán, momentum, param sweep, mùa vụ tháng, sau Tết, sau chia cổ tức, theo giá dầu vàng — Dùng khi kiểm chứng chiến lược bằng code qua pipeline baseline, kỹ thuật, thời gian, sự kiện, hàng hóa kèm best và worst param. Không dùng khi cần sizing vị thế cụ thể (dùng leg Đệm trong danh-gia-truoc-bctc), định giá nội tại (dùng dinh-gia-chuyen-sau).'
when_to_use: 'Dùng khi user hỏi chiến lược có ăn không (VD: SMA20/50 FPT có ăn không, mua khi RSI<30 có thắng không, tháng nào hay tăng, cổ phiếu sau Tết/chia cổ tức, theo giá dầu/vàng). Không dùng khi: cần sizing vị thế cụ thể và quản trị rủi ro (xem leg Đệm trong danh-gia-truoc-bctc); hỏi định giá DCF (dùng dinh-gia-chuyen-sau); hỏi tin/sentiment (dùng tim-kiem-tin-tuc / phan-tich-sentiment).'
activation: auto
requires_tools: [mcp__opentrading__quant_backtest]
tool_budget: 12
triggers:
  keywords: [backtest, kiểm chứng, chiến lược, sma cross, rsi dưới, quá bán, momentum chiến lược, param sweep, mùa vụ tháng, sau tết, sau chia cổ tức, theo giá dầu, theo giá vàng]
version: 1.1.1
```

# Kiểm chứng chiến lược (backtest)

Pipeline chuẩn mỗi run: baseline → chiến lược → sweep → seasonality/event → kết luận. Best PHẢI KÈM worst (chống overfit).

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: kiểm chứng điều kiện kỹ thuật (SMA/momentum/RSI), thời gian (tháng/quý), sau sự kiện (Tết/cổ tức/ĐHĐCĐ), theo giá hàng hóa (dầu/vàng).
- Khi KHÔNG dùng: sizing vị thế cụ thể → leg Đệm trong `danh-gia-truoc-bctc`; định giá → `dinh-gia-chuyen-sau`; tin/sentiment → `tim-kiem-tin-tuc` / `phan-tich-sentiment`.
- CẤM kết luận "đáng tin" khi chỉ có best mà thiếu worst; CẤM sweep >30 combos hoặc >3 symbol/run.

## Workflow

| Wave | Tools (giữ nguyên tool + params) | Ghi chú |
|---|---|---|
| 1. Dữ liệu — TUẦN TỰ đầu tiên | `vn_quote_history`(stock) hoặc `dnse_ohlc_history`(futures/index) · `vn_index_ohlcv`(benchmark) | 1 symbol/lần |
| 2. Điều kiện KỸ THUẬT | `backtest_strategies`(strategy=sma_cross/momentum/**rsi_meanrev** + rsi_low/rsi_high) | rsi_meanrev: mua RSI<30, thoát RSI>70 |
| 3. Điều kiện THỜI GIAN | `backtest_strategies` + `months`/`quarters` · `seasonality` (mô tả tháng/quý) | entries chỉ kỳ chọn, exits luôn mở |
| 4. Điều kiện SAU SỰ KIỆN | `event_study`(symbol, dates, window ±N) — CAR quanh Tết/cổ tức/ĐHĐCĐ (ngày từ `event_calendar_vn`) | nearest-day 3 phiên, hit-rate/best-worst |
| 5. Điều kiện GIÁ HÀNG HÓA | `backtest_strategies` + `condition_symbol` (BZ=F/GC=F... theo map ngành S13) + `condition_rule` above_sma/rising | vnstock→yfinance fallback trong tool |
| 6. Tổng hợp | `param_sweep`(≤30 combos, passthrough months/quarters) · `correlation_matrix` · `portfolio_optimize`(nhiều mã) | best KÈM worst (chống overfit) |

- `param_sweep` cap 30 combos có sẵn — KHÔNG tự nới; KHÔNG sweep >3 symbol/run; 1 symbol mỗi lần sweep.
- `condition_symbol` chết → cả call unavailable, nói rõ, KHÔNG thay symbol khác tự ý.

## Verdict (BẮT BUỘC)

- Baseline buy-hold → từng điều kiện (số trades/net/win) → best param + worst param → seasonality/event bias → kết luận "đáng tin / đáng nghi + lý do".
- BẮT BUỘC ghi rõ engine: numpy-only, cost mặc định, T+2 VN chưa model.
- `event_window` engine sâu và Elliott/Wyckoff full vẫn Phase 2 — GHI RÕ giới hạn, CẤM tuyên bố full.
- Provenance: nguồn nến (`vn_quote_history`/`dnse_ohlc_history`), benchmark (`vn_index_ohlcv`), ngày sự kiện (`event_calendar_vn`).

## Chống tràn lan

- Budget TỐI ĐA 12 calls; 1 symbol mỗi lần sweep; `param_sweep` cap 30 combos.
- Quy tắc dừng: đủ baseline + từng điều kiện được hỏi + best/worst → DỪNG; KHÔNG sweep thêm param ngoài yêu cầu.
- Months=[1] trên nến tháng 3 → 0 trades + warning là hợp lệ, KHÔNG retry đổi timeframe tự ý.

## Lỗi thường gặp

- `condition_symbol` chết → cả call unavailable, nói rõ, KHÔNG thay symbol khác tự ý.
- 0 trades (VD months=[1] trên nến tháng 3) → ghi warning, KHÔNG bịa kết quả; giải thích entries/exits.
- T+2 VN chưa model, cost mặc định — BẮT BUỘC caveat trong kết luận, CẤM tuyên bố lợi nhuận ròng thực tế.
- vnstock→yfinance fallback nằm trong tool, KHÔNG tự đổi nguồn tay.

## Bằng chứng live (02-10-2026)

VCB buy-hold −4.9% gross · sma_cross 7 trades −10.4% · sweep best **+3.7%** · seasonality tháng 1 mean +4.67% · rsi_meanrev VCB 1 trade · months=[1] trên nến tháng 3 → 0 trades + warning · event_study VCB 2026-09-21: CAR +0.25%.

## Nghiệm thu

- "Backtest mua RSI<30 FPT + backtest sau Tết" → bảng từng điều kiện (trades/net/win) + best/worst + kết luận, kèm caveat T+2/cost.
- Thiếu worst param hoặc thiếu caveat engine → CHƯA đạt.


---

## 14 · kiem-tra-nguon-du-lieu
> File thật: `OpenTrading/skills/kiem-tra-nguon-du-lieu/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: kiem-tra-nguon-du-lieu
description: Check nguồn, kiểm tra nguồn dữ liệu, server sống không, Vietstock chết chưa, data sáng nay có đủ không, health check trước phiên — quét toàn bộ upstream trong 1 lượt, bảng trạng thái từng nguồn + khuyến nghị skill nào chạy được. Dùng khi user hỏi nguồn sống không, check trước phiên, hoặc khi skills khác báo unavailable hàng loạt. Không dùng để phân tích thị trường (không verdict mua/bán).
when_to_use: "Server còn sống không, Vietstock chết chưa, sáng nay data có đủ không, check nguồn trước phiên, skills báo unavailable hàng loạt. Không dùng để phân tích thị trường."
activation: manual
requires_tools: [mcp__opentrading__doctor]
tool_budget: 12
triggers:
  keywords: [check nguồn, kiểm tra nguồn, server sống không, vietstock chết, data có đủ không, health check, nguồn dữ liệu]
version: 1.0.1
```

# Kiểm tra nguồn dữ liệu

Chạy định kỳ mỗi phiên hoặc khi skills khác báo unavailable hàng loạt.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi server còn sống không, Vietstock chết chưa, sáng nay có đủ data chạy dossier/backtest/kỹ thuật không, check nguồn trước phiên.
- Khi KHÔNG dùng: phân tích thị trường, verdict mua/bán (CHỈ dùng các skill phân tích); quét tin (CHỈ dùng skill tin tức).

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 | `doctor` | env keys + versions local. |
| 1 (song song 5) | `source_status` · `vs_auth_status` | Tổng quan upstream + hạn JWT. |
| 2 (smoke mỗi upstream, song song 5) | `vn_quote_history` (VCB, days=5) · `vs_market_index` · `dnse_latest_trade` (VN30F1M) · `yf_market_pins` · `crypto_spot` (BTCUSDT) | vnstock · Vietstock · DNSE · yfinance · Binance. Smoke dùng limit/days NHỎ NHẤT (limit=1, days=5) — mục đích là ping, CẤM lấy dữ liệu thật. |
| 3 (smoke tiếp, song song 4) | `news_market` (limit=1) · `fred_series` (DGS10, limit=1) · `world_prediction_odds` (limit=1) · `sbv_rates` | Fireant/GDELT · FRED · Gamma · SBV scrape. Smoke CHỈ limit=1, CẤM retry quá 1 lần/upstream. |

## Verdict (bảng BẮT BUỘC)

| Nguồn | Trạng thái | Độ trễ | Skills ảnh hưởng nếu chết |
|---|---|---|---|
| vnstock | ok/throttle/down | giây | kỹ thuật/cơ bản/so sánh/backtest... |
| Vietstock JWT | còn hạn tới.../HẾT | — | cơ bản/CTCK/macro (chuyển mirror/HAR) |
| Vietstock HAR-session | sống/chết | — | macro VN, CTKH |
| DNSE | ok/lạnh | — | intraday (WS trio cần worker) |
| yfinance/Binance/GDELT/Fireant/Gamma/FRED/SBV | ... | ... | ... |

+ 1 dòng khuyến nghị ("sáng nay đủ data chạy dossier/backtest/ky-thuat" hay "chỉ chạy legs không-Vietstock").

## Chống tràn lan

- Smoke dùng limit/days NHỎ NHẤT (limit=1, days=5) — mục đích là ping, không lấy dữ liệu; CẤM retry quá 1 lần/upstream.
- CẤM phân tích thị trường trong skill này; CHỈ báo trạng thái + khuyến nghị skill chạy được.

## Lỗi thường gặp

- Chính skill này cũng có thể partial (1–2 nguồn chết) — verdict vẫn ra đủ bảng, đánh dấu đỏ nguồn chết.
- Tài khoản Vietstock login Google → password fallback bị từ chối ("đăng nhập bằng Google!") — phải re-login Google + export HAR/cookie mới (sự cố 02-10-2026).

## Bằng chứng live (02-10-2026)

Sự cố JWT hết hạn 19:15 → skill này bắt được ở wave 1 (`vs_auth_status` false) trước khi skills khác fail hàng loạt; HAR-session sống độc lập (macro vẫn available khi JWT chết).

## Nghiệm thu

Chạy 1 lượt → bảng đủ 9 nguồn + khuyến nghị, ≤12 calls, ≤3 phút.


---

## 15 · ky-thuat-chuyen-sau
> File thật: `OpenTrading/skills/ky-thuat-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: ky-thuat-chuyen-sau
description: "kỹ thuật, RSI, MACD, Bollinger BB, Ichimoku, ADX, EMA, SMA, Elliott, Wyckoff, hỗ trợ kháng cự, breakout, pattern, orderbook, higher-high lower-low đa khung 1D/1W/1M 1 mã. Dùng khi user hỏi kỹ thuật đa khung, breakout, đọc băng, sóng Elliott, HH/LL (VCB kỹ thuật sao, FPT có breakout không). Không dùng khi: hỏi BCTC/cơ bản → co-ban-chuyen-sau; hỏi định giá fair value → dinh-gia-chuyen-sau."
when_to_use: "Hỏi kỹ thuật 1 mã đa khung (VCB kỹ thuật đa khung sao, FPT có breakout không, đọc băng HPG, higher-high hay lower-low, sóng Elliott/Wyckoff). Không dùng khi: hỏi cơ bản/BCTC (→ co-ban-chuyen-sau), hỏi định giá fair value/PER (→ dinh-gia-chuyen-sau), phân tích toàn diện 8 bước (→ phan-tich-chuyen-sau-1-ma)."
activation: auto
requires_tools: [mcp__opentrading__signals_technical]
tool_budget: 8
triggers:
  keywords: [kỹ thuật, rsi, macd, bb, bollinger, ichimoku, elliott, wyckoff, hỗ trợ, kháng cự, breakout, pattern, orderbook, băng giá, chỉ báo, adx, ema, sma, higher high, lower low, đa khung]
version: 1.1.1
```

# Kỹ thuật chuyên sâu 1 mã (đa khung)

Phân tích THUẦN kỹ thuật 1 mã đa khung (1D/1W/1M): RSI/MACD/BB/Ichimoku, Elliott/Wyckoff, hỗ trợ-kháng cự, higher-high hay lower-low.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi kỹ thuật 1 mã (`VCB kỹ thuật đa khung sao`, `FPT có breakout không`, `đọc băng HPG`, `higher-high hay lower-low`, `sóng Elliott`).
- Khi KHÔNG dùng:
  - Hỏi BCTC/cơ bản/M-Score → `co-ban-chuyen-sau`.
  - Hỏi định giá/fair value/PER/upside → `dinh-gia-chuyen-sau`.
  - Phân tích toàn diện 1 mã → `phan-tich-chuyen-sau-1-ma` (skill đó sẽ DISPATCH skill này).
  - So sánh nhiều mã → `so-sanh-cung-nganh`.

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Nến đa khung | `signals_technical` (symbol, interval=1D) · `signals_technical` (interval=1W) · [`signals_technical` (interval=1M) nếu hỏi dài hạn] | Mỗi khung 1 call: RSI/MACD/BB/Ichimoku/S-R/patterns. GỌI TRỰC TIẾP. |
| 2. Cấu trúc sóng | Đọc từ output Wave 1: swings + swing_trend + fib + elliott + wyckoff | KHÔNG gọi tool mới; tự dán nhãn HH/HL/LH/LL + Fibonacci 7 mức + Elliott (impulse/corrective/developing + invalidation) + Wyckoff phase. |
| 3. Xác nhận (chọn) | `pattern_match` (analogy lịch sử) · `dnse_latest_trade` / `dnse_orderbook` / `vn_trades` (intraday) · `vn_index_ohlcv` (trend index) | Tối đa 3 calls, CHỈ gọi theo câu hỏi. GỌI TRỰC TIẾP. |

CẤM gọi chồng chéo: CẤM gọi `financial_detail` / `valuation_run` / `stock_forensic` trong skill này (đó là việc của `co-ban-chuyen-sau` / `dinh-gia-chuyen-sau`). Wave 3 CẤM gọi quá 3 calls xác nhận.

## Verdict

Verdict cho MỖI khung (1D/1W[/1M]), mỗi mục ghi số + trend + provenance:

1. Trend: SMA stack + ADX (`provenance: signals_technical` khung đó).
2. Momentum: RSI/MACD/BB/Ichimoku (số cụ thể từng chỉ báo).
3. S-R của khung đó.
4. Cấu trúc: HH/HL/LH/LL + Fibo + Elliott pattern/invalidation + Wyckoff phase + confidence.
5. Kết luận khung: higher-high hay lower-low.
6. Tổng hợp: đồng thuận đa khung hay phân kỳ + trigger giá → timing MUA/CHỜ/BÁN.
7. Kết luận 1 câu chốt toàn mã.

Elliott/Wyckoff là heuristic → BẮT BUỘC ghi confidence + invalidation, CẤM diễn giải sóng chuẩn bằng lời suông.

## Chống tràn lan

- Budget ≤8 calls. Cap: CHỈ 1 mã; mặc định 2 khung (1D+1W), khung 1M CHỈ khi user hỏi dài hạn.
- `interval` CHỈ nhận 1D/1W/1M (1W ≥30 bars, 1M ≥24 bars); interval lạ → `unavailable`, CẤM retry.
- Quy tắc dừng: đủ 2 khung + HH/LL thì DỪNG nếu câu hỏi hẹp; CẤM mở Wave 3 khi user không hỏi intraday/analogy.

## Lỗi thường gặp

- Mã mới <60 nến → indicators null → báo `thiếu lịch sử`, CẤM bịa RSI/MACD.
- DNSE hết giờ → orderbook rỗng là đúng data, ghi rõ phiên đóng.
- `pattern_match` corr <0.4 = không có analogy đáng tin → ghi đúng, CẤM cố gán pattern.
- Giá theo kVND (`signals_technical.last 57.3` = 57,300đ) → BẮT BUỘC qui đổi + ghi đơn vị.
- Partial data: khung nào thiếu → verdict partial khung còn lại + ghi khung thiếu.

## Bằng chứng live (02-10-2026)

- VCB — RSI 39.2, ADX 12.1 (trend yếu), MACD −0.31/−0.13, EMA10 58.09, pos_52w 0.21 · HPG pattern best_corr 0.409 (yếu — ghi đúng) · VCB 1W bearish/lower-low/fib-down nhất quán.

## Nghiệm thu

- `FPT kỹ thuật 1D+1W` → verdict 2 khung + HH/LL + Ichimoku signal, ≤8 calls.


---

## 16 · nhip-dap-crypto
> File thật: `OpenTrading/skills/nhip-dap-crypto/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: nhip-dap-crypto
description: "BTC bitcoin, ETH ethereum, SOL, crypto tiền số tiền ảo, funding rate, fear greed — nhịp đập crypto bằng ngôn ngữ thường cho người ít chuyên, xu hướng gì, đòn bẩy có nóng không, liên thông gì tới VN. Dùng khi user hỏi BTC/ETH sao rồi, crypto lên hay xuống, có nên quan tâm crypto không. Không dùng khi: bối cảnh regime vĩ mô toàn cầu (dùng danh-gia-vi-mo-quoc-te), odds sự kiện crypto trên Polymarket (dùng du-doan-polymarket)."
when_to_use: "BTC/ETH sao rồi, crypto lên hay xuống, funding có nóng không, có nên quan tâm crypto không, giá quy VND bao nhiêu. Không dùng khi: bối cảnh regime toàn cầu (danh-gia-vi-mo-quoc-te), odds sự kiện crypto (du-doan-polymarket)."
activation: auto
requires_tools: [mcp__opentrading__crypto_spot]
tool_budget: 6
triggers:
  keywords: [btc, bitcoin, eth, ethereum, crypto, tiền số, tiền ảo, funding]
version: 1.1.1
```

# Nhịp đập crypto

Skill này viết cho người ít chuyên crypto: mọi thuật ngữ đều BẮT BUỘC giải thích 1 dòng kèm theo số.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi BTC/ETH/SOL sao rồi, crypto lên hay xuống, funding/OI nói gì, giá crypto quy ra VND, crypto có liên thông gì tới chứng khoán VN.
- Khi KHÔNG dùng: bối cảnh regime vĩ mô toàn cầu (CHỈ dùng `danh-gia-vi-mo-quoc-te`); odds xác suất sự kiện crypto (CHỈ dùng `du-doan-polymarket`); phân tích vàng/tỷ giá (CHỈ dùng `phan-tich-vang-ty-gia`).

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `crypto_spot` (BTC ETH SOL) | Giá + % 24h = "tăng/giảm bao nhiêu hôm nay". Tối đa 3 đồng/wave 1. |
| 2 | `crypto_derivs` (BTC ETH) | funding rate = "phe mua đang trả tiền cho phe bán (dương = đám đông cược lên)"; OI = "tổng tiền đang cược"; long/short = "bên nào đông hơn"; funding cao + OI cao = đòn bẩy nóng, dễ đảo chiều. |
| 3 | `world_fear_greed` · `vn_crypto_ohlv` (path quy VND) | Tham lam/Sợ hãi (0–100) + giá quy VND cho người VN. |

## Verdict (format BẮT BUỘC — 3 câu)

1. Xu hướng gì (lên/xuống/đi ngang + %) · 2. Đòn bẩy có nóng không (funding cao + OI cao = dễ đảo chiều) · 3. Liên thông gì tới VN (giá VND + chứng khoán còn lại — không có thì ghi "độc lập").

## Chống tràn lan + Cảnh báo BẮT BUỘC

- Binance có thể geo-block từ worker Singapore (funding rỗng = ghi chú, không phải thị trường chết).
- Crypto chạy 24/7 — số "hôm nay" khác phiên chứng khoán VN, đừng so lệch phiên.
- CHỈ drill Polymarket crypto khi user hỏi xác suất; không tự lan sang odds/event-study.

## Lỗi thường gặp

- funding/OI rỗng do geo-block → ghi "không lấy được do giới hạn vùng", CẤM kết luận thị trường chết.
- So % 24h crypto với % phiên HOSE → sai phiên; BẮT BUỘC ghi chú 24/7.
- Để jargon (funding, OI, long/short) không kèm giải thích 1 dòng + số → CẤM.

## Bằng chứng live (02-10-2026)

BTC 83,476 (+0.33%) · funding 2.8e-05 (trung tính) · OI 95.7k · fear/greed 70-74.

## Nghiệm thu

"BTC sao rồi" → 3 câu trả lời + 0 jargon không giải thích, ≤6 calls.


---

## 17 · phan-tich-chuyen-sau-1-ma
> File thật: `OpenTrading/skills/phan-tich-chuyen-sau-1-ma/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-chuyen-sau-1-ma
description: "phân tích cổ phiếu, phân tích mã, toàn diện 8 bước: mã-ngành-kỹ thuật-định giá-lợi nhuận quý-tin-sự kiện-tổng hợp tích cực/tiêu cực/động lực. Dùng khi user yêu cầu phân tích toàn diện 1 mã (phân tích FPT, VCB thế nào, mã này sao). Không dùng khi user chỉ hỏi 1 chiều: RSI/breakout/đa khung → ky-thuat-chuyen-sau; BCTC/M-Score/cổ đông → co-ban-chuyen-sau; fair value/PER/upside → dinh-gia-chuyen-sau; so 2-6 mã → so-sanh-cung-nganh."
when_to_use: "Người dùng yêu cầu phân tích toàn diện một mã (phân tích FPT, VCB thế nào, mã này sao). Không dùng khi: user chỉ hỏi 1 chiều (RSI/breakout → ky-thuat-chuyen-sau; BCTC/M-Score → co-ban-chuyen-sau; fair value/PER → dinh-gia-chuyen-sau); so sánh nhiều mã → so-sanh-cung-nganh; setup trước BCTC → danh-gia-truoc-bctc."
activation: auto
requires_tools: [mcp__opentrading__stock_overview]
tool_budget: 8
triggers:
  keywords: [phân tích, phân tích cổ phiếu, phân tích mã, toàn diện, chi tiết mã, mã này sao]
version: 1.1.1
```

# Phân tích chuyên sâu 1 mã

Skill điều phối toàn diện 1 mã theo 8 bước. Skill này TỰ LÀM nhận diện mã + ngành + tin + sự kiện, DISPATCH kỹ thuật/định giá sang sub-skill rồi gộp verdict.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user yêu cầu phân tích toàn diện 1 mã (`phân tích FPT`, `VCB thế nào`, `mã này sao`).
- Khi KHÔNG dùng:
  - Chỉ hỏi kỹ thuật (RSI, breakout, đa khung, higher-high/lower-low) → `ky-thuat-chuyen-sau`.
  - Chỉ hỏi BCTC/cơ bản (M-Score, cổ đông, cổ tức) → `co-ban-chuyen-sau`.
  - Chỉ hỏi định giá (fair value, PER, upside) → `dinh-gia-chuyen-sau`.
  - So sánh 2-6 mã cùng ngành → `so-sanh-cung-nganh`.
  - Đánh giá setup trước khi BCTC ra → `danh-gia-truoc-bctc`.

## Workflow

| Bước | Tools | Ghi chú |
|---|---|---|
| 1. Xác định mã | `symbol_lookup` (tên công ty) · `symbol_resolve` (mã đa loại, có fallback xếp hạng) | Chuẩn hóa mã CK (VCB, BID...). Mã nhập nhằng (vàng/BTC/USD) → BẮT BUỘC `symbol_resolve` trước. GỌI TRỰC TIẾP. |
| 2. Ngành + kiếm tiền nhờ đâu | `vn_company` · `vs_company_info` · `vs_industry_tree` | Lấy ngành GICS, mô hình kinh doanh, nguồn thu chính. GỌI TRỰC TIẾP. |
| 3. Trạng thái kỹ thuật | DISPATCH `ky-thuat-chuyen-sau` | Reuse nguyên sub-skill (S22). CẤM gọi trực tiếp `signals_technical` ở skill này — ai cần kỹ thuật thì đi qua sub-skill. |
| 4. Định giá | DISPATCH `dinh-gia-chuyen-sau` | Reuse nguyên sub-skill (S24). CẤM gọi trực tiếp `valuation_run` ở skill này. |
| 5. Lợi nhuận các quý gần đây | `financial_detail` (cross-ref S23, CHỈ lấy số nhanh KQKD 4 quý + so QoQ/YoY, biên) | GỌI TRỰC TIẾP nhưng CẤM đào sâu BCTC/M-Score/F-score (đó là việc của `co-ban-chuyen-sau`). |
| 6. Tin tức doanh nghiệp | `news_symbol` (cross-ref S26) · `company_events` | Tin + công bố. GỌI TRỰC TIẾP. |
| 7. Sự kiện tương lai | `event_calendar_vn` | Lịch 30–90 ngày (BCTC/ĐHĐCĐ/cổ tức). GỌI TRỰC TIẾP. |
| 8. Tổng hợp | `evidence_bundle` (khóa verdict) | Gộp 7 bước trên thành bảng Tích cực / Tiêu cực / Động lực tương lai. GỌI TRỰC TIẾP. |

CẤM gọi chồng chéo: CẤM gọi trực tiếp `signals_technical` / `valuation_run` / `stock_forensic` để thay thế Bước 3–4. Bước 5 CHỈ được dùng `financial_detail` lấy số nhanh, CẤM phân tích chất lượng lợi nhuận tại đây.

## Verdict

BẮT BUỘC đủ các mục, mỗi mục ghi số + trend + provenance (tool/sub-skill nào ra số đó):

1. Nhận định 1 câu (khuyến nghị/tone chính).
2. Ngành + cách kiếm tiền (2 dòng, từ Bước 2).
3. Kỹ thuật (ghi rõ `provenance: ky-thuat-chuyen-sau`, kèm khung 1D/1W).
4. Định giá (ghi rõ `provenance: dinh-gia-chuyen-sau`, kèm UPSIDE/DOWNSIDE % nếu có).
5. Lợi nhuận quý (số DT/LN 4 quý + trend QoQ/YoY + biên, từ `financial_detail` Bước 5).
6. Tin + sự kiện sắp tới (từ `news_symbol` / `company_events` / `event_calendar_vn`).
7. Bảng Tích cực / Tiêu cực / Động lực tương lai (3 cột, khóa bằng `evidence_bundle`).
8. Kết luận 1 câu chốt lại toàn mã.

## Chống tràn lan

- Budget 8 CHỈ đếm tool nhà của skill này; tool của sub-skill nằm trong budget của sub-skill, KHÔNG cộng dồn.
- Cap: CHỈ 1 mã/lần chạy. User hỏi 1 chiều (`RSI FPT`) → BẮT BUỘC trả lời bằng sub-skill tương ứng, CẤM chạy đủ 8 bước.
- Quy tắc dừng: đủ 8 bước hoặc đủ dữ liệu ra bảng 3 cột thì DỪNG, CẤM gọi thêm vòng tin/sự kiện thứ hai.
- Reuse legs: Bước 3–4 BẮT BUỘC reuse sub-skill, CẤM tự chạy lại tool của sub-skill.

## Lỗi thường gặp

- Sub-skill chết 1 chân (kỹ thuật hoặc định giá lỗi) → vẫn ra verdict với leg còn sống + ghi rõ leg thiếu, CẤM bù số/bịa số thay thế.
- Mã mới chưa phân loại ngành (`vs_industry_tree` không match) → ghi `chưa phân loại`, vẫn chạy các bước còn lại.
- `symbol_resolve` trả nhiều ứng viên → chọn hạng cao nhất + ghi rõ đã resolve từ tên nào sang mã nào; thiếu mã thì DỪNG và hỏi lại, CẤM đoán mã.

## Bằng chứng live

- Skill điều phối nên KHÔNG có số liệu live riêng; số liệu live nằm ở sub-skill `ky-thuat-chuyen-sau` và `dinh-gia-chuyen-sau` (giữ nguyên theo bản cũ, CẤM bịa số tại skill này).

## Nghiệm thu

- `Phân tích FPT` → đủ 8 bước, có bảng 3 cột tích cực/tiêu cực/động lực, ≤8 calls nhà (chưa tính calls trong sub-skill).


---

## 18 · phan-tich-sentiment
> File thật: `OpenTrading/skills/phan-tich-sentiment/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-sentiment
description: 'sentiment, dư luận, phố nói gì, crowd, FOMO, tâm lý nhà đầu tư, comment Fireant — Dùng khi cần đo dư luận/crowd về 1 mã trên Fireant kèm điểm, quotes và cảnh báo FOMO. Không dùng khi cần tin chính thống hoặc xác minh rumor (dùng tim-kiem-tin-tuc), fear/greed thị trường chung (dùng danh-gia-vi-mo-quoc-te, nhip-dap-crypto), khuyến nghị CTCK (dùng tim-co-hoi-bao-cao-ctck).'
when_to_use: 'Dùng khi user hỏi phố/crowd nói gì về 1 mã (VD: Phố nói gì về FPT, sentiment VCB, crowd có FOMO HPG không). Không dùng khi: cần tin chính thống/xác minh rumor (dùng tim-kiem-tin-tuc); hỏi fear/greed chung toàn thị trường (dùng danh-gia-vi-mo-quoc-te / nhip-dap-crypto); hỏi rating CTCK (dùng tim-co-hoi-bao-cao-ctck). Chỉ 1 symbol/run.'
activation: auto
requires_tools: [mcp__opentrading__sentiment_score]
tool_budget: 6
triggers:
  keywords: [sentiment, dư luận, phố nói gì, crowd, fomo, tâm lý nhà đầu tư, comment]
version: 1.0.1
```

# Phân tích sentiment

Đo *đám đông*, không đo *doanh nghiệp* — crowd có thể sai, sentiment KHÔNG bao giờ là leg duy nhất.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: hỏi dư luận/crowd/FOMO/comment về 1 mã cụ thể trên Fireant.
- Khi KHÔNG dùng: tin chính thống/rumor → `tim-kiem-tin-tuc`; fear/greed chung → `danh-gia-vi-mo-quoc-te` / `nhip-dap-crypto`; rating CTCK → `tim-co-hoi-bao-cao-ctck`.
- CẤM dùng sentiment làm leg duy nhất của quyết định; CẤM chuẩn hóa chéo 2 mode Groq/heuristic.

## Workflow

| Wave | Tools (giữ nguyên tool + params) | Ghi chú |
|---|---|---|
| 1 — SONG SONG | `news_symbol`(symbol, limit=20) · `sentiment_score`(symbol, limit=20) | Cùng nguồn Fireant; limit 20 đủ 90% mẫu |
| 2 — CHỈ khi mâu thuẫn, TUẦN TỰ | `company_events`(symbol) | Đối chiếu comment với công bố chính thức khi comment contradicts disclosures |

- 1 symbol/run; KHÔNG call lại với limit lớn hơn.
- `company_events` CHỈ khi comment mâu thuẫn công bố; KHÔNG dùng sentiment để "chốt luận" — chỉ confirm/deny.

## Verdict (BẮT BUỘC)

- **Điểm sentiment** (Groq hoặc heuristic — BẮT BUỘC ghi nhãn nguồn `Groq` / `heuristic`, heuristic thang khác, KHÔNG chuẩn hóa chéo).
- **3–5 trích comment tiêu biểu** (positive / negative / repeat-thuyết) + provenance Fireant.
- **Nhận diện FOMO/hoảng loạn** (tần suất symbol tag + likes); ngưỡng heuristic: <−0.3 hoảng loạn · >+0.3 FOMO · giữa = trung tính.
- **Cảnh báo vòng lặp** BẮT BUỘC: crowd có thể sai — sentiment KHÔNG được là leg duy nhất của quyết định.

## Chống tràn lan

- Budget TỐI ĐA 6 calls (thực tế ≤4); 1 symbol/run; limit 20, KHÔNG nới limit.
- Quy tắc dừng: đủ điểm + ≥3 quotes + nhãn nguồn → DỪNG; wave 2 chỉ khi có mâu thuẫn rõ ràng.

## Lỗi thường gặp

- Thiếu Groq → `score_heuristic` + warning "groq unavailable" → BẮT BUỘC nhãn `heuristic` trong verdict.
- Posts rỗng = mã ít bàn (empty hợp lệ), KHÔNG bịa quotes; ghi rõ "ít bàn luận".
- Fireant chết → fallback duy nhất: GDELT titles qua `tim-kiem-tin-tuc` (1 call), GHI RÕ nguồn thay thế.
- CẤM diễn giải heuristic thành "nên mua/bán".

## Bằng chứng live (02-10-2026)

FPT — 20 posts, heuristic **−0.25**, trong khi M −2.06 sạch (điển hình crowd≠fundamentals) · VCB posts lãi suất 0.1-6% · Groq key có trên prod, thiếu trên local dev.

## Nghiệm thu

- "Phố nói gì về FPT" → điểm + ≥3 quotes + nhãn nguồn Groq/heuristic, ≤4 calls.
- Thiếu nhãn nguồn hoặc thiếu cảnh báo vòng lặp → CHƯA đạt.

## Ghi chú review — dữ liệu CÓ ý nghĩa nếu đọc đúng

Sentiment đo *đám đông*, không đo *doanh nghiệp* (live: FPT heuristic −0.25 trong khi M −2.06 sạch). Ngưỡng diễn giải heuristic: <−0.3 hoảng loạn · >+0.3 FOMO · giữa = trung tính; KHÔNG chuẩn hóa chéo 2 mode Groq/heuristic; không bao giờ dùng sentiment làm leg duy nhất của quyết định.


---

## 19 · phan-tich-vang-ty-gia
> File thật: `OpenTrading/skills/phan-tich-vang-ty-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-vang-ty-gia
description: "Vàng SJC, vàng miếng, giá vàng, XAUUSD vàng thế giới, USDVND tỷ giá, premium vàng, chênh lệch SJC thế giới — phân tích giá TG + TA vàng + địa chính trị, lãi suất 2 đầu, dự đoán vàng VN. Dùng khi user hỏi vàng SJC đắt hơn thế giới bao nhiêu, tỷ giá có áp lực không, dự đoán vàng VN. Không dùng khi: lãi suất điều hành VN chung (dùng danh-gia-vi-mo-viet-nam), nhịp đập crypto (dùng nhip-dap-crypto)."
when_to_use: "Vàng SJC đắt hơn thế giới bao nhiêu, giá vàng hôm nay, tỷ giá USDVND áp lực không, dự đoán vàng VN theo TG hay ngược TG. Không dùng khi: lãi suất điều hành VN chung (danh-gia-vi-mo-viet-nam), crypto (nhip-dap-crypto)."
activation: auto
requires_tools: [mcp__opentrading__vn_retail_gold]
tool_budget: 10
triggers:
  keywords: [vàng sjc, vàng miếng, giá vàng, usdvnd, tỷ giá, premium vàng, vàng thế giới, xauusd, dự đoán vàng]
version: 1.1.1
```

# Phân tích vàng & tỷ giá

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi giá vàng SJC/vàng miếng, chênh lệch (premium) VN–TG, giá vàng thế giới + TA vàng, áp lực tỷ giá USDVND, dự đoán vàng VN, lãi suất 2 đầu SBV–Fed và hàm ý tỷ giá.
- Khi KHÔNG dùng: lãi suất điều hành VN chung (CHỈ dùng `danh-gia-vi-mo-viet-nam`); nhịp đập crypto (CHỈ dùng `nhip-dap-crypto`); TA mã chứng khoán VN (CHỈ dùng `ky-thuat-chuyen-sau`).

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Giá vàng quốc tế + TA vàng | `yf_commodities` (GC) · `vn_msn_fx_gold` | Giá XAUUSD + đọc trend/momentum trên nến daily (giá vs SMA20/50 + RSI ước từ series `yf_commodities`). CHỈ 1 call `yf_commodities` (đã gồm GC+DXY), CẤM tách tick riêng lẻ. |
| 2. Rủi ro địa chính trị + xung đột | cross-ref `danh-gia-tinh-hinh-xung-dot` / `bat-on-quoc-gia` | Yếu tố đẩy giá vàng (leo thang = vàng lên); không gọi lại nếu vừa chạy. |
| 3. So lệch VN–TG → dự đoán vàng VN | `vn_retail_gold` (SJC mua/bán) + giá TG wave 1 | Premium = (SJC mua vào − giá TG quy đổi) / giá TG; premium nở = vàng VN khó giảm theo TG. |
| 4. Lãi suất 2 đầu | `sbv_rates` · `fred_series` (DGS10) · `yf_yield_curve` | SBV (tái cấp vốn/chiết khấu) vs US (DGS10/curve) — chênh lệch hút vốn, hàm ý tỷ giá. |
| 5. Dự đoán + macro | `world_prediction_odds` (cross-ref `du-doan-fed`) · `macro_events_vn` | Odds Fed/căng thẳng + bối cảnh vĩ mô. |

## Verdict (format BẮT BUỘC)

Giá TG + TA 3 dòng · premium % + dự đoán vàng VN (theo TG / ngược TG khi premium nở) · lãi suất 2 đầu + hàm ý tỷ giá · kịch bản odds · KHÔNG point-forecast giá.

## Chống tràn lan + Cảnh báo BẮT BUỘC

- 1 call `yf_commodities` (đã gồm GC+DXY) thay vì tick riêng lẻ.
- TA vàng đọc từ series có sẵn; `signals_technical` CHỈ hỗ trợ mã VN — CẤM ép dùng cho GC=F.
- CẤM point-forecast giá cụ thể ("vàng sẽ lên X triệu"); CHỈ nêu premium + driver + kịch bản odds.

## Lỗi thường gặp

- Ép `signals_technical` cho GC=F → sai phạm vi tool; BẮT BUỘC đọc TA từ series `yf_commodities`.
- Quên quy đổi đơn vị khi tính premium (SJC VND/lượng vs XAUUSD USD/oz) → BẮT BUỘC ghi giả định quy đổi.
- Gọi lại xung đột/macro khi vừa chạy ở skill trước → tốn budget; CHỈ cross-ref.

## Bằng chứng live (02-10-2026)

VÀNG MIẾNG SJC 999.9 (BTMC live) · XAUUSD 4,195 · USDVND 25,970 (MSN) · SBV 4.5% tái cấp vốn · Fed giữ 74.5%.

## Nghiệm thu

"Vàng SJC hôm nay đắt hơn thế giới bao nhiêu" → số premium % + giả định + 2 driver, ≤10 calls.


---

## 20 · so-sanh-cung-nganh
> File thật: `OpenTrading/skills/so-sanh-cung-nganh/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: so-sanh-cung-nganh
description: "so sánh, vs, so với, cùng ngành, mạnh nhất, leader, hơn kém, xếp hạng 2-6 mã cùng ngành (VCB vs BID vs CTG, bank nào đáng mua). Dùng khi user hỏi so sánh/xếp hạng mã cùng ngành. Không dùng khi: chỉ 1 mã → phan-tich-chuyen-sau-1-ma; hỏi lẻ 1 chiều 1 mã (RSI → ky-thuat-chuyen-sau, BCTC → co-ban-chuyen-sau, fair value → dinh-gia-chuyen-sau)."
when_to_use: "So sánh 2-6 mã cùng ngành (VCB vs BID vs CTG, steel mạnh nhất là ai, ngân hàng nào đáng mua nhất). Không dùng khi: chỉ 1 mã (→ phan-tich-chuyen-sau-1-ma; hỏi lẻ 1 chiều → ky-thuat-chuyen-sau / co-ban-chuyen-sau / dinh-gia-chuyen-sau)."
activation: auto
requires_tools: [mcp__opentrading__compare_equities]
tool_budget: 8
triggers:
  keywords: [so sánh, vs, so với, cùng ngành, mạnh nhất, leader, hơn kém, xếp hạng mã]
version: 1.1.1
```

# So sánh cùng ngành (điều phối)

Skill điều phối thứ hai (cùng họ `phan-tich-chuyen-sau-1-ma`): xác định mã cùng ngành, gọi skill chuyên cho từng mã, gộp xếp hạng.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi so sánh/xếp hạng 2–6 mã cùng ngành (`VCB vs BID vs CTG`, `steel mạnh nhất là ai`, `ngân hàng nào đáng mua nhất`).
- Khi KHÔNG dùng:
  - Chỉ 1 mã → `phan-tich-chuyen-sau-1-ma`.
  - Hỏi lẻ 1 chiều 1 mã (RSI → `ky-thuat-chuyen-sau`; BCTC → `co-ban-chuyen-sau`; fair value → `dinh-gia-chuyen-sau`).

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 0. Xác định mã cùng ngành | `vn_reference` (industry) hoặc `vs_industry_tree` (tra GICS) → chọn ≤6 mã · `stock_screener` (filter ngành, pool hẹp) khi chỉ cho tên ngành | Cap TUYỆT ĐỐI 6 mã — trên 6 thì yêu cầu thu hẹp, CẤM tự mở rộng. GỌI TRỰC TIẾP. |
| 1. Bảng nhanh | `compare_equities` (≤4 mã/lần) + `peer_compare` (chia 4+2 khi 5–6 mã) · `vn_equity_quote_batch` (≤6 mã, 1 call) | Overview + momentum + bảng giá 1 shot. GỌI TRỰC TIẾP. |
| 2. Gọi skills trên từng mã | DISPATCH `ky-thuat-chuyen-sau` HOẶC `co-ban-chuyen-sau` HOẶC `dinh-gia-chuyen-sau` cho mỗi mã — theo câu hỏi, song song ≤4 | DISPATCH sub-skill, CẤM gọi trực tiếp `signals_technical` / `financial_detail` / `valuation_run` tại skill này. CẤM chạy cả 3 sub-skills cho cả 6 mã. |
| 3. Bối cảnh ngành | `vs_gics_index` (group) — index ngành làm nền | 1 call. GỌI TRỰC TIẾP. |

CẤM gọi chồng chéo: Wave 2 BẮT BUỘC đi qua sub-skill; CẤM gọi tool lõi của sub-skill trực tiếp ở đây. Mỗi mã CHỈ 1 sub-skill theo câu hỏi (hỏi momentum → kỹ thuật; hỏi chất lượng → cơ bản; hỏi đắt rẻ → định giá), CẤM chạy full 3 chiều/mã.

## Verdict

BẮT BUỘC đủ các mục, mỗi mục ghi số + provenance:

1. Bảng xếp hạng {mã · PE · ROE · momentum · RS · giá} (`provenance: compare_equities` / `peer_compare` / `vn_equity_quote_batch` + sub-skill Wave 2).
2. 1 dòng luận chọn: leader = chất lượng × momentum; định giá tốt = PE thấp trong nhóm ROE cao.
3. Cảnh báo tương quan nhóm khi chia tiền cả nhóm (cross-ref `correlation_matrix`, CHỈ tham chiếu).
4. Kết luận 1 câu: chọn mã nào + vì sao.

Thiếu dữ liệu 1 tiêu chí → xếp hạng partial + ghi `n/6 mã có đủ`, CẤM loại mã âm thầm, CẤM bịa số lấp bảng.

## Chống tràn lan

- Budget 8 CHỈ đếm tool nhà; calls của sub-skill tính vào budget sub-skill, KHÔNG cộng dồn vô hạn.
- Cap: TUYỆT ĐỐI ≤6 mã; Wave 2 song song ≤4; `compare_equities` ≤4 mã/lần (5–6 mã thì chia 4+2 với `peer_compare`).
- Quy tắc dừng: có bảng nhanh + xong 1 vòng sub-skill thì DỪNG, CẤM chạy vòng sub-skill thứ hai.
- Reuse legs: Wave 2 BẮT BUỘC reuse 3 sub-skill trên, CẤM tự phân tích kỹ thuật/cơ bản/định giá thủ công.

## Lỗi thường gặp

- Enrich throttle giờ cao điểm → ratios rỗng → verdict kỹ thuật-only + ghi chú thiếu, CẤM bịa PE/ROE.
- `vn_reference` industry không match → thử `vs_industry_tree` 1 lần, vẫn không ra → hỏi lại ngành, CẤM đoán mã.
- Partial data (1–2 mã thiếu) → giữ bảng partial, CẤM xóa mã thiếu khỏi bảng.

## Bằng chứng live (02-10-2026)

- compare_equities VCB-vs-HPG 2.8s · peer_compare cap 6 · vs_gics_index 3 nhóm live · quote_batch 1 request VN30 · HOSE universe 757 mã.

## Nghiệm thu

- `So sánh bank` → peer list ≤6 + sub-skill calls có giới hạn + bảng xếp hạng, ≤8 calls nhà.


---

## 21 · tim-co-hoi-bao-cao-ctck
> File thật: `OpenTrading/skills/tim-co-hoi-bao-cao-ctck/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tim-co-hoi-bao-cao-ctck
description: 'CTCK, khuyên mua, giá mục tiêu, target, báo cáo phân tích, khuyến nghị, rating, upside — Dùng khi săn cơ hội theo báo cáo phân tích CTCK kèm rating, giá mục tiêu và upside % đã kiểm chứng. Không dùng khi cần tin đồn/crowd (dùng phan-tich-sentiment, tim-kiem-tin-tuc), tự định giá nội tại (dùng dinh-gia-chuyen-sau).'
when_to_use: 'Dùng khi user hỏi CTCK khuyên mua gì, target mới cho mã nào, báo cáo VPS/SSI nói gì (VD: CTCK gần đây khuyên mua gì, có target mới cho MSN không). Không dùng khi: hỏi tin đồn/crowd/FOMO (dùng phan-tich-sentiment / tim-kiem-tin-tuc); hỏi tự định giá DCF/so sánh (dùng dinh-gia-chuyen-sau); hỏi backtest chiến lược (dùng kiem-chien-luoc-backtest).'
activation: auto
requires_tools: [mcp__opentrading__analyst_consensus]
tool_budget: 8
triggers:
  keywords: [ctck, khuyên mua, giá mục tiêu, target, báo cáo phân tích, khuyến nghị, rating]
version: 1.1.1
```

# Tìm cơ hội từ báo cáo CTCK

Khuyến nghị CTCK là INPUT, không phải chân lý — PHẢI kiểm chứng upside bằng giá hiện tại.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: hỏi rating/target/báo cáo CTCK theo feed chung hoặc theo mã cụ thể, cần bảng upside %.
- Khi KHÔNG dùng: rumor/crowd → `phan-tich-sentiment` / `tim-kiem-tin-tuc`; tự định giá → `dinh-gia-chuyen-sau`; backtest → `kiem-chien-luoc-backtest`.
- CẤM suy diễn khuyến nghị thành "nên mua"; CẤM bịa giá mục tiêu khi feed không có.

## Workflow

| Wave | Tools (giữ nguyên tool + params) | Ghi chú |
|---|---|---|
| 1 — feed chung | `analyst_consensus`(limit=30) | **Feed chung không symbol** — parse rating + giá mục tiêu từ titles; 1 call duy nhất |
| 1b — báo cáo vĩ mô, SONG SONG nếu cần | `analyst_consensus`(report_type=macro) | Lọc báo cáo vĩ mô CTCK (entry section/report); không có dated reports thì dùng số liệu gốc |
| 2 — mã cụ thể, TUẦN TỰ sau wave 1 | `analyst_consensus`(symbol, limit=15) · `vs_documents`(symbol) · `web_fetch`(format=pdf, URL báo cáo) | Report cho mã + tài liệu gốc + **đọc nội dung PDF** (stdlib-only, scan báo trung thực; cap 10 trang/20k ký tự) |
| 3 — xác nhận, TUẦN TỰ | `stock_overview`(mã target) 1–2 call | So giá hiện tại vs mục tiêu → upside % |

- Hỏi "HPG" mà `analyst_consensus`(symbol=HPG) empty → đọc feed chung và lọc title chứa HPG (title-scrape filter có thể sót), KHÔNG retry đổi limit.
- `vs_documents` chỉ lấy 1 mã đáng giá nhất; leg 3 chỉ kiểm chứng 1–2 mã nổi bật nhất, KHÔNG kiểm chứng tất cả.

## Verdict (BẮT BUỘC)

- Bảng {mã · CTCK · rating · giá mục tiêu · ngày · upside % so giá hiện tại}, lọc trong `days` (default 7).
- Top 3 cơ hội (upside lớn + rating MUA + còn hiệu lực).
- Cột **"đã kiểm chứng"** BẮT BUỘC = leg 3 chạy cho 1–2 mã nổi bật nhất (có `stock_overview`); mã chưa kiểm chứng ghi rõ "chưa kiểm chứng giá hiện tại".
- Disclaimer BẮT BUỘC: khuyến nghị CTCK là INPUT, không phải chân lý — không suy diễn thành "nên mua".
- Provenance: nguồn ngày từ URL/title; nếu `source/date null` (đặc trưng parse titles) → suy ngày từ URL/title + GHI RÕ nguồn ngày "không chắc chắn".

## Chống tràn lan

- Budget TỐI ĐA 8 calls; feed chung 1 call (symbol-less feed CÓ dữ liệu).
- Cap PDF: 10 trang/20k ký tự; `vs_documents` 1 mã; `stock_overview` 1–2 call.
- Quy tắc dừng: đủ bảng ≥5 dòng + kiểm chứng 2 mã top → DỪNG; KHÔNG đào thêm mã ngoài top.

## Lỗi thường gặp

- `source/date null` trong reports (đặc trưng parse titles) → suy ngày từ URL/title, ghi chú nguồn ngày "không chắc chắn", CẤM bịa ngày chính xác.
- Feed rỗng thật (cuối tuần) → empty hợp lệ, nới `days` 1 lần duy nhất rồi kết luận; KHÔNG retry vô hạn.
- Filter symbol empty (VD symbol=VCB/FPT từng empty đúng hiện tượng) → fallback đọc feed chung lọc title, KHÔNG đổi limit retry.

## Bằng chứng live (02-10-2026)

Feed chung **7 reports** — MBB MUA 28,200 · **MSN MUA 89,200 (30/09)** · VPB KHẢ QUAN 30,500 · MSB GIẢM TỶ TRỌNG 13,200 · FRT THEO DÕI 157,000 · filter symbol=VCB/FPT từng empty đúng hiện tượng.

## Nghiệm thu

- "CTCK khuyên mua gì tuần này" → bảng ≥5 dòng có upside %, kiểm chứng 2 mã top, ≤8 calls.
- Thiếu cột "đã kiểm chứng" hoặc thiếu disclaimer → CHƯA đạt; bịa target khi feed rỗng → CHƯA đạt.


---

## 22 · tim-kiem-tin-tuc
> File thật: `OpenTrading/skills/tim-kiem-tin-tuc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tim-kiem-tin-tuc
description: 'tin, tin đồn, rumor, nghe đồn, có thật không, tin về mã, dư luận về cổ phiếu — Dùng khi tìm tin theo từ khóa/mã/phạm vi VN/toàn cầu KỂ CẢ rumor, săn web + comments và đối chiếu công bố. Không dùng khi cần digest tin nóng mặc định trong ngày (dùng tin-tuc-nong-viet-nam, tin-tuc-nong-quoc-te), sentiment crowd thuần túy (dùng phan-tich-sentiment), khuyến nghị CTCK (dùng tim-co-hoi-bao-cao-ctck).'
when_to_use: 'Dùng khi user nêu mã/từ khóa cụ thể (VD: Tin về FPT, nghe đồn HPG..., tin dầu thế giới, dư luận về VCB) hoặc muốn xác minh tin đồn có thật không. Không dùng khi: user chỉ hỏi digest tin nóng mặc định trong ngày mà không nêu mã (dùng tin-tuc-nong-viet-nam / tin-tuc-nong-quoc-te); hỏi crowd FOMO thuần túy không cần tin (dùng phan-tich-sentiment); hỏi rating/giá mục tiêu CTCK (dùng tim-co-hoi-bao-cao-ctck).'
activation: auto
requires_tools: [mcp__opentrading__news_symbol]
tool_budget: 10
triggers:
  keywords: [tin về, tìm tin, tin tức về, news về, tin trên, dư luận về, nghe đồn, tin đồn, có thật không]
version: 1.1.1
```

# Tìm kiếm tin tức (kể cả rumor)

Rumor có TRƯỚC tin chính thống — skill này săn cả hai, nhưng PHẢI phân loại rõ ràng chính thống vs CHƯA XÁC NHẬN.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user nêu mã/từ khóa/phạm vi cụ thể, muốn săn tin + rumor + dư luận, muốn xác minh tin đồn, muốn phân tích chi tiết 1 tin.
- Khi KHÔNG dùng: digest mặc định không từ khóa → `tin-tuc-nong-viet-nam` / `tin-tuc-nong-quoc-te`; chỉ hỏi crowd/FOMO → `phan-tich-sentiment`; chỉ hỏi rating/target CTCK → `tim-co-hoi-bao-cao-ctck`; chỉ hỏi backtest chiến lược → `kiem-chien-luoc-backtest`.
- CẤM suy diễn rumor thành sự thật; CẤM bỏ nhãn độ tin.

## Workflow

| Chế độ | Wave | Tools (giữ nguyên tool + params) |
|---|---|---|
| **A. Theo mã (+ rumor)** | 1 | `news_symbol`(symbol, limit=20) — Fireant-first, TUẦN TỰ trước wave 2 |
| | 2. Săn web + comments — SONG SONG | `web_search`("tên mã" + "đồn"/"tin đồn"/rumor) → `web_fetch` 1–2 URL đáng ngờ nhất · `fireant_thread`(post_id từ wave 1 — rumor nằm ở replies) |
| | 3. Đối chiếu — TUẦN TỰ sau wave 1-2 | `corporate_calendar`(symbol) + `company_events`(symbol) — tin có khớp công bố không? |
| | 4. Dư luận | `sentiment_score`(symbol) |
| **B. VN** | 1 — SONG SONG | `news_market`(limit=15) + `corporate_calendar`(limit=20) |
| | 2 — TUẦN TỰ | `news_symbol` × 2–3 mã nổi bật + `web_search` tin nóng nhất để xác minh chéo |
| **C. Toàn cầu** | 1 — SONG SONG | `news_market`(sources=gdelt, limit=10) |
| | 2 — SONG SONG | `geo_intel`(topic) / `event_stats`(query) + `web_search`(từ khóa EN) |

- Mode A dừng khi đã ≥5 tin đạt chuẩn; `web_search` TỐI ĐA 2 query/mode; KHÔNG fetch quá 2 URL.
- GDELT rỗng → THỬ từ khóa English 1 lần rồi kết luận "ít coverage ngôn ngữ đó".

## Verdict (BẮT BUỘC 4 cột mỗi tin)

| Tiêu đề | Tuổi tin | Độ tin cậy + provenance | Triển vọng |
|---|---|---|---|
- **Tiêu đề** đầy đủ, có mã liên quan.
- **Tuổi tin** (mấy giờ/ngày trước — tin cũ >3 ngày với bluechip coi như đã phản ánh giá).
- **Độ tin cậy** (chính thống / CTCK / Fireant-crowd / ẩn danh-nguồn mở) + provenance (`news_symbol`/`news_market`/Fireant/GDELT/web).
- **Triển vọng** (tác động tới DN: doanh thu/lợi nhuận/giá — hay chỉ là noise).
- Tin đồn → BẮT BUỘC nhãn `CHƯA XÁC NHẬN` + điều kiện xác nhận (chờ công bố nào, ngày nào).

Phân tích chi tiết tin quan trọng nhất: Ai nói → nói gì → bằng chứng kèm theo → tác động định lượng được không (VD cổ tức bao nhiêu đồng, thương vụ bao nhiêu tỷ) → kịch bản nếu đúng/sai.

## Chống tràn lan

- Budget TỐI ĐA 10 calls; mode A dừng khi ≥5 tin đạt chuẩn.
- Cap: `web_search` tối đa 2 query/mode; `web_fetch` tối đa 2 URL; KHÔNG đào thêm mã ngoài 2–3 mã/mode B.
- Quy tắc dừng: đủ verdict 4 cột cho 5 tin → DỪNG, không săn thêm cho "chắc ăn".

## Lỗi thường gặp

- `web_search` ẩn khi thiếu key → chỉ dùng Fireant+GDELT + GHI RÕ "chưa quét web".
- Fireant posts giờ CÓ id thật (parser postID, P17) — dùng `fireant_thread` đọc replies; KHÔNG bịa post_id.
- Cả 2 nguồn news chết → `snapshot_history`(kind=news_feed) đọc cache, BẮT BUỘC GHI RÕ "cache <ngày>".
- GDELT rỗng → thử EN 1 lần, KHÔNG retry vô hạn.

## Bằng chứng live (02-10-2026)

`news_symbol("VCB")` → lãi suất VCB 0.1-6% posts · GDELT "dầu" live · corporate VCB 487 docs · `fireant_thread`(post PNJ 42088453) → root + 2 replies thật.

## Nghiệm thu

- "Nghe đồn HPG ... thật không" → verdict 4 cột + phân tích chi tiết + nhãn xác nhận, ≤10 calls.
- Thiếu 1 trong 4 cột verdict → CHƯA đạt; thiếu nhãn `CHƯA XÁC NHẬN` cho rumor → CHƯA đạt.


---

## 23 · tin-tuc-nong-quoc-te
> File thật: `OpenTrading/skills/tin-tuc-nong-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tin-tuc-nong-quoc-te
description: 'tin quốc tế, tin thế giới, thị trường Mỹ, Fed, Wall Street, Nasdaq, Trung Quốc — Dùng khi cần digest tin thế giới tác động thị trường kèm market reaction xác nhận bằng số. Không dùng khi hỏi tin VN (dùng tin-tuc-nong-viet-nam), tìm tin theo từ khóa riêng hoặc rumor (dùng tim-kiem-tin-tuc chế độ C), phân tích vĩ mô chuyên sâu (dùng danh-gia-vi-mo-quoc-te).'
when_to_use: 'Dùng khi user hỏi tin quốc tế/Mỹ/Trung hôm nay, Fed, Wall Street, Nasdaq. Không dùng khi: hỏi tin VN/VN30 (dùng tin-tuc-nong-viet-nam); đã có từ khóa/mã riêng cần săn sâu hoặc rumor (dùng tim-kiem-tin-tuc chế độ C); chỉ cần fear/greed hoặc mega-cap flows không cần tin (hỏi trực tiếp tool, không cần skill).'
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 8
triggers:
  keywords: [tin quốc tế, tin thế giới, thị trường mỹ, fed tin, wall street, nasdaq]
version: 1.0.1
```

# Tin nóng quốc tế

Tin thế giới + market reaction xác nhận bằng SỐ — không đưa tin suông.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: tin quốc tế/Mỹ/Trung, Fed, Wall Street, cần headline + số liệu thị trường xác nhận.
- Khi KHÔNG dùng: tin VN → `tin-tuc-nong-viet-nam`; từ khóa riêng/rumor → `tim-kiem-tin-tuc` chế độ C; vĩ mô chuyên sâu (curve, flows, fear/greed riêng lẻ) → `danh-gia-vi-mo-quoc-te`; crypto → `nhip-dap-crypto`.
- CẤM đưa headline quốc tế mà không có mục reaction hoặc không ghi rõ "thị trường chưa phản ánh".

## Workflow

| Wave | Tools (giữ nguyên tool + params) | Cách chạy |
|---|---|---|
| 1 | `news_market`(sources=gdelt) · `geo_intel`(không topic = global coverage) | SONG SONG |
| 2 | `yf_mega_flows` · `world_fear_greed` | SONG SONG, TUẦN TỰ sau wave 1 để soi reaction đúng tin |
| 3 | `event_stats`(từ khóa tin nổi bật nhất) | TUẦN TỰ, chỉ cho 1 tin nổi bật nhất |

- Wave 3 CHỈ chạy cho 1 từ khóa nổi bật nhất, KHÔNG chạy cho mọi headline.
- GDELT rỗng → thử từ khóa English 1 lần rồi kết luận "ít coverage".

## Verdict (BẮT BUỘC)

- 5 headline, mỗi tin: **tiêu đề + tuổi tin + provenance** (GDELT/`geo_intel`) + **market reaction bằng SỐ** (mega-cap flows, fear/greed, curve nếu liên quan rates).
- Tin chưa có reaction → BẮT BUỘC ghi "thị trường chưa phản ánh", CẤM bịa reaction.
- Tin đồn quốc tế → BẮT BUỘC nhãn `CHƯA XÁC NHẬN`.

## Chống tràn lan

- Budget TỐI ĐA 8 calls; `event_stats` TỐI ĐA 1 từ khóa; KHÔNG drill-down quá 1 tin.
- Quy tắc dừng: đủ 5 headline + ≥2 mục reaction định lượng → DỪNG.

## Lỗi thường gặp

- GDELT rỗng → thử EN 1 lần, KHÔNG retry vô hạn; kết luận "ít coverage ngôn ngữ đó".
- `geo_intel` không topic = global coverage; KHÔNG tự thêm topic hẹp nếu user hỏi chung.
- Cả 2 nguồn news chết → `snapshot_history`(kind=news_feed) cache, BẮT BUỘC GHI RÕ "cache <ngày>".
- Feed rỗng cuối tuần → empty hợp lệ, ghi rõ phiên nghỉ.

## Bằng chứng live (02-10-2026)

mega_flows AAPL/MSFT/NVDA OK · fear/greed 70-74 Greed 7 ngày.

## Nghiệm thu

- "Tin thế giới" → ≥5 headline + ≥2 mục reaction định lượng, ≤8 calls.
- Thiếu reaction số mà không ghi "thị trường chưa phản ánh" → CHƯA đạt.

## Ghi chú review

Như tin-tuc-nong-viet-nam — không kế thừa gì từ 8010 (đã retire).


---

## 24 · tin-tuc-nong-viet-nam
> File thật: `OpenTrading/skills/tin-tuc-nong-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tin-tuc-nong-viet-nam
description: 'tin nóng, tin chứng khoán hôm nay, tin VN, headline VN30, tin doanh nghiệp Việt Nam — Dùng khi cần digest tin nóng trong ngày về thị trường/doanh nghiệp VN kèm phân loại và sentiment. Không dùng khi tìm tin theo mã/từ khóa cụ thể hoặc xác minh tin đồn (dùng tim-kiem-tin-tuc), tin thế giới (dùng tin-tuc-nong-quoc-te), sentiment crowd chuyên sâu (dùng phan-tich-sentiment).'
when_to_use: 'Dùng khi user hỏi chung về tin VN hôm nay (VD: Tin chứng khoán hôm nay, có tin gì về VN30, headline doanh nghiệp). Không dùng khi: user nêu mã/từ khóa cụ thể hoặc rumor cần xác minh (dùng tim-kiem-tin-tuc); hỏi tin Mỹ/Trung/toàn cầu (dùng tin-tuc-nong-quoc-te); hỏi crowd FOMO thuần (dùng phan-tich-sentiment); hỏi khuyến nghị CTCK (dùng tim-co-hoi-bao-cao-ctck).'
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 9
triggers:
  keywords: [tin nóng, tin chứng khoán, tin hôm nay, tin vn, tin doanh nghiệp, headline]
version: 1.0.1
```

# Tin nóng Việt Nam

Digest nhanh tin VN trong ngày — headline + phân loại + sentiment, có provenance rõ ràng.

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: hỏi tin nóng VN hôm nay, VN30, thị trường/doanh nghiệp VN, cần 5–7 headline nhanh.
- Khi KHÔNG dùng: có mã/từ khóa cụ thể hoặc rumor → `tim-kiem-tin-tuc`; tin Mỹ/Trung/toàn cầu → `tin-tuc-nong-quoc-te`; đào sâu crowd/FOMO 1 mã → `phan-tich-sentiment`; rating/target CTCK → `tim-co-hoi-bao-cao-ctck`.
- CẤM suy diễn sentiment heuristic thành khuyến nghị mua/bán.

## Workflow

| Wave | Tools (giữ nguyên tool + params) | Cách chạy |
|---|---|---|
| 1 | `news_market`(limit=15) · `corporate_calendar`(limit=20) | SONG SONG |
| 2 | `news_symbol` × 2–3 mã xuất hiện nhiều nhất trong tin | TUẦN TỰ sau wave 1, chọn theo tần suất xuất hiện, KHÔNG theo cảm tính |
| 3 | `sentiment_score`(mã nóng nhất) · `company_events`(mã đó) | SONG SONG |

- TỐI ĐA 3 mã đào thêm ở wave 2.
- `sentiment_score` heuristic fallback (thiếu Groq) → BẮT BUỘC ghi nhãn "heuristic".

## Verdict (BẮT BUỘC mỗi headline)

- 5–7 headline, mỗi tin gồm: **tiêu đề + mã liên quan + phân loại** (catalyst / đồn đoán / tin vĩ mô) + **sentiment** nếu đủ dữ kiện + **provenance** (Fireant/GDELT) + **tuổi tin**.
- Sentiment heuristic → BẮT BUỘC nhãn `heuristic`; KHÔNG diễn giải thành "nên mua/bán".
- Tin đồn → BẮT BUỘC nhãn `CHƯA XÁC NHẬN`.

## Chống tràn lan

- Budget TỐI ĐA 9 calls; wave 2 TỐI ĐA 3 mã; KHÔNG call lại `sentiment_score` với limit lớn hơn.
- Quy tắc dừng: đủ 5 headline có provenance → DỪNG; đủ verdict wave 3 cho mã nóng nhất → DỪNG.
- `company_events` chỉ để đối chiếu, KHÔNG đào toàn bộ lịch sử.

## Lỗi thường gặp

- Fireant chết → tự GDELT fallback (trong tool); KHÔNG retry Fireant vô hạn.
- Cả hai chết → `snapshot_history`(kind=news_feed) đọc cache 1 ngày, BẮT BUỘC GHI RÕ là cache + ngày cache.
- Feed rỗng cuối tuần/nghỉ lễ → empty là hợp lệ, KHÔNG bịa tin; ghi rõ "phiên nghỉ, ít tin mới".
- Thiếu Groq → dùng heuristic + warning, BẮT BUỘC nhãn `heuristic` trong verdict.

## Bằng chứng live (02-10-2026)

Fireant posts 02-10 (quỹ bình ổn xăng dầu về KBNN; đất nền HN đổi tâm lý; chiến dịch làm sạch mã số thuế) · `news_symbol("VCB")` → posts lãi suất 0.1-6%.

## Nghiệm thu

- "Tin nóng hôm nay" → ≥5 headline có provenance, ≤9 calls.
- Thiếu provenance hoặc thiếu phân loại → CHƯA đạt; sentiment không nhãn nguồn → CHƯA đạt.

## Ghi chú review

KHÔNG liên quan server 8010 cũ — 8010 đã retire, nguồn tin là Fireant→GDELT hoàn toàn mới.


---

## 25 · ve-bieu-do-ky-thuat
> File thật: `OpenTrading/skills/ve-bieu-do-ky-thuat/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: ve-bieu-do-ky-thuat
description: "Vẽ chart, vẽ nến VCB, chart HPG, đường giá, sparkline, biểu đồ, đồ thị, so sánh mã, bar ngành, gauge fear greed, heatmap tương quan, donut tỷ trọng, histogram, winloss, depth — vẽ biểu đồ nến/đường/bar/gauge/heatmap/compare ngay trong TUI khi user xin xem chart. Dùng khi user nói vẽ, chart, nến, candlestick, so sánh, tương quan, tỷ trọng. Không dùng khi: phân tích chữ (dùng ky-thuat-chuyen-sau), định giá (dùng dinh-gia-chuyen-sau)."
when_to_use: "Vẽ nến VCB, chart HPG, so sánh mã, bar ngành, gauge fear/greed, heatmap tương quan, donut tỷ trọng, histogram CARs. Không dùng khi: phân tích chữ (ky-thuat-chuyen-sau), định giá (dinh-gia-chuyen-sau)."
activation: auto
requires_tools: [chart_render]
triggers:
  keywords: [vẽ, chart, nến, candlestick, đường giá, sparkline, biểu đồ, đồ thị, so sánh, bar, gauge, heatmap, donut, histogram, fear, greed, tương quan, tỷ trọng]
tool_budget: 8
version: 1.1.1
```

# Vẽ biểu đồ kỹ thuật trong TUI

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user nói vẽ, chart, nến, candlestick, đường giá, sparkline, so sánh 2–5 mã, bar ngành/top tăng giảm, gauge fear/greed, heatmap tương quan, donut tỷ trọng, histogram phân phối, depth orderbook.
- Khi KHÔNG dùng: phân tích chữ thuần (CHỈ dùng `ky-thuat-chuyen-sau`); định giá chi tiết (CHỈ dùng `dinh-gia-chuyen-sau`).

## Bảng tra data → kind (GIỮ NGUYÊN tool + params)

| Dữ liệu (tool) | `chart_render` kind |
|---|---|
| Nến OHLC: `vn_equity_ohlcv`, `market_candles_batch`, `dnse_ohlc_history` | `candlestick` (bars ≥5) |
| Chuỗi giá/macro: `vn_quote_history`, `fred_series`, `vs_indicator_data`, `yf_alloc_history` | `line` / `sparkline` / `area` |
| So 2–5 mã/tài sản: `compare_assets`, `compare_equities`, `vn_equity_quote_batch` | `chart_compare` (tool riêng, legend + % từ điểm đầu) |
| Top tăng/giảm, ngành, per/pb, odds, KH năm: `market_movers`, `sector_performance`, `valuation_run`, `world_prediction_odds`, `planned_targets` | `bar` (series + labels; xanh khi ≥0, đỏ khi <0) |
| Phân phối: `event_study` CARs, `pattern_match` corrs | `histogram` |
| Ma trận: `correlation_matrix`, `compare_assets`, `vs_industry_heatmap` | `heatmap` (matrix + labels rows+cols) |
| 1 số: `world_fear_greed`, `sentiment_score`, `quant_risk` | `gauge` (value+max) |
| Tỷ trọng: `portfolio_optimize`, `holders`, `breadth_scan` | `donut` (value+max) |
| Thắng/thua: `money_flow`, `vs_nn_flow` sign | `winloss` |
| Orderbook: `dnse_orderbook` | `chart_depth` |

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Lấy dữ liệu | tool dữ liệu theo bảng trên | Thiếu → báo trung thực, CẤM vẽ chay. Dùng lại dữ liệu đã có trong context, CẤM fetch lại. |
| 2. Vẽ | `chart_render` (+symbol) hoặc `chart_compare` | Màu ANSI tự theo chiều (tăng xanh/giảm đỏ); `color=never` khi user copy text thuần. Rộng mặc định 64 ký tự (CẤM vượt 100 để khỏi vỡ wrap TUI); cao nến 14, line 10, compact 1–8. |
| 3. Verdict | đọc từ hình + số | Trend, HH/LL, vị trí giá vs range; 2–3 câu, ghi đơn vị kVND. |

## Chống tràn lan + Cảnh báo BẮT BUỘC

- Ngưỡng tối thiểu: candlestick ≥5 nến; line/sparkline/area/winloss ≥2 điểm; histogram ≥5 điểm; heatmap matrix phi rỗng; gauge/donut cần value+max. Chưa đủ → CẤM vẽ, báo thiếu data.
- Chart dài tự collapse sau 3 dòng (ctrl+o mở rộng) — CẤM tóm tắt hình bằng lời dài.
- CẤM fetch khi đã có dữ liệu trong context (dùng lại).

## Lỗi thường gặp

- Ngoài giờ DNSE → orderbook rỗng thì `chart_depth` báo rỗng đúng, không retry.
- Giá theo kVND (`57.3` = 57,300đ) — BẮT BUỘC ghi đơn vị khi verdict.
- Vượt rộng 100 ký tự → vỡ wrap TUI; BẮT BUỘC giữ 64 mặc định.

## Verdict

Đọc từ hình + số: trend, HH/LL, vị trí giá vs range. 2–3 câu, ghi đơn vị kVND. Chart dài tự collapse — CẤM tóm tắt hình bằng lời dài.

## Lưu ý

Skill thuần hiển thị, không có số live cố định — số liệu lấy từ tool dữ liệu mỗi lần gọi; CẤM bịa số minh họa thành số thật.

## Nghiệm thu

"vẽ nến VCB 30 phiên" → 1 call data + 1 call `chart_render` + hình nến màu + verdict ≤3 câu, ≤8 calls.


---

## 26 · vn-market-basics
> File thật: `OpenTrading/skills/vn-market-basics/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: vn-market-basics
description: "Biên độ, bước giá, lô chẵn lô lẻ, ATO ATC, loại lệnh LO MP, phiên giao dịch, thanh toán T+2, sàn HOSE HNX UPCoM — kiến thức nền về cơ chế giao dịch chứng khoán Việt Nam. Dùng khi user hỏi sàn, phiên ATO/liên tục/ATC, biên độ, bước giá, lô, chu kỳ thanh toán, loại lệnh. Không dùng khi: giải thích chỉ số tài chính P/E ROE margin (dùng explain-term), phản biện mã đang giữ (dùng devil-advocate)."
when_to_use: Câu hỏi về sàn HOSE/HNX/UPCoM, phiên ATO/liên tục/ATC, biên độ, bước giá, lô giao dịch, chu kỳ thanh toán, loại lệnh. Không dùng để phân tích mã hay giải thích chỉ số tài chính.
activation: auto
triggers:
  keywords: [biên độ, bước giá, lô chẵn, lô lẻ, ATO, ATC, loại lệnh, thanh toán T, phiên giao dịch]
version: 1.1.1
```

# Cơ chế thị trường VN

## Khi nào dùng / Khi KHÔNG dùng

- Dùng khi: user hỏi sàn HOSE/HNX/UPCoM, phiên ATO/liên tục/ATC, biên độ giá, bước giá, lô chẵn/lẻ, chu kỳ thanh toán, loại lệnh (LO, MP, ATO, ATC...).
- Khi KHÔNG dùng: hỏi P/E, EPS, ROE, margin là gì (CHỈ dùng `explain-term`); hỏi mã đang nắm có nên giữ không (CHỈ dùng `devil-advocate`); xin giá/chỉ số hiện tại (CHỈ dùng skill phân tích).

## Workflow

| Bước | Việc làm | Ghi chú |
|---|---|---|
| 1 | Xác định sàn liên quan | Phân biệt rõ HOSE/HNX/UPCoM khi quy định khác nhau; CẤM gộp chung. |
| 2 | Trả lời theo quy tắc KRX hiện hành | Quy định thay đổi theo thời gian (hệ thống KRX, lộ trình CCP, nâng hạng FTSE); BẮT BUỘC ghi "theo hiểu biết của model, có thể đã cũ". |
| 3 | Khuyên đối chiếu nguồn chính thức | BẮT BUỘC khuyên user đối chiếu thông báo của sở giao dịch hoặc CTCK. |

## Verdict (format BẮT BUỘC)

Trả lời gọn theo từng sàn (nếu khác nhau) · ghi chú KRX/CCP/nâng hạng có thể đã cũ · 1 dòng khuyên đối chiếu nguồn chính thức.

## Chống tràn lan + Cảnh báo BẮT BUỘC

- Quy định thị trường thay đổi theo thời gian (hệ thống KRX, lộ trình CCP, nâng hạng FTSE) — BẮT BUỘC nói rõ thông tin có thể đã cũ.
- CẤM đưa ra con số giá hay chỉ số thị trường hiện tại trong skill này.
- Phân biệt rõ quy định giữa các sàn khi chúng khác nhau.

## Lỗi thường gặp

- Gộp biên độ/bước giá/lô cả 3 sàn thành 1 số → sai; BẮT BUỘC tách HOSE/HNX/UPCoM.
- Nói chắc chắn về quy định KRX/CCP mới mà không ghi chú "có thể đã cũ" → CẤM.
- Tiện trả lời kèm giá hiện tại → CẤM; CHỈ cơ chế, không số thị trường.

## Lưu ý

Skill nền kiến thức, không gọi tool dữ liệu, không có số live cố định — CẤM bịa giá/chỉ số; mọi thay đổi KRX/CCP/FTSE phải kèm cảnh báo đối chiếu nguồn chính thức.

## Nghiệm thu

"Biên độ HOSE bao nhiêu" → số theo sàn + ghi chú KRX có thể cũ + dòng khuyên đối chiếu sở/CTCK, không kèm giá thị trường.


---
