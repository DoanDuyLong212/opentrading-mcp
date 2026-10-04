# SKILLS.md — Gộp toàn bộ skills của harness OpenTrading (để kiểm duyệt)

> Nguồn sự thật: repo **OpenTrading** `skills/<slug>/SKILL.md` (24 skills: 21 theo
> thiết kế `docs/skills-design-for-harness.md` rev.3 + 3 skill nền: devil-advocate,
> explain-term, vn-market-basics). File gộp này chỉ để ĐỌC/DUYỆT — chỉnh sửa
> phải làm trên từng file SKILL.md trong OpenTrading rồi gộp lại.
>
> **rev.3 (Phase A)**: đã XÓA 6 skills theo yêu cầu — `danh-gia-tinh-hinh-thi-truong`,
> `kiem-tra-rui-ro-vi-the`, `luan-chuyen-nganh-viet-nam`, `luan-chuyen-tai-san-toan-cau`,
> `san-loc-co-phieu`, `theo-doi-va-bao-thuc`. Cross-refs trong skills còn lại đã sửa.
>
> **Bản P17 (02-10-2026, MCP-server `89db45b`)** — skills chịu ảnh hưởng, đã cập nhật dưới đây:
> `ky-thuat-chuyen-sau` (1W/1M + Ichimoku/swing/Elliott/Wyckoff),
> `kiem-chien-luoc-backtest` (rsi_meanrev + months/quarters + condition_symbol + `event_study`),
> `tim-co-hoi-bao-cao-ctck` (macro filter + đọc PDF),
> `tim-kiem-tin-tuc` + `phan-tich-sentiment` (`fireant_thread`, parser postID),
> `danh-gia-vi-mo-viet-nam` (macro filter), `phan-tich-chuyen-sau-1-ma` (`symbol_resolve`).

## Đặc tả frontmatter chung

| Field | Bắt buộc | Ý nghĩa |
|---|---|---|
| `name` | ✔ | slug kebab-case không dấu, ≤64 ký tự |
| `description` | ✔ | 1-2 câu; có "Dùng khi…/Không dùng khi…" để skill tự loại khỏi scope nhau |
| `activation` | ✔ | `auto` (model nạp khi khớp) / `always` (luôn trong system) / `manual` (chỉ /skill <tên>) |
| `requires_tools` | khuyến khích | skill chỉ hiện trong catalog khi MỌI tool này có mặt (gate theo preset) |
| `tool_budget` | với skill thiết kế | số lần gọi tool tối đa mỗi run; harness chặn cứng 20/lượt |
| `triggers.keywords` | khuyến khích | pre-routing: khớp keyword → gợi ý skill ở reminder |
| `version` | ✔ | semver, lưu cùng phiên bản session |

## Bảng tổng quan

| # | Skill | Kích hoạt | Budget | Tools yêu cầu (đã bỏ prefix mcp__) |
|---|---|---|---|---|
| 1 | `bat-on-quoc-gia` | auto | 6 | geo_intel |
| 2 | `co-ban-chuyen-sau` | auto | 9 | financial_detail |
| 3 | `danh-gia-tinh-hinh-chinh-tri-toan-cau` | auto | 8 | — |
| 4 | `danh-gia-tinh-hinh-xung-dot` | auto | 9 | event_stats |
| 5 | `danh-gia-truoc-bctc` | auto | 10 | company_events |
| 6 | `danh-gia-vi-mo-quoc-te` | auto | 10 | fred_series |
| 7 | `danh-gia-vi-mo-viet-nam` | auto | 12 | vs_indicator_data |
| 8 | `devil-advocate` | auto | — | — |
| 9 | `dinh-gia-chuyen-sau` | auto | 7 | valuation_run |
| 10 | `du-doan-fed` | auto | 8 | world_prediction_odds |
| 11 | `du-doan-polymarket` | auto | 6 | world_prediction_odds |
| 12 | `explain-term` | auto | — | — |
| 13 | `kiem-chien-luoc-backtest` | auto | 12 | quant_backtest |
| 14 | `ky-thuat-chuyen-sau` | auto | 8 | signals_technical |
| 15 | `nhip-dap-crypto` | auto | 8 | crypto_spot |
| 16 | `phan-tich-chuyen-sau-1-ma` | auto | 6 | stock_overview |
| 17 | `phan-tich-sentiment` | auto | 6 | sentiment_score |
| 18 | `phan-tich-vang-ty-gia` | auto | 10 | vn_retail_gold |
| 19 | `so-sanh-cung-nganh` | auto | 8 | compare_equities |
| 20 | `tim-co-hoi-bao-cao-ctck` | auto | 8 | analyst_consensus |
| 21 | `tim-kiem-tin-tuc` | auto | 10 | news_symbol |
| 22 | `tin-tuc-nong-quoc-te` | auto | 8 | news_market |
| 23 | `tin-tuc-nong-viet-nam` | auto | 9 | news_market |
| 24 | `vn-market-basics` | auto | — | — |

---

## 1 · bat-on-quoc-gia
> File thật: `OpenTrading/skills/bat-on-quoc-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: bat-on-quoc-gia
description: Đo bất ổn/ổn định của MỘT QUỐC GIA — 4 mức verdict từ GDELT counts + mức độ + transmission.
when_to_use: "Thái Lan đang bất ổn gì, đo độ ổn định Trung Quốc. Không dùng khi: nhiều nước so sánh (chạy lặp skill mỗi nước), bầu cử/chính sách toàn cầu (danh-gia-tinh-hinh-chinh-tri-toan-cau), chiến sự (danh-gia-tinh-hinh-xung-dot)."
activation: auto
requires_tools: [mcp__opentrading__geo_intel]
tool_budget: 6
triggers:
  keywords: [bất ổn, bất ổn quốc gia, biểu tình, đảo chính, ổn định, thái lan, bangladesh]
version: 1.0.0
---

# Bất ổn quốc gia

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `geo_intel`(topic=tên nước EN) · `event_stats`(query=tên nước EN) | 2 call song song, cùng upstream GDELT |
| 2 | `news_market`(sources=gdelt, lọc theo tên nước) | chỉ khi wave 1 mỏng |
| 3 (tùy chọn impact) | `yf_commodities` hoặc `assets_rotation` 1 call | khi user hỏi "ảnh hưởng thị trường" |

## Verdict

Chỉ báo bất ổn 4 mức (ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG) dựa: tần suất event GDELT
(so với baseline chính query đó — run này là baseline, run sau so sánh) · mức độ
(protest/conflict/coup keywords trong titles) · coverage nước láng giềng · transmission sang
giá (dầu/vàng/rotation nếu leg 3 chạy). Mỗi mục 1 dòng evidence + URL.

## Chống tràn lan

- 1 nước/run; query EN 1 lần + 1 biến thể; KHÔNG quét nhiều nước (user hỏi "ASEAN" → đề nghị tách từng nước).

## Lỗi thường gặp

GDELT rate-limit → 1 retry sau backoff (server đã cache 600s). Coverage mỏng là KẾT QUẢ
(nước ít tin — ghi chú "low-coverage ≠ stable").

## Bằng chứng live (02-10-2026)

geo_intel("Vietnam") + event_stats("vietnam") trả articles counts OK; pipeline EN-query thông.

## Nghiệm thu

"Bất ổn Thái Lan" → 4 mức verdict + ≥3 evidence lines có URL, ≤6 calls.
```


---

---

## 2 · co-ban-chuyen-sau
> File thật: `OpenTrading/skills/co-ban-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: co-ban-chuyen-sau
description: Phân tích THUẦN cơ bản 1 mã — BCTC từng dòng, chất lượng lợi nhuận (M-Score), kế hoạch, sở hữu, cổ tức.
when_to_use: "Đọc BCTC FPT, VCB có dấu hiệu thao túng không, cổ đông lớn HPG. Không dùng khi: kỹ thuật (ky-thuat-chuyen-sau), định giá (dinh-gia-chuyen-sau), so sánh nhiều mã (so-sanh-cung-nganh)."
activation: auto
requires_tools: [mcp__opentrading__financial_detail]
tool_budget: 9
triggers:
  keywords: [bctc, báo cáo tài chính, cơ bản, lợi nhuận gộp, nợ phải trả, vốn chủ, m-score, thao túng, cổ đông lớn, cổ tức, kế hoạch kinh doanh]
version: 1.0.0
---

# Cơ bản chuyên sâu 1 mã

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 | `vs_auth_status` | JWT sống = được dùng `financial_detail`; chết → nhánh mirror |
| 1 | `financial_detail`(statement=KQKD, periods_n=4) · `stock_forensic`(symbol) | song song 2 |
| 2 (chọn) | `financial_statements` · `financial_ratios` · `vn_fundamentals` | trend + ratios; 3 call max |
| 3 (chọn) | `planned_targets` · `holders` · `insider_trading` · `dividends_splits` | sở hữu/kế hoạch/chia cổ tức |
| 4 (tham chiếu) | `vs_financial_norms`/`vs_financial_terms`/`vs_company_info` | CHỈ khi cần giải thích norm_id/kỳ |

## Verdict

Chất lượng tăng trưởng (DT/LN 4 quý, biên) · ratios chủ chốt · M-Score + F-score + red flags ·
so với kế hoạch (vượt/hụt %) · cấu trúc sở hữu + thay đổi insider · chính sách cổ tức.
Kết luận 1 câu: CƠ BẢN TỐT/TRUNG BÌNH/YẾU + 3 rủi ro lớn nhất.

## Chống tràn lan

- Aspect nào mới chạy leg đó — "chataluong" chỉ wave 1; "sohuu" chỉ wave 3.
- `vs_financeinfo` chỉ là fallback JWT-chết; `vs_documents` KHÔNG thuộc skill này (tim-co-hoi-bao-cao-ctck).
- LCTT/CDKT chỉ gọi khi user hỏi dòng tiền/bảng cân đối (statement param).

## Lỗi thường gặp

Bank m_partial (SGAI null do LCTT rỗng — VCB live) → "M không kết luận", không gán M=0.
`financial_detail` periods vượt gói → rows rỗng + warning → degrade `vs_financeinfo` 1 lần.
`financial_statements` warning "statement not found, returning all pages" = đặc trưng v3-compat
— đọc trang trong data, đừng abort. vn_company chậm 30s khi throttle → đặt cuối wave, thiếu được.

## Bằng chứng live (02-10-2026)

FPT detail 25 norms × 138 số · M **−2.06**, F 2/6 · KH DT 61,850/75,400/58,580 · VCB holders
SBV 74.8% · VCB cổ tức 450đ · insider empty là đúng data.

## Nghiệm thu

"BCTC FPT có gì lạ" → wave 1 (2 calls) đủ M/F + 4 quý; "toàn cảnh cơ bản VPL" → ≤9 calls, không leg gọi 2 lần.
```


---

---

## 3 · danh-gia-tinh-hinh-chinh-tri-toan-cau
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-chinh-tri-toan-cau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: danh-gia-tinh-hinh-chinh-tri-toan-cau
description: Bản đồ rủi ro chính trị toàn cầu — bầu cử, chính sách, căng thẳng quốc tế, ghép xác suất + tin.
when_to_use: "Địa chính trị tuần này, bầu cử Brazil, rủi ro chính sách. Không dùng khi: xung đột vũ trang cụ thể (danh-gia-tinh-hinh-xung-dot), bất ổn 1 nước (bat-on-quoc-gia), chỉ xin odds (du-doan-polymarket), Fed (du-doan-fed)."
activation: auto
tool_budget: 8
triggers:
  keywords: [địa chính trị, bầu cử, chính trị, chính sách trump, căng thẳng quốc tế, rủi ro chính trị]
version: 1.0.0
---

# Đánh giá tình hình chính trị toàn cầu

Skill tổ chức — không home tool riêng, dùng cross-ref (design, không phải vi phạm).

## Workflow

| Wave | Tools |
|---|---|
| 1 | `world_prediction_odds`(tag=fed/politics/elections theo câu hỏi) · `geo_intel`(topic) |
| 2 | `polymarket_event`(slug top 1-2) · `event_stats`(query) |
| 3 | `news_market(sources=gdelt)` · `web_fetch`(1-2 nguồn chính thức trong tin) |

## Verdict

Bản đồ rủi ro 4-6 mục: sự kiện + xác suất (prob_pct) + volume thanh khoản (độ tin của odds)
+ tin GDELT xác nhận + market-impact nếu có.

## Chống tràn lan

- Odds đã sort vol24h — lấy top 5, không kéo cả 20 event.
- `polymarket_event` chỉ cho event THẬT SỰ liên quan câu hỏi.

## Lỗi thường gặp

GDELT rate-limit (đã gặp live) → backoff 20s → 1 lần. Gamma proxy chậm → fallback direct, chờ 1 lần.

## Bằng chứng live (02-10-2026)

Fed October 2026: "no change" **74.5%** (volume 24h ~2.6M USD) · Brazil presidential event OK.

## Nghiệm thu

"Rủi ro chính trị toàn cầu" → ≥4 mục có prob_pct + provenance event URL.
```


---

---

## 4 · danh-gia-tinh-hinh-xung-dot
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-xung-dot/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: danh-gia-tinh-hinh-xung-dot
description: Đánh giá xung đột/chiến sự cụ thể — cường độ, giá đã phản ánh, kênh truyền dẫn, xác suất leo thang.
when_to_use: "Trung Đông, Biển Đông, chiến sự X ảnh hưởng gì thị trường. Không dùng khi: chính trị bầu cử (danh-gia-tinh-hinh-chinh-tri-toan-cau), bất ổn 1 nước (bat-on-quoc-gia), odds thuần (du-doan-polymarket)."
activation: auto
requires_tools: [mcp__opentrading__event_stats]
tool_budget: 9
triggers:
  keywords: [xung đột, chiến tranh, biển đông, trung đông, leo thang, dầu hay vàng lên, chiến sự]
version: 1.0.0
---

# Đánh giá tình hình xung đột

## Workflow

| Wave | Tools |
|---|---|
| 1 | `geo_intel`(topic xung đột) · `event_stats`(query) |
| 2 | `yf_commodities`(dầu + vàng) · `assets_rotation` |
| 3 | `world_prediction_odds`(từ khóa cuộc chiến) · `web_search`/`web_fetch` |

## Verdict — 5 mục

Cường độ (event counts GDELT trend) · giá đã phản ánh chưa (dầu/vàng move vs baseline) ·
kênh truyền dẫn (energy→inflation→rates) · xác suất leo thang (odds) · hàm ý vị thế (đánh giá cushion/size trong danh-gia-truoc-bctc leg 6 trước khi hành động).

## Chống tràn lan

- 1 topic/call; từ khóa THỬ cả tiếng Việt lẫn Anh ("biển đông" → "south china sea") — tối đa 2 lần thử rồi chấp nhận "ít coverage".

## Lỗi thường gặp

GDELT rỗng với từ khóa VN → chuyển English query là ĐẶC TRƯNG data, không phải lỗi, ghi chú.

## Bằng chứng live (02-10-2026)

geo_intel("Vietnam") trả articles · event_stats("vietnam") articles >0 · gold 4,195 USD/oz cùng phiên.

## Nghiệm thu

"Xung đột X ảnh hưởng gì" → 5 mục verdict, có số dầu/vàng phiên gần nhất.
```


---

---

## 5 · danh-gia-truoc-bctc
> File thật: `OpenTrading/skills/danh-gia-truoc-bctc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: danh-gia-truoc-bctc
description: "Đánh giá setup trước BCTC — grade A/B/C từ 6 leg: sự kiện, trend, thao túng, kỳ vọng, positioning, đệm."
when_to_use: "Mùa BCTC cận kề (FPT sắp ra báo cáo, đánh giá setup). Không dùng khi: phân tích mã thường (phan-tich-chuyen-sau-1-ma), BCTC đã công bố (co-ban-chuyen-sau)."
activation: auto
requires_tools: [mcp__opentrading__company_events]
tool_budget: 10
triggers:
  keywords: [trước bctc, sắp ra báo cáo, pre earnings, công bố lợi nhuận, setup bctc]
version: 1.0.0
---

# Đánh giá trước BCTC

## Workflow (6 leg)

| Leg | Tools | Ghi chú |
|---|---|---|
| 1 Ngày | `company_events` + `event_calendar_vn` | dated hay rumor? |
| 2 Trend | load `co-ban-chuyen-sau` (aspect=baokao) | reuse leg, không gọi lại financial_* chồng chéo |
| 3 Thao túng | co-ban-chuyen-sau (aspect=chataluong) | M-Score/Piotroski |
| 4 Kỳ vọng | `planned_targets` + `analyst_consensus` + `news_symbol` + `sentiment_score` | anchor = kế hoạch DN (VN không consensus EPS) |
| 5 Positioning | `insider_trading` + `money_flow` + `block_trades` | |
| 6 Đệm | load `dinh-gia-chuyen-sau` + `scenario_simulate`(−5%) | size gợi ý |

## Verdict

Grade **A/B/C** + 1 dòng evidence/leg + size đề xuất + unknowns tường minh.
Rubric: A = ≥5 leg xanh + M-Score sạch + KH rõ; B = 4-5 leg; C = <4 leg hoặc M-Score đỏ (> −1.78).

## Chống tràn lan

Không forecast KQKD. `sentiment_score` heuristic không được tính là leg xanh đầy đủ.

## Bằng chứng live (02-10-2026, FPT)

M **−2.06** sạch · F 2/6 · KH DT 61,850/75,400/**58,580** · thưởng CP 10:1 ex 21-09 ·
sentiment heuristic −0.25 · NN bán ròng · pt 0% phiên → grade B.

## Nghiệm thu

"Đánh giá trước BCTC HPG" → grade + 6 leg evidence + unknowns, ≤10 calls (reuse legs).
```


---

---

## 6 · danh-gia-vi-mo-quoc-te
> File thật: `OpenTrading/skills/danh-gia-vi-mo-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: danh-gia-vi-mo-quoc-te
description: Đánh giá kinh tế Mỹ/toàn cầu — chu kỳ, đường cong lợi suất, chế độ rủi ro, so VN.
when_to_use: "Hỏi kinh tế Mỹ/global: Fed (bối cảnh, không phải odds), lợi suất, việc làm, GDP các nước, risk regime. Không dùng khi: VN (danh-gia-vi-mo-viet-nam), xác suất Fed (du-doan-fed)."
activation: auto
requires_tools: [mcp__opentrading__fred_series]
tool_budget: 10
triggers:
  keywords: [kinh tế mỹ, recession, suy thoái, đường cong lợi suất, yield curve, risk-on, risk-off, fed bối cảnh, kinh tế toàn cầu]
version: 1.0.0
---

# Đánh giá vĩ mô quốc tế

## Workflow

| Wave | Tools |
|---|---|
| 1 | `fred_series`(DGS10) · `fred_series`(CPIAUCSL) · `yf_yield_curve` |
| 2 | `yf_regime_assets` · `assets_rotation` · `world_macro_country`(VN/CHINA theo câu hỏi) |
| 3 | `yf_global_indices` · `yf_commodities` · `world_fear_greed` |

## Verdict — 5 mục

Chu kỳ Mỹ (soft/hard landing, dựa DGS10+CPI+curve) · đường cong (inverted?) · chế độ toàn
cầu (RISK-ON/OFF từ rotation) · so VN-vs-global (GDP VN cross-ref S3) · biến số theo dõi.

## Chống tràn lan

- fred series GỌI THEO TÊN (≥3 series cùng lúc là dấu hiệu tràn lan — dừng). yf wave ≤3.

## Lỗi thường gặp

FRED thiếu key → unavailable, chuyển nhánh không-FRED + ghi chú. Curve flaky (từng
fail→tự hồi) → retry 1 lần sau backoff, rồi bỏ.

## Bằng chứng live (02-10-2026)

US10Y 5.24% / 2Y 4.61%, không đảo chiều · WorldBank GDP VN 8.02% · fear/greed crypto 70-74 (tham lam).

## Nghiệm thu

"Kinh tế Mỹ hiện tại" → 5 mục verdict, curve + ≥2 series fred có số.
```


---

---

## 7 · danh-gia-vi-mo-viet-nam
> File thật: `OpenTrading/skills/danh-gia-vi-mo-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: danh-gia-vi-mo-viet-nam
description: Đánh giá vĩ mô VN — GDP, CPI, xuất nhập khẩu, tỷ giá, lãi suất điều hành, lịch công bố.
when_to_use: "Hỏi GDP/CPI/XNK VN, tỷ giá USDVND bối cảnh vĩ mô, lãi suất SBV, lịch công bố số liệu. Không dùng khi: vĩ mô Mỹ/toàn cầu (danh-gia-vi-mo-quoc-te), vàng-tỷ giá thao tác (phan-tich-vang-ty-gia)."
activation: auto
requires_tools: [mcp__opentrading__vs_indicator_data]
tool_budget: 12
triggers:
  keywords: [vĩ mô, GDP, CPI, lạm phát, xuất khẩu, nhập khẩu, lãi suất điều hành, sbv, xnk, cán cân]
version: 1.0.0
---

# Đánh giá vĩ mô Việt Nam

## Workflow

| Wave | Tools |
|---|---|
| 0 | `source_status` · `vs_auth_status` |
| 1 (catalog) | `vs_categories` — tra category_id nếu chưa chắc · `analyst_consensus`(report_type=macro) quét báo cáo vĩ mô CTCK (P17; section pointers + dated reports, thiếu thì dùng số liệu gốc) |
| 2 (series) | `vs_indicator_data`(GDP: 73,tt3) · (CPI: 15,tt7,sub2) · (XK: 38,tt2) · `vs_xnk_detail`(xk) |
| 3 | `sbv_rates` · `macro_events_vn` · `vn_msn_fx_gold` · `vn_retail_fx` · `economic_calendar` |
| 4 (lịch sử) | `snapshot_history`(macro_curated) khi live fail |

## Verdict — 6 mục

Tăng trưởng (q/dư + trend) · lạm phát (yoy) · thương mại (cán cân, đối tác lớn) ·
tỷ giá (USDVND + spread SBV) · lãi suất điều hành · kỳ công bố sắp tới (ngày).
GDP/CPI/XK: lấy ≥8 điểm cuối, ghi rõ đơn vị.

## Chống tràn lan

- CẶP category/termType phải ĐÚNG (sai là rows rỗng — GDP đúng tt3, không phải tt2).
- Không quét cả 60 categories — chỉ 4-6 cần thiết. `vs_xnk_detail` theo direction riêng — chọn 1 theo câu hỏi.

## Lỗi thường gặp

Thiếu HAR session → macro trả permission message → BẢO TRUNG THỰC "macro cần session",
fallback `snapshot_history`; không diễn giải message permission thành dữ liệu.

## Bằng chứng live (02-10-2026)

GDP 504 rows tới Q2/2026 · CPI 1,839 · XK 2,941 · XNK-country 3,675 · SBV tái cấp vốn
4.5% / tái chiết khấu 3% · USDVND 25,970 · NSO lịch CPI tháng 8.

## Nghiệm thu

"Đánh giá vĩ mô VN" → đủ 6 mục, GDP+CPI có số quý gần nhất; thiếu session → nêu đúng tình trạng + dùng snapshot cache.
```


---

---

## 8 · devil-advocate
> File thật: `OpenTrading/skills/devil-advocate/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: devil-advocate
description: Phản biện luận điểm đầu tư của người dùng để chống thiên kiến xác nhận.
when_to_use: Người dùng hỏi về mã họ đang nắm hoặc đã thích, xin ý kiến về một luận điểm mua/giữ, hoặc yêu cầu phản biện.
activation: auto
triggers:
  keywords: [phản biện, bear case, có nên giữ, rủi ro gì, đang nắm, đang giữ]
version: 1.1.0
---

Vai trò của bạn là người phản biện. Người dùng thường hỏi về cổ phiếu họ đã mua hoặc đã thích.

1. Tóm tắt luận điểm của người dùng trong 1–2 câu để chắc chắn hiểu đúng.
2. Liệt kê 3–5 lý do mạnh nhất khiến luận điểm có thể SAI (ngành, doanh nghiệp, định giá, vĩ mô, thanh khoản).
3. Với mỗi lý do, nêu dấu hiệu cụ thể cần theo dõi để biết rủi ro đó đang xảy ra.
4. Nêu điều kiện phủ định: sự kiện nào xảy ra thì luận điểm nên bị bỏ.
5. Giữ giọng trung lập, không mỉa mai, không kết luận thay người dùng.
```


---

---

## 9 · dinh-gia-chuyen-sau
> File thật: `OpenTrading/skills/dinh-gia-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: dinh-gia-chuyen-sau
description: Định giá chuyên sâu 1 mã — vùng fair value (PER/PB/DCF-lite), so lịch sử, UPSIDE/DOWNSIDE %.
when_to_use: "FPT đắt chưa, VCB fair value, định giá theo PER. Không dùng khi: so sánh nhiều mã (so-sanh-cung-nganh), cơ bản thuần (co-ban-chuyen-sau)."
activation: auto
requires_tools: [mcp__opentrading__valuation_run]
tool_budget: 7
triggers:
  keywords: [định giá, fair value, dcf, per, đắt hay rẻ, upside, giá mục tiêu tự tính, valuation]
version: 1.0.0
---

# Định giá chuyên sâu 1 mã

## Workflow

| Wave | Tools |
|---|---|
| 1 | `valuation_run`(symbol, method) · `vs_overview_trading`(symbol) |
| 2 | `financial_ratios`(symbol) · `vn_quote_history`(symbol, days=365) |
| 3 (bối cảnh) | `yf_yield_curve` · `vs_trading_info`(symbol) |

## Verdict

Giá hiện tại vs vùng fair (method nào dẫn, chênh bao nhiêu %) · PER/PB hiện vs trung bình
2-3 năm (tự tính từ wave 2) · rẻ/đắt hợp lý vì sao (tăng trưởng, chất lượng co-ban-chuyen-sau
cross-ref, lãi suất leg 3) · **UPSIDE/DOWNSIDE %** + độ tin (cao nếu 2 method đồng thuận).

## Chống tràn lan

- DCF-lite trong `valuation_run` đã tính sẵn — KHÔNG tự dựng lại DCF.
- 1 `method` per run (auto trừ khi user khăng khăng); bond context chỉ khi PB-heavy.

## Lỗi thường gặp

`method` sai enum → warning, về auto. EPS âm (công ty lỗ) → per_pb vô nghĩa, nói thẳng
"không đủ cơ sở định giá". Bank (đặc thù PB) → ưu tiên per_pb.

## Bằng chứng live (02-10-2026)

VCB per_pb @57,400 (2 method đồng thuận) · FPT per_pb @62,700 · US10Y 5.24% context · overview_trading VCB PE/PB/ROEA đủ.

## Nghiệm thu

"FPT đắt chưa" → UPSIDE % + so lịch sử 2 dòng, ≤7 calls.
```


---

---

## 10 · du-doan-fed
> File thật: `OpenTrading/skills/du-doan-fed/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: du-doan-fed
description: Xác suất/kịch bản lãi suất Fed — odds, đường cong, lịch FOMC, hàm ý cho VN.
when_to_use: "Fed tháng tới, cắt hay giữ, FOMC, dot plot. Không dùng khi: bối cảnh vĩ mô Mỹ chung (danh-gia-vi-mo-quoc-te)."
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 8
triggers:
  keywords: [fed, fomc, cắt giảm lãi suất, dot plot, xác suất fed, lãi suất mỹ]
version: 1.0.0
---

# Dự đoán Fed

## Workflow

| Wave | Tools |
|---|---|
| 1 | `world_prediction_odds`(query=fed) |
| 2 | `polymarket_event`(slug fed-decision-*) · `fred_series`(DGS10 [+ EFFR/DFII nếu cần]) |
| 3 | `yf_yield_curve` · `web_fetch`(fed.gov statement/nguồn chính thức trong odds) |

## Verdict — 5 mục

Xác suất từng kịch bản (cắt/giữ/tăng, prob_pct + volume + end-date) · đường cong ám chỉ ·
lịch FOMC kế tiếp · biến số theo dõi (CPI Mỹ, jobs) · hàm ý cho VN (tỷ giá, cross-ref S3/S16).

## Chống tràn lan

- CHỈ 1 event fed chính (slug mới nhất, đã sort vol24h) — không bắn 5 query biến thể.

## Lỗi thường gặp

Odds stale (end date qua) → lọc `end > today`. Gamma chết cả proxy+lần → nói rõ "không có
odds", KHÔNG thay bằng nhận định riêng.

## Bằng chứng live (02-10-2026)

"Fed Decision in October 2026": Yes(no change) **74.5% / No 25.5%**, volume24h 2.6M · curve US10Y 5.24% không đảo.

## Nghiệm thu

"Fed tháng tới" → prob ≥2 kịch bản + lịch họp + 1 dòng hàm ý VN.
```


---

---

## 11 · du-doan-polymarket
> File thật: `OpenTrading/skills/du-doan-polymarket/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: du-doan-polymarket
description: Xác suất từ Polymarket theo chủ đề — bảng event + cờ tin-cậy (liquidity, end-date).
when_to_use: "Market nào đang nóng, odds bầu cử Mỹ, bao giờ BTC chạm 100k. Không dùng khi: Fed chuyên biệt (du-doan-fed), chính trị rộng (danh-gia-tinh-hinh-chinh-tri-toan-cau)."
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 6
triggers:
  keywords: [polymarket, odds, xác suất, prediction market, bao giờ bitcoin, cá cược sự kiện]
version: 1.0.0
---

# Dự đoán Polymarket

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `world_prediction_odds`(query hoặc tag, limit=10) | đã sort vol24h — tin dùng top |
| 2 | `polymarket_event`(slug — 1 event user quan tâm) | drill-down outcomes đầy đủ |
| 3 (chọn lọc ≤2) | `polymarket_event`(slug thứ 2) | tối đa 2 drill-down/run |

## Verdict

Bảng event {title · prob_pct từng outcome · volume24h · liquidity · end-date} + 2 cờ bắt
buộc: (1) liquidity thấp (<50k) → "odds kém tin"; (2) end-date đã qua → loại. Kết luận 1
câu "thị trường đặt cược X với xác suất Y".

## Chống tràn lan

- Drill-down tối đa 2 event/run — người dùng chọn, skill không tự mở cả top-10.
- Query rỗng → ĐỔI tag 1 lần rồi kết luận "không có market cho chủ đề".

## Lỗi thường gặp

Jina proxy chậm → tool tự fallback direct (warnings cho biết). Gamma chết cả 2 đường →
unavailable, nói rõ "không có odds", không bịa xác suất.

## Bằng chứng live (02-10-2026)

Fed T10/2026 no-change **74.5%** (vol 2.6M) · Brazil presidential detail OK · sort vol24h hoạt động.

## Nghiệm thu

"Polymarket đang nóng gì về kinh tế" → ≥5 event + cờ tin-cậy trên từng dòng.
```


---

---

## 12 · explain-term
> File thật: `OpenTrading/skills/explain-term/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: explain-term
description: Giải thích một thuật ngữ chứng khoán / tài chính cho nhà đầu tư cá nhân.
when_to_use: Người dùng hỏi một thuật ngữ, chỉ số hoặc khái niệm là gì (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2…).
activation: auto
triggers:
  keywords: [là gì, nghĩa là gì, giải thích, khái niệm, thuật ngữ]
version: 1.1.0
---

Khi người dùng hỏi một thuật ngữ (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, v.v.):

1. Định nghĩa trong một câu, không dùng biệt ngữ khác chưa giải thích.
2. Công thức (nếu có), viết bằng chữ, không tự thay số.
3. Ví dụ minh hoạ dùng số tròn giả định, ghi rõ "ví dụ giả định".
4. Cách dùng thực tế ở thị trường Việt Nam và một cái bẫy hay gặp khi đọc chỉ số này.
5. Kết thúc bằng một câu hỏi gợi ý để người dùng đào sâu.
```


---

---

## 13 · kiem-chien-luoc-backtest
> File thật: `OpenTrading/skills/kiem-chien-luoc-backtest/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: kiem-chien-luoc-backtest
description: Kiểm chứng chiến lược/backtest — baseline, best param KÈM worst param, seasonality, verdict đáng tin.
when_to_use: "SMA20/50 FPT có ăn không, mùa vụ tháng mấy, backtest VN30F1M. Không dùng khi: cỡ vị thế/sizing trước lệnh (xem leg Đệm trong danh-gia-truoc-bctc)."
activation: auto
requires_tools: [mcp__opentrading__quant_backtest]
tool_budget: 12
triggers:
  keywords: [backtest, kiểm chứng, chiến lược, sma cross, momentum chiến lược, param sweep, mùa vụ tháng]
version: 1.0.0
---

# Kiểm chứng chiến lược (backtest)

## Workflow

| Wave | Tools |
|---|---|
| 1 | `vn_quote_history`(stock) hoặc `dnse_ohlc_history`(futures/index) · `vn_index_ohlcv`(benchmark) |
| 2 | `quant_backtest`(baseline buy-hold) · `quant_factors` |
| 3 | `backtest_strategies`(sma/momentum/**rsi_meanrev** + `rsi_low`/`rsi_high` + filter `months`/`quarters` + `condition_symbol` dầu/vàng + `condition_rule`) · `param_sweep`(fast×slow ≤30 combos, passthrough months/quarters) |
| 4 | `seasonality` · `correlation_matrix` · `portfolio_optimize`(nếu nhiều mã) · `pattern_match` |
| 5 (sau sự kiện) | `event_study`(symbol, dates, window ±N, benchmark) — CAR quanh Tết/cổ tức/ĐHĐCĐ, nearest-day 3 phiên |

## Verdict

Baseline → chiến lược → best param **KÈM worst param** (chống overfit) → seasonality bias →
event CAR (nếu hỏi sự kiện) → kết luận "đáng tin / đáng nghi + lý do". Ghi rõ engine:
numpy-only, cost mặc định, T+2 VN chưa model trong backtest. `rsi_meanrev`: mua RSI<30,
thoát RSI>70. Month filter: entries chỉ kỳ chọn, exits luôn mở.

## Chống tràn lan

- 1 symbol mỗi lần sweep; `param_sweep` cap 30 combos có sẵn — không tự nới; không sweep >3 symbol/run.
- `condition_symbol`: VN qua vnstock, còn lại (BZ=F, GC=F...) qua yfinance — tool tự fallback;
  condition chết → cả call unavailable, nói rõ.

## Bằng chứng live (02-10-2026)

VCB buy-hold −4.9% gross · sma_cross HPG-family: 7 trades −10.4% · param_sweep best
**+3.7%** · seasonality bucket theo tháng · basis F1M 31-37bps.
P17: rsi_meanrev VCB 1 trade · month filter months=[1] trên nến tháng 3 → 0 trades +
warning `month-filtered` · event_study VCB 2026-09-21: 1 event, CAR +0.25%.

## Nghiệm thu

"Backtest SMA FPT 1 năm" → baseline+strategy+sweep bảng, kèm caveat.
```


---

---

## 14 · ky-thuat-chuyen-sau
> File thật: `OpenTrading/skills/ky-thuat-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: ky-thuat-chuyen-sau
description: Phân tích THUẦN kỹ thuật 1 mã — chỉ báo, pattern, S-R, RS vs index, intraday/orderbook.
when_to_use: "VCB kỹ thuật sao, FPT có breakout không, đọc băng HPG, RSI và hỗ trợ-kháng cự. Không dùng khi: cơ bản (co-ban-chuyen-sau), định giá (dinh-gia-chuyen-sau), săn breakout toàn thị trường (gọi signals_scan trực tiếp, cap max_symbols=100)."
activation: auto
requires_tools: [mcp__opentrading__signals_technical]
tool_budget: 8
triggers:
  keywords: [kỹ thuật, rsi, macd, hỗ trợ, kháng cự, breakout, pattern, orderbook, băng giá, chỉ báo, adx, ema, sma]
version: 1.0.0
---

# Kỹ thuật chuyên sâu 1 mã

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `signals_technical`(symbol, interval=1D/1W/1M) | 1 call = RSI/MACD/Bands/ADX/patterns/S-R/RS/pos_52w/sma150 + Ichimoku (tenkan/kijun/senkou/signal) + swings HH/HL/LH/LL + Fibonacci 7 mức + Elliott (impulse/corrective/developing + invalidation) + Wyckoff phase — live từ P17 |
| 2 (chọn) | `pattern_match`(symbol) · `vn_quote_history`(symbol, days=250) | analogy + tự vẽ đường xu hướng |
| 3 (intraday) | `dnse_latest_trade` · `dnse_orderbook` · `vn_trades` | ≤3, cùng upstream DNSE |
| 4 (index context) | `vn_index_ohlcv`(VNINDEX) | khi cần so trend index |

## Verdict

Trạng thái trend (đỉnh/đáy/downtrend/đi ngang bằng SMA stack + ADX) · momentum (RSI/MACD/
stoch) · vùng S-R + giá hiện tại nằm đâu · pattern + xác suất lịch sử (pattern_match corr) ·
Ichimoku signal + swing trend (higher-high/lower-low) + Elliott pattern/invalidation +
Wyckoff phase · RS vs VNINDEX · kết luận timing (MUA/CHỜ/BÁN + trigger giá).

## Chống tràn lan

- Wave 2 CHỈ khi user hỏi "mẫu hình/quá khứ"; wave 3 CHỈ khi intraday.
- `interval` chấp nhận 1D/1W/1M (1W cần ≥30 bars, 1M ≥24 bars); interval lạ → tool báo
  unavailable, đừng retry.
- Elliott/Wyckoff là heuristic (kèm confidence) — verdict ghi confidence + invalidation,
  không diễn giải sóng chuẩn bằng lời suông.
- `signals_technical` 1 call đã đủ 80% verdict — skill "1 tool trụ cột" mẫu mực.

## Lỗi thường gặp

Mã mới <60 nến → indicators null, báo "thiếu lịch sử". DNSE hết giờ → orderbook rỗng là
đúng. `pattern_match` corr <0.4 = không có analogy đáng tin. Giá theo kVND
(`signals_technical.last 57.3` = 57,300đ) — qui đổi + ghi đơn vị.

## Bằng chứng live (02-10-2026)

VCB — RSI 39.2, ADX 12.1 (trend yếu), MACD −0.31/−0.13, EMA10 58.09, pos_52w 0.21, recommend
Sell (HPG) · HPG pattern best_corr 0.409 (yếu — ghi đúng) · orderbook VCB depth live · băng 10:18 giá 58.1.
P17: VCB 1W bearish/lower-low/fib-down nhất quán (ichimoku + swing + fib live).

## Nghiệm thu

"RSI FPT và vùng hỗ trợ" → 2 mục verdict ≤2 calls; "intraday SSI" → thêm leg orderbook, tổng ≤8.
```


---

---

## 15 · nhip-dap-crypto
> File thật: `OpenTrading/skills/nhip-dap-crypto/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: nhip-dap-crypto
description: Nhịp đập crypto — giá, funding, OI, sentiment, nến quy VND.
when_to_use: "BTC/ETH sao rồi, funding rate, crypto quy VND. Không dùng khi: bối cảnh regime toàn cầu (danh-gia-vi-mo-quoc-te), odds sự kiện crypto (du-doan-polymarket)."
activation: auto
requires_tools: [mcp__opentrading__crypto_spot]
tool_budget: 8
triggers:
  keywords: [btc, bitcoin, eth, ethereum, crypto, funding, open interest, binance]
version: 1.0.0
---

# Nhịp đập crypto

## Workflow

| Wave | Tools |
|---|---|
| 1 | `crypto_spot`(≤5 symbols) · `crypto_derivs`(BTC ETH SOL) · `world_fear_greed` |
| 2 | `vn_crypto_ohlv`(path quy VND) · `yf_commodities`(BTC ref) |
| 3 | `polymarket_event`/`world_prediction_odds`(crypto markets — chỉ khi user hỏi xác suất) |

## Verdict — 4 mục

Giá + 24h volume · leverage read (funding, OI, long/short) · fear/greed + label · path VND
(điểm khác biệt của bộ tool này) · rủi ro chính sách nếu có tin (chỉ khi user hỏi).

## Bằng chứng live (02-10-2026)

BTC 83,476 (+0.33%) · funding 2.8e-05 · OI 95.7k · fear/greed 70-74.

## Nghiệm thu

"Crypto sao rồi" → 4 mục verdict; funding/OI fail một symbol không làm chết batch (per-symbol error).
```


---

---

## 16 · phan-tich-chuyen-sau-1-ma
> File thật: `OpenTrading/skills/phan-tich-chuyen-sau-1-ma/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: phan-tich-chuyen-sau-1-ma
description: Phân tích TOÀN DIỆN một mã cụ thể — điều phối các skill chuyên (S22 kỹ thuật, S23 cơ bản, S24 định giá, S25 so sánh, S26 sentiment, S27 báo cáo CTCK) rồi gộp verdict. KHÔNG tự gọi chồng chéo hàng chục tools.
when_to_use: "Người dùng yêu cầu phân tích toàn diện một mã (phân tích FPT). Không dùng khi: user chỉ hỏi 1 chiều (RSI → ky-thuat-chuyen-sau; BCTC → co-ban-chuyen-sau; fair value → dinh-gia-chuyen-sau)."
activation: auto
requires_tools: [mcp__opentrading__stock_overview]
tool_budget: 6
triggers:
  keywords: [phân tích, phân tích cổ phiếu, phân tích mã, so sánh phân tích, toàn diện, chi tiết mã]
version: 1.0.0
---

# Phân tích chuyên sâu 1 mã (điều phối)

Skill điều phối: kích các skill chuyên làm việc chân, tự lo budget riêng (≤8 call mỗi skill),
rồi gộp verdict. CẤM gọi trực tiếp `signals_technical`/`financial_detail`/`valuation_run`/
`stock_forensic`… — ai cần chiều nào kích sub-skill chiều đó.

## Workflow

| Wave | Việc |
|---|---|
| 0 (pre-flight) | `source_status` (+ `vs_auth_status` nếu sẽ dùng vs_*) |
| 1 | `stock_overview(symbol)` · `symbol_lookup` nếu nghi tên (mã đa loại/nhập nhằng: vàng/BTC/USD → `symbol_resolve` trước, P16) — snapshot nhanh |
| 2 | `event_calendar_vn(symbol)` — lịch sự kiện 30 ngày tới |
| 3 (dispatch) | toan-dien → load_skill lần lượt: ky-thuat-chuyen-sau → co-ban-chuyen-sau → dinh-gia-chuyen-sau; focus đơn → chỉ skill tương ứng |
| 4 | `evidence_bundle` — khóa verdict từ các leg đã chạy |

## Verdict (6 mục, mỗi mục 1-2 dòng + provenance)

1. Kỹ thuật (từ S22) · 2. Cơ bản (S23) · 3. Định giá (S24) · 4. Dòng tiền/sự kiện ·
5. Sentiment/cơ hội (S26/S27) · 6. Bull-bear + điều kiện đổi nhận định.

## Chống tràn lan

- Budget 6 chỉ đếm tool nhà của skill; tool của sub-skill nằm trong budget sub-skill.
- User hỏi 1 chiều ("RSI FPT") → trả lời bằng sub-skill tương ứng, không chạy skill này.

## Lỗi thường gặp

Sub-skill chết 1 chân → vẫn ra verdict với leg còn sống + ghi leg thiếu, không bù số.

## Nghiệm thu

"Phân tích FPT" → verdict 6 mục; skill ≤6 calls nhà; không tool trùng giữa điều phối và sub-skill.
```


---

---

## 17 · phan-tich-sentiment
> File thật: `OpenTrading/skills/phan-tich-sentiment/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: phan-tich-sentiment
description: Dư luận/crowd sentiment về 1 mã trên Fireant — điểm + quotes + cảnh báo FOMO, bắt buộc ghi nhãn nguồn.
when_to_use: "Phố nói gì về FPT, sentiment VCB, crowd có FOMO HPG không. Không dùng khi: tin chính thống (tim-kiem-tin-tuc), fear/greed thị trường chung (danh-gia-vi-mo-quoc-te / nhip-dap-crypto)."
activation: auto
requires_tools: [mcp__opentrading__sentiment_score]
tool_budget: 6
triggers:
  keywords: [sentiment, dư luận, phố nói gì, crowd, fomo, tâm lý nhà đầu tư, comment]
version: 1.0.0
---

# Phân tích sentiment

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `news_symbol`(symbol, limit=20) · `sentiment_score`(symbol, limit=20) | song song — cùng nguồn Fireant; posts giờ CÓ id thật (parser postID, P17) |
| 2 (đào thread nóng) | `fireant_thread`(post_id của post nhiều replies nhất) | rumor threads nằm ở replies — đọc trước khi kết luận FOMO/hoảng loạn |
| 3 (chọn khi mâu) | `company_events`(symbol) | đối chiếu cmt với công bố chính thức |

## Verdict

Điểm sentiment (Groq hoặc heuristic — **BẮT BUỘC ghi nhãn nguồn**, heuristic thang khác) +
3-5 trích comment tiêu biểu (positive/negative/repeat-thuyết) + nhận diện FOMO/hoảng loạn
(tần suất symbol tag + likes) + **cảnh báo vòng lặp**: crowd có thể sai — sentiment KHÔNG
được là leg duy nhất của quyết định.

## Chống tràn lan

- 1 symbol/run; limit 20 đủ 90% mẫu — không call lại limit lớn hơn.
- `company_events` chỉ khi comment contradicts disclosures; không dùng sentiment "chốt luận" — chỉ confirm/deny.

## Lỗi thường gặp

Thiếu Groq → `score_heuristic` + warning "groq unavailable" → nhãn "heuristic" trong
verdict. Posts rỗng = mã ít bàn (empty hợp lệ). Fireant chết → fallback duy nhất: GDELT
titles qua tim-kiem-tin-tuc (1 call).

## Bằng chứng live (02-10-2026)

FPT — 20 posts, heuristic **−0.25**, trong khi M −2.06 sạch (điển hình crowd≠fundamentals) ·
VCB posts lãi suất 0.1-6% · Groq key có trên prod, thiếu trên local dev.

## Nghiệm thu

"Phố nói gì về FPT" → điểm + ≥3 quotes + nhãn nguồn, ≤4 calls.
```


---

---

## 18 · phan-tich-vang-ty-gia
> File thật: `OpenTrading/skills/phan-tich-vang-ty-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: phan-tich-vang-ty-gia
description: Phân tích vàng SJC/thế giới, tỷ giá USDVND — premium, trend, điều khiển, khung dự báo.
when_to_use: "Vàng SJC đắt hơn thế giới bao nhiêu, tỷ giá áp lực. Không dùng khi: lãi suất điều hành VN chung (danh-gia-vi-mo-viet-nam), crypto (nhip-dap-crypto)."
activation: auto
requires_tools: [mcp__opentrading__vn_retail_gold]
tool_budget: 10
triggers:
  keywords: [vàng sjc, vàng miếng, giá vàng, usdvnd, tỷ giá, premium vàng, vàng thế giới, xauusd]
version: 1.0.0
---

# Phân tích vàng & tỷ giá

## Workflow

| Wave | Tools |
|---|---|
| 1 | `vn_retail_gold`(SJC+nhẫn) · `vn_msn_fx_gold`(XAUUSD+USDVND) · `sbv_rates` |
| 2 | `yf_commodities`(GC) · `fred_series`(DGS10) · `world_prediction_odds`(fed) |
| 3 | `vn_forex_ohlcv`(USDVND path) · `macro_events_vn` · `vn_retail_fx`(spreads VCB) |

## Verdict

Premium SJC vs thế giới (qui đổi, ghi giả định tính thuế/phí) · trend tỷ giá + khoảng cách
trần · điều khiển (DGS10, Fed odds, SBV) · dự báo KHUNG (không point-forecast).

## Chống tràn lan

- 1 call `yf_commodities` (đã gồm GC+DXY) thay vì tick riêng lẻ.

## Bằng chứng live (02-10-2026)

VÀNG MIẾNG SJC 999.9 (BTMC live) · XAUUSD 4,195 · USDVND 25,970 (MSN) · SBV 4.5% tái cấp vốn · Fed giữ 74.5%.

## Nghiệm thu

"Vàng SJC hôm nay đắt hơn thế giới bao nhiêu" → số premium % + giả định + 2 driver.
```


---

---

## 19 · so-sanh-cung-nganh
> File thật: `OpenTrading/skills/so-sanh-cung-nganh/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: so-sanh-cung-nganh
description: So sánh 2-6 mã CÙNG NGÀNH / chọn leader — bảng xếp hạng + 1 dòng luận chọn.
when_to_use: "VCB vs BID vs CTG, steel mạnh nhất là ai, ngân hàng nào đáng mua nhất. Không dùng khi: 1 mã (phan-tich-chuyen-sau-1-ma / co-ban-chuyen-sau / dinh-gia-chuyen-sau), ngành chảy tiền thế nào: dùng sector_performance + vs_industry_heatmap trực tiếp; user đưa FILTER: gọi stock_screener trực tiếp (universe hẹp, limit ≤20)."
activation: auto
requires_tools: [mcp__opentrading__compare_equities]
tool_budget: 8
triggers:
  keywords: [so sánh, vs, so với, cùng ngành, mạnh nhất, leader, hơn kém, xếp hạng mã]
version: 1.0.0
---

# So sánh cùng ngành

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 (nếu nhập ngành) | `vn_reference`(industry) → chọn ≤6 mã | hoặc `vs_industry_tree`(tra GICS id) 1 call |
| 1 | `compare_equities`(≤4) | overview + momentum; 5-6 mã → chia 4+2 qua `peer_compare` |
| 2 | `signals_technical` × ≤4 mã (song song 4) | RS/pos_52w từng ứng viên |
| 3 | `financial_ratios` × ≤3 (song song 3) | PE/ROE/biên |
| 4 (bối cảnh) | `vs_gics_index`(group) · `vn_equity_quote_batch`(≤6 mã, 1 call) | index ngành + bảng giá 1 shot |

## Verdict

Bảng xếp hạng {mã · PE · ROE · momentum · RS · giá} + **1 dòng luận chọn** (leader = chất
lượng×momentum; định giá tốt = PE thấp trong nhóm ROE cao) + cảnh báo (correlation_matrix
cross-ref khi user hỏi "chia tiền cả nhóm").

## Chống tràn lan

- Cap tuyệt đối 6 mã/run — trên 6 → yêu cầu thu hẹp; `signals_technical` tối đa 4.
- Thiếu dữ liệu 1 tiêu chí → xếp hạng partial + ghi "n/6 mã có đủ", không loại âm thầm.

## Lỗi thường gặp

Enrich throttle giờ cao điểm (0/20 từng live) → ratios rỗng → verdict kỹ thuật-only, ghi
chú. `vn_reference` industry không match → thử `vs_industry_tree` 1 lần.

## Bằng chứng live (02-10-2026)

compare_equities VCB-vs-HPG 2.8s · peer_compare cap 6 · vs_gics_index 3 nhóm live ·
quote_batch 1 request VN30 · HOSE universe 757 mã.

## Nghiệm thu

"So sánh bank" → bảng ≥4 mã xếp hạng + luận chọn 1 dòng, ≤8 calls.
```


---

---

## 20 · tim-co-hoi-bao-cao-ctck
> File thật: `OpenTrading/skills/tim-co-hoi-bao-cao-ctck/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: tim-co-hoi-bao-cao-ctck
description: Săn cơ hội theo BÁO CÁO PHÂN TÍCH CTCK — rating, giá mục tiêu, upside % đã kiểm chứng.
when_to_use: "CTCK gần đây khuyên mua gì, có target mới cho MSN không, báo cáo VPS/SSI nói gì về HPG. Không dùng khi: tin đồn/crowd (phan-tich-sentiment / tim-kiem-tin-tuc), tự định giá (dinh-gia-chuyen-sau)."
activation: auto
requires_tools: [mcp__opentrading__analyst_consensus]
tool_budget: 8
triggers:
  keywords: [ctck, khuyên mua, giá mục tiêu, target, báo cáo phân tích, khuyến nghị, rating]
version: 1.0.0
---

# Tìm cơ hội từ báo cáo CTCK

## Workflow

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `analyst_consensus`(limit=30) | **feed chung không symbol** — parse rating + giá mục tiêu từ titles |
| 1b (báo cáo vĩ mô) | `analyst_consensus`(report_type=macro) | lọc báo cáo vĩ mô CTCK (entry section/report); không có dated reports thì tool báo trung thực + dùng `vs_indicator_data` lấy số liệu gốc |
| 2 (mã cụ thể) | `analyst_consensus`(symbol, limit=15) · `vs_documents`(symbol) · `web_fetch`(format=pdf, URL báo cáo) | report cho mã + tài liệu gốc + **đọc nội dung PDF** (stdlib-only, scan báo trung thực; cap 10 trang/20k ký tự) |
| 3 (xác nhận) | `stock_overview`(mã target) 1-2 call | so giá hiện tại vs mục tiêu → upside % |

## Verdict

Bảng {mã · CTCK · rating · giá mục tiêu · ngày · upside % so giá hiện tại} lọc trong `days`
(default 7); top 3 cơ hội (upside lớn + rating MUA + còn hiệu lực); **cột "đã kiểm chứng"**
= leg 3 chạy cho 1-2 mã nổi bật nhất, không kiểm chứng tất cả. Disclaimer: khuyến nghị CTCK
là INPUT, không phải chân lý — không suy diễn thành "nên mua".

## Chống tràn lan

- Feed chung 1 call (symbol-less feed CÓ dữ liệu).
- Hỏi "HPG" mà `analyst_consensus(symbol=HPG)` empty → đọc feed chung và lọc title chứa HPG
  (title-scrape filter có thể sót), không retry đổi limit.
- `vs_documents` chỉ lấy 1 mã đáng giá nhất.

## Lỗi thường gặp

`source/date null` trong reports (đặc trưng parse titles) → suy ngày từ URL/title, ghi chú
nguồn ngày "không chắc chắn". Feed rỗng thật (cuối tuần) → empty hợp lệ, nới days 1 lần.

## Bằng chứng live (02-10-2026)

Feed chung **7 reports** — MBB MUA 28,200 · **MSN MUA 89,200 (30/09)** · VPB KHẢ QUAN
30,500 · MSB GIẢM TỶ TRỌNG 13,200 · FRT THEO DÕI 157,000 · filter symbol=VCB/FPT từng empty đúng hiện tượng.

## Nghiệm thu

"CTCK khuyên mua gì tuần này" → bảng ≥5 dòng có upside %, kiểm chứng 2 mã top, ≤8 calls.
```


---

---

## 21 · tim-kiem-tin-tuc
> File thật: `OpenTrading/skills/tim-kiem-tin-tuc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: tim-kiem-tin-tuc
description: Tìm tin theo từ khóa/mã/phạm vi — 3 chế độ (mã / VN / toàn cầu), provenance từng tin.
when_to_use: "Tin về FPT, tin VN hôm nay, tin thế giới về dầu. Không dùng khi: digest tin nóng mặc định (tin-tuc-nong-viet-nam / tin-tuc-nong-quoc-te)."
activation: auto
requires_tools: [mcp__opentrading__news_symbol]
tool_budget: 10
triggers:
  keywords: [tin về, tìm tin, tin tức về, news về, tin trên, dư luận về]
version: 1.0.0
---

# Tìm kiếm tin tức

## Workflow theo chế độ

| Chế độ | Wave | Tools |
|---|---|---|
| **A. Theo mã (+ rumor)** | 1 | `news_symbol(symbol, limit=20)` (Fireant-first, GDELT fallback trong tool — posts giờ CÓ id thật) |
| | 2. Săn web + thread | `web_search`("tên mã" + "đồn"/"tin đồn"/rumor) → `web_fetch` 1–2 URL đáng ngờ nhất · `fireant_thread`(post_id từ `news_symbol` — rumor nằm ở replies, live P17) |
| | 3. Đối chiếu (Fireant mỏng) | `corporate_calendar`(symbol) + `company_events`(symbol) — tin có khớp công bố không? |
| | 4. Dư luận | `sentiment_score`(symbol) |
| **B. VN** | 1 | `news_market(limit=10)` + `corporate_calendar(limit=20)` |
| | 2 | `news_symbol` × 2-3 mã nổi bật nhất |
| **C. Toàn cầu** | 1 | `news_market(sources=gdelt, limit=10)` |
| | 2 | `geo_intel(topic)` hoặc `event_stats(query)` |
| | 3 (có key) | `web_search(query)` → `web_fetch` 1-2 nguồn chính thức |

## Verdict

Bảng tin {tiêu đề · ngày · nguồn · mã/tag liên quan · phân loại catalyst/đồn} + nguồn nào
đang chết (pre-flight). Tin đồn → ghi nhãn "chưa xác nhận", không diễn giải.

## Chống tràn lan

- Mode A không gọi `news_market` nếu `news_symbol` đã ≥5 tin đạt chuẩn.
- GDELT rỗng → THỬ từ khóa English 1 lần rồi kết luận "ít coverage ngôn ngữ đó".
- `web_search` ẩn khi thiếu key → degrade `web_fetch`, không retry.

## Lỗi thường gặp

Cả 2 nguồn news chết → `snapshot_history(kind=news_feed)` cache, GHI RÕ "cache <ngày>".
Fireant posts `id/user null` = đặc trưng payload, không phải lỗi.

## Bằng chứng live (02-10-2026)

`news_symbol("VCB")` → lãi suất VCB 0.1-6% posts · mode C "dầu" — GDELT articles live ·
corporate_calendar VCB → 487 docs.
P17: `fireant_thread`(post PNJ 42088453) → root + **2 replies thật** (parser đã đọc đúng
postID/totalLikes, trước đây id/user null).

## Nghiệm thu

3 input mẫu (mã/VN/global) → mỗi output ≥3 tin có provenance, ≤10 calls, không vượt 4 song song.
```


---

---

## 22 · tin-tuc-nong-quoc-te
> File thật: `OpenTrading/skills/tin-tuc-nong-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: tin-tuc-nong-quoc-te
description: Tin thế giới tác động thị trường + market reaction xác nhận bằng số.
when_to_use: "Tin quốc tế, thị trường Mỹ/Trung hôm nay. Không dùng khi: tin VN (tin-tuc-nong-viet-nam), từ khóa riêng (tim-kiem-tin-tuc chế độ C)."
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 8
triggers:
  keywords: [tin quốc tế, tin thế giới, thị trường mỹ, fed tin, wall street, nasdaq]
version: 1.0.0
---

# Tin nóng quốc tế

## Workflow

| Wave | Tools |
|---|---|
| 1 | `news_market(sources=gdelt)` · `geo_intel`(không topic = global coverage) |
| 2 | `yf_mega_flows` · `world_fear_greed` |
| 3 | `event_stats`(từ khóa tin nổi bật nhất) |

## Verdict

5 headline + market reaction xác nhận bằng SỐ (mega-cap flows, fear/greed, curve nếu liên
quan rates) — tin chưa có reaction thì ghi "thị trường chưa phản ánh".

## Bằng chứng live (02-10-2026)

mega_flows AAPL/MSFT/NVDA OK · fear/greed 70-74 Greed 7 ngày.

## Nghiệm thu

"Tin thế giới" → ≥5 headline + ≥2 mục reaction định lượng.
```


---

---

## 23 · tin-tuc-nong-viet-nam
> File thật: `OpenTrading/skills/tin-tuc-nong-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: tin-tuc-nong-viet-nam
description: Digest tin nóng trong ngày về thị trường/doanh nghiệp VN — headline, phân loại, sentiment.
when_to_use: "Tin chứng khoán hôm nay, có tin gì về VN30. Không dùng khi: tin theo từ khóa/mã cụ thể (tim-kiem-tin-tuc), tin thế giới (tin-tuc-nong-quoc-te)."
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 9
triggers:
  keywords: [tin nóng, tin chứng khoán, tin hôm nay, tin vn, tin doanh nghiệp, headline]
version: 1.0.0
---

# Tin nóng Việt Nam

## Workflow

| Wave | Tools |
|---|---|
| 1 | `news_market`(limit=15) · `corporate_calendar`(limit=20) |
| 2 | `news_symbol` × 2-3 mã xuất hiện nhiều nhất trong tin |
| 3 | `sentiment_score`(mã nóng nhất) · `company_events`(mã đó) |

## Verdict

5-7 headline, mỗi tin: tiêu đề + mã liên quan + phân loại (catalyst/đồn đoãi/tin vĩ mô) +
sentiment nếu đủ dữ kiện + provenance (Fireant/GDELT).

## Chống tràn lan

- Tối đa 3 mã đào thêm ở wave 2 (chọn theo tần suất xuất hiện, không theo cảm tính).
- `sentiment_score` heuristic fallback (thiếu Groq) → ghi nhãn "heuristic", không diễn giải thành "phố tin/bán".

## Lỗi thường gặp

Fireant chết → tự GDELT fallback (trong tool). Cả hai chết → `snapshot_history(kind=news_feed)`
đọc cache 1 ngày, GHI RÕ là cache.

## Bằng chứng live (02-10-2026)

Fireant posts 02-10 (quỹ bình ổn xăng dầu về KBNN; đất nền HN đổi tâm lý; chiến dịch làm
sạch mã số thuế) · `news_symbol("VCB")` → posts lãi suất 0.1-6%.

## Nghiệm thu

"Tin nóng hôm nay" → ≥5 headline có provenance, ≤9 calls.
```


---

---

## 24 · vn-market-basics
> File thật: `OpenTrading/skills/vn-market-basics/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```markdown
---
name: vn-market-basics
description: Kiến thức nền về cơ chế giao dịch thị trường chứng khoán Việt Nam.
when_to_use: Câu hỏi về sàn HOSE/HNX/UPCoM, phiên ATO/liên tục/ATC, biên độ, bước giá, lô giao dịch, chu kỳ thanh toán, loại lệnh.
activation: auto
triggers:
  keywords: [biên độ, bước giá, lô chẵn, lô lẻ, ATO, ATC, loại lệnh, thanh toán T, phiên giao dịch]
version: 1.1.0
---

Trả lời các câu hỏi về cơ chế giao dịch Việt Nam: sàn HOSE / HNX / UPCoM, phiên ATO / liên tục / ATC,
biên độ giá, bước giá, lô giao dịch, chu kỳ thanh toán, loại lệnh (LO, MP, ATO, ATC…).

Quy tắc:
- Quy định thị trường thay đổi theo thời gian (hệ thống KRX, lộ trình CCP, nâng hạng FTSE).
  Luôn nói rõ thông tin là theo hiểu biết của model và có thể đã cũ; khuyên người dùng đối chiếu
  với thông báo chính thức của sở giao dịch hoặc công ty chứng khoán.
- Phân biệt rõ quy định giữa các sàn khi chúng khác nhau.
- Không đưa ra con số giá hay chỉ số thị trường hiện tại.
```
