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
>
> **Bản rewrite skill-creator (06-10-2026, thay thế toàn bộ)** — viết lại cả 26 skills
> từ đầu theo `opencode-skill-creator` (Anthropic skill-creator): `description` pushy
> (what + trigger contexts cụ thể), body theo cấu trúc When to Use / Workflow checklist /
> Template (strict) / Examples — không còn tuân thủ `SKILL-TEMPLATE.md` cũ
> (file đã xóa khỏi repo). Giữ nguyên frontmatter harness, tool names/params, budgets,
> live evidence. Bump minor (`1.0.x→1.1.0`, `1.1.x→1.2.0`). Eval trực tiếp
> 20 queries/skill (không gọi provider ngoài): **520/520 đúng**.
>
> **Bản 06-10-2026 (theo nhánh `MCP-server`)** — `phan-tich-chuyen-sau-1-ma` 1.2.0→1.2.1
> (thêm Step 2b chart pipeline: dùng lại nến trong context → `chart_render` local đính kèm
> verdict); `kiem-chien-luoc-backtest` 1.2.0→1.2.1 (ghi rõ `quant_backtest` deprecated cho
> chiến lược, mọi timing rule qua `backtest_strategies`); `ve-bieu-do-ky-thuat` giữ 1.2.0
> (đã đủ: render/compare/depth + màu/size). Không tạo skills mới — các tên
> `giam-sat-canh-bao`, `quet-thi-truong-tim-co-hoi`, `tim-kiem-web`, `doc-trang-web`,
> `chay-xac-minh-cuoi-phien` hiện chưa tồn tại trong repo OpenTrading.
>
> **Bản 06-10-2026 (fix từ eval live, đợt 1)** — 7 skills thêm guard chọn nguồn đúng
> (eval phát hiện model dùng `vn_crypto_ohlcv` cho cổ phiếu, đi web trực tiếp thay vì
> tool chuyên): `phan-tich-chuyen-sau-1-ma` 1.2.2, `kiem-chien-luoc-backtest` 1.2.2,
> `ve-bieu-do-ky-thuat`/`nhip-dap-crypto`/`tim-kiem-tin-tuc` → 1.2.1,
> `danh-gia-vi-mo-quoc-te`/`bat-on-quoc-gia` → 1.1.1. Chi tiết: `docs/eval-2026-10-06/`.

## Đặc tả frontmatter chung

| Field | Bắt buộc | Ý nghĩa |
|---|---|---|
| `name` | ✔ | slug kebab-case không dấu, ≤64 ký tự, trùng tên folder |
| `description` | ✔ | front-load keywords user hay nói; có "Dùng khi…/Không dùng khi…" + tên skill loại trừ (opencode chỉ thấy field này để routing) |
| `when_to_use` | ✔ (harness) | câu hỏi mẫu + loại trừ chi tiết, mirror vào body `Khi nào dùng` |
| `activation` | ✔ | `auto` (model nạp khi khớp) / `manual` (chỉ /skill <tên>, ví dụ kiem-tra-nguon-du-lieu) |
| `requires_tools` | khuyến khích | skill chỉ hiện trong catalog khi MỌI tool này có mặt (gate theo tool hiện có; single surface, không preset từ 06-10) |
| `tool_budget` | với skill thiết kế | số lần gọi tool tối đa mỗi run; harness chặn cứng 20/lượt; mirror vào `Chống tràn lan` |
| `triggers.keywords` | khuyến khích | pre-routing: khớp keyword → gợi ý skill ở reminder |
| `version` | ✔ | semver (skill-creator 06-10 bump minor → 1.1.0/1.2.0; eval-fix đợt 1 bump → 1.1.1/1.2.1/1.2.2) |

## Bảng tổng quan

| # | Skill | Kích hoạt | Budget | Version | Tools yêu cầu (đã bỏ prefix mcp__) |
|---|---|---|---|---|---|
| 1 | `bat-on-quoc-gia` | auto | 6 | 1.1.1 | geo_intel |
| 2 | `co-ban-chuyen-sau` | auto | 9 | 1.1.0 | financial_detail |
| 3 | `danh-gia-tinh-hinh-chinh-tri-toan-cau` | auto | 8 | 1.1.0 | — |
| 4 | `danh-gia-tinh-hinh-xung-dot` | auto | 9 | 1.1.0 | event_stats |
| 5 | `danh-gia-truoc-bctc` | auto | 10 | 1.1.0 | company_events |
| 6 | `danh-gia-vi-mo-quoc-te` | auto | 10 | 1.1.1 | fred_series |
| 7 | `danh-gia-vi-mo-viet-nam` | auto | 12 | 1.2.0 | vs_indicator_data |
| 8 | `devil-advocate` | auto | — | 1.2.0 | — |
| 9 | `dinh-gia-chuyen-sau` | auto | 7 | 1.1.0 | valuation_run |
| 10 | `du-doan-fed` | auto | 8 | 1.1.0 | world_prediction_odds |
| 11 | `du-doan-polymarket` | auto | 6 | 1.1.0 | world_prediction_odds |
| 12 | `explain-term` | auto | — | 1.2.0 | — |
| 13 | `kiem-chien-luoc-backtest` | auto | 12 | 1.2.2 | quant_backtest |
| 14 | `kiem-tra-nguon-du-lieu` | manual | 12 | 1.1.0 | doctor |
| 15 | `ky-thuat-chuyen-sau` | auto | 8 | 1.2.0 | signals_technical |
| 16 | `nhip-dap-crypto` | auto | 6 | 1.2.1 | crypto_spot |
| 17 | `phan-tich-chuyen-sau-1-ma` | auto | 8 | 1.2.2 | stock_overview |
| 18 | `phan-tich-sentiment` | auto | 6 | 1.1.0 | sentiment_score |
| 19 | `phan-tich-vang-ty-gia` | auto | 10 | 1.2.0 | vn_retail_gold |
| 20 | `so-sanh-cung-nganh` | auto | 8 | 1.2.0 | compare_equities |
| 21 | `tim-co-hoi-bao-cao-ctck` | auto | 8 | 1.2.0 | analyst_consensus |
| 22 | `tim-kiem-tin-tuc` | auto | 10 | 1.2.1 | news_symbol |
| 23 | `tin-tuc-nong-quoc-te` | auto | 8 | 1.1.0 | news_market |
| 24 | `tin-tuc-nong-viet-nam` | auto | 9 | 1.1.0 | news_market |
| 25 | `ve-bieu-do-ky-thuat` | auto | 8 | 1.2.1 | chart_render (local) |
| 26 | `vn-market-basics` | auto | — | 1.2.0 | — |

---

## 1 · bat-on-quoc-gia
> File thật: `OpenTrading/skills/bat-on-quoc-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: bat-on-quoc-gia
description: Đánh giá độ ổn định hoặc bất ổn chính trị của MỘT quốc gia (biểu tình, đảo chính, bất ổn) theo thang 4 mức kèm evidence. Luôn dùng skill này khi user hỏi tình hình ổn định của một nước cụ thể — ví dụ "Thái Lan đang bất ổn gì", "Trung Quốc có ổn định không", "Bangladesh sau đảo chính ra sao" — ngay cả khi user không nói rõ muốn "đánh giá".
activation: auto
requires_tools: [mcp__opentrading__geo_intel]
tool_budget: 6
triggers:
  keywords: [bất ổn, bất ổn quốc gia, biểu tình, đảo chính, ổn định, thái lan, bangladesh]
version: 1.1.1
```


# Assessing Single-Country Stability

Đánh giá 1 quốc gia theo thang ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG, mỗi mức kèm evidence có URL. Hỏi nhiều nước thì chạy lặp skill này mỗi nước 1 lượt thay vì gộp.

## When to Use

- Dùng khi: user nêu tên MỘT quốc gia + hỏi bất ổn/ổn định/biểu tình/đảo chính.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - So sánh/bản đồ nhiều nước, bầu cử/chính sách toàn cầu → `danh-gia-tinh-hinh-chinh-tri-toan-cau`.
  - Chiến sự/xung đột vũ trang + ảnh hưởng thị trường → `danh-gia-tinh-hinh-xung-dot`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: đo cường độ (GDELT counts + mức độ)
- [ ] Step 2: xác minh bằng tin (chỉ khi Step 1 mỏng)
- [ ] Step 3: verdict 4 mức + provenance
```

**Step 1: Đo cường độ (bắt buộc).**

Chạy song song 2 calls cùng upstream GDELT: `geo_intel` (topic = tên nước tiếng Anh) + `event_stats` (query = tên nước tiếng Anh). CẤM đi web_search/web_fetch trước khi có counts GDELT — web chỉ dùng ở Step 2 khi Step 1 mỏng. Query tiếng Anh 1 lần + tối đa 1 biến thể; query tiếng Việt rỗng là đặc trưng data, không phải lỗi. GDELT rate-limit thì retry tối đa 1 lần sau backoff (server đã cache 600s); vẫn lỗi thì ghi trung thực và verdict dựa trên dữ liệu cũ.

**Step 2: Xác minh bằng tin (chỉ khi Step 1 mỏng).**

Chạy `news_market` (sources=gdelt, lọc theo tên nước) tuần tự sau Step 1. Đủ counts + titles ở Step 1 thì dừng, không chạy Step 2. Coverage mỏng là KẾT QUẢ ("low-coverage ≠ stable"), không suy diễn thành ỔN ĐỊNH.

**Step 3: Chốt verdict.**

Chỉ thêm `yf_commodities` hoặc `assets_rotation` (1 call) khi user hỏi rõ "ảnh hưởng thị trường". Tối đa 6 calls/run vì mỗi call ngoài tốn quota còn làm verdict loãng — dừng ngay khi đủ evidence.

## Template

ALWAYS use this exact verdict structure:

1. **Verdict 4 mức (chỉ chọn 1):** ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG.
2. **Căn cứ (mỗi mục 1 dòng + URL):** tần suất event GDELT (run này là baseline) · mức độ (keywords protest/conflict/coup trong titles) · coverage nước láng giềng · transmission sang giá nếu có Step phụ (dầu/vàng, đơn vị USD/oz hoặc % move).
3. **Provenance:** mỗi mục bắt buộc 1 dòng evidence + URL nguồn.

## Examples

**Example 1:**
Input: Bất ổn Thái Lan
Output:
```
Verdict: CẢNH BÁO
- Tần suất event GDELT tăng vs baseline ... + URL
- Mức độ: keywords protest xuất hiện ... + URL
- Coverage nước láng giềng: ...
Provenance: (1 dòng evidence + URL cho mỗi mục trên)
```

**Example 2 (coverage mỏng):**
Input: Bất ổn Lào
Output: Verdict kèm ghi chú trung thực "low-coverage ≠ stable", không suy diễn thành ỔN ĐỊNH.
---

## 2 · co-ban-chuyen-sau
> File thật: `OpenTrading/skills/co-ban-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: co-ban-chuyen-sau
description: Đọc BCTC và đánh giá chất lượng cơ bản của 1 mã (M-Score thao túng, F-score, tăng trưởng, sở hữu, cổ tức) trong tối đa 9 calls. Luôn dùng skill này khi user hỏi đọc BCTC, chất lượng lợi nhuận, M-Score, cổ đông lớn, insider hay cổ tức của một mã — ví dụ "BCTC FPT có gì lạ", "VCB có thao túng không", "cổ đông lớn HPG" — ngay cả khi user không nói rõ muốn "phân tích cơ bản".
activation: auto
requires_tools: [mcp__opentrading__financial_detail]
tool_budget: 9
triggers:
  keywords: [bctc, báo cáo tài chính, cơ bản, lợi nhuận gộp, nợ phải trả, vốn chủ, m-score, thao túng, cổ đông lớn, cổ tức, kế hoạch kinh doanh]
version: 1.1.0
```

# Analyzing Single-Stock Fundamentals

Phân tích THUẦN cơ bản 1 mã theo aspect: hỏi khía cạnh nào thì chỉ chạy leg đó rồi dừng — đừng quét hết BCTC vì "cho chắc".

## When to Use

- Dùng khi: user hỏi BCTC, chất lượng lợi nhuận, M-Score/thao túng, F-score, kế hoạch kinh doanh, cổ đông lớn, insider, cổ tức của 1 mã.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Hỏi kỹ thuật (RSI, MACD, breakout, hỗ trợ/kháng cự) → `ky-thuat-chuyen-sau`.
  - Hỏi định giá (fair value, PER, upside) → `dinh-gia-chuyen-sau`.
  - So sánh 2-6 mã → `so-sanh-cung-nganh`.
  - Phân tích toàn diện 1 mã → `phan-tich-chuyen-sau-1-ma`.
  - Đọc báo cáo CTCK (không phải BCTC gốc) → `tim-co-hoi-bao-cao-ctck`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 0: kiểm tra JWT sống hay chết
- [ ] Step 1: lõi BCTC + chất lượng (aspect chataluong dừng tại đây)
- [ ] Step 2-3: chỉ chạy aspect user hỏi (trend/ratios, sở hữu/kế hoạch)
- [ ] Step 4: chốt verdict 7 mục + provenance
```

**Step 0: Kiểm tra JWT (bắt buộc, gọi trực tiếp đầu tiên).**

Chạy `vs_auth_status`. JWT sống thì được dùng `financial_detail`; JWT chết thì chuyển nhánh mirror `vs_financeinfo` — hai tool này không bao giờ chạy song song vì cùng một nguồn số.

**Step 1: Lõi BCTC + chất lượng.**

Chạy song song 2 calls: `financial_detail` (statement=KQKD, periods_n=4) + `stock_forensic` (symbol). Nếu user chỉ hỏi chất lượng (`chataluong`) thì dừng ngay tại đây.

**Step 2: Mở rộng theo aspect (mỗi aspect là 1 leg, chỉ chạy leg được hỏi).**

- Trend/ratios: `financial_statements` · `financial_ratios` · `vn_fundamentals` (tối đa 3 calls).
- Sở hữu/kế hoạch (`sohuu`/`cophieu`/`kehoach`): `planned_targets` · `holders` · `insider_trading` · `dividends_splits` (+ Step 1 nếu cần nền).
- Tham chiếu: `vs_financial_norms` / `vs_financial_terms` / `vs_company_info` — chỉ khi cần giải thích norm_id/kỳ.
- Không bao giờ gọi `vs_documents` ở đây (đó là tool của `tim-co-hoi-bao-cao-ctck). LCTT/CDKT chỉ gọi khi user hỏi explicitly dòng tiền/bảng cân đối qua param `statement`.

**Step 3: Validate trước khi chốt verdict.**

Leg nào rỗng thì verdict partial + ghi rõ nguồn thiếu, không bịa số lấp chỗ trống. Bank cho M partial (SGAI null do LCTT rỗng — VCB live) thì ghi "M không kết luận", không gán M=0. `financial_detail` periods vượt gói → rows rỗng + warning → degrade sang `vs_financeinfo` đúng 1 lần, ghi rõ fallback. `vn_company` chậm ~30s khi throttle thì đặt cuối, thiếu thì ghi thiếu.

## Template

ALWAYS use this exact verdict structure, mỗi mục ghi số + trend + provenance:

1. Chất lượng tăng trưởng: DT/LN 4 quý + trend QoQ/YoY + biên (`provenance: financial_detail`).
2. Ratios chủ chốt (`provenance: financial_ratios` / `vn_fundamentals`).
3. M-Score + F-score + red flags (`provenance: stock_forensic`).
4. So với kế hoạch: vượt/hụt % (`provenance: planned_targets`).
5. Cấu trúc sở hữu + thay đổi insider (`provenance: holders` / `insider_trading`).
6. Chính sách cổ tức (`provenance: dividends_splits`).
7. Kết luận 1 câu: CƠ BẢN TỐT/TRUNG BÌNH/YẾU + 3 rủi ro lớn nhất.

## Examples

**Example 1:**
Input: BCTC FPT có gì lạ
Output (Wave 1 đủ, 2 calls): M-Score/F-score + 4 quý DT/LN + verdict 7 mục, không mở Wave 3–4.

**Example 2 (live 02-10-2026, không bịa số mới):**
Input: cơ bản FPT
Output: FPT detail 25 norms × 138 số · M **−2.06**, F 2/6 · KH DT 61,850/75,400/58,580 · VCB holders SBV 74.8% · VCB cổ tức 450đ · insider empty là đúng data.
---

## 3 · danh-gia-tinh-hinh-chinh-tri-toan-cau
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-chinh-tri-toan-cau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-tinh-hinh-chinh-tri-toan-cau
description: Vẽ bản đồ rủi ro chính trị toàn cầu (bầu cử, chính sách, căng thẳng quốc tế) 4-6 mục, mỗi mục có xác suất odds + tin GDELT xác nhận + URL. Luôn dùng skill này khi user hỏi rủi ro chính trị/bầu cử/chính sách ở quy mô nhiều nước — ngay cả khi user không nói rõ muốn "bản đồ rủi ro".
activation: auto
tool_budget: 8
triggers:
  keywords: [địa chính trị, bầu cử, chính trị, chính sách mỹ, căng thẳng quốc tế, rủi ro chính trị]
version: 1.1.0
```

# Mapping Global Political Risk

Skill tổ chức cross-ref (không có home tool riêng — ghép odds + tin từ nhiều nguồn). Mỗi mục verdict bắt buộc có event URL + tin URL, thiếu một trong hai thì ghi rõ.

## When to Use

- Dùng khi: user hỏi bản đồ rủi ro chính trị toàn cầu, bầu cử, chính sách, căng thẳng quốc tế (nhiều sự kiện, cần ghép odds + tin).
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Xung đột vũ trang cụ thể → dùng `danh-gia-tinh-hinh-xung-dot`.
  - Bất ổn 1 nước → dùng `bat-on-quoc-gia`.
  - Chỉ xin odds/bảng Polymarket thuần → dùng `du-doan-polymarket`.
  - Fed cắt/giữ thuần → dùng `du-doan-fed`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: odds + intel song song
- [ ] Step 2: drill-down event liên quan (tối đa 2 slugs)
- [ ] Step 3: xác minh tin (1-2 nguồn chính thức)
- [ ] Step 4: verdict 4-6 mục + provenance
```

**Step 1: Odds + intel (song song, bắt buộc).**

Chạy `world_prediction_odds` (tag=fed/politics/elections theo câu hỏi) + `geo_intel` (topic). Odds đã sort vol24h nên chỉ lấy top 5 — kéo cả 20 events là tràn lan.

**Step 2: Drill-down (song song, tuần tự sau Step 1).**

Chạy `polymarket_event` (slug top 1-2) + `event_stats` (query). Chỉ drill event thật sự liên quan câu hỏi, tối đa 2 slugs/run. Không gọi chồng chéo `geo_intel` + `event_stats` + `news_market` cùng query quá 1 vòng.

**Step 3: Xác minh tin (tuần tự sau Step 2).**

Chạy `news_market` (sources=gdelt) + `web_fetch` 1-2 URL nguồn chính thức trong tin. Đủ 4 mục có prob + tin xác nhận thì dừng.

**Step 4: Validate trước khi chốt.**

GDELT rate-limit → backoff 20s, retry tối đa 1 lần → vẫn lỗi thì ghi trung thực "thiếu tin GDELT, verdict chỉ dựa trên odds". Gamma chậm thì tool tự fallback direct, chờ 1 lần. Odds stale (end-date qua) → lọc `end > today`, loại event hết hạn. Hai đường chết hết thì ghi "không có odds", không bịa xác suất.

## Template

ALWAYS use this exact verdict structure:

1. **Sự kiện:** tên + bối cảnh 1 dòng.
2. **Xác suất:** prob_pct từng outcome (đơn vị %) + end-date.
3. **Độ tin odds:** volume 24h + liquidity (đơn vị USD; <50k thì cờ "odds kém tin").
4. **Tin GDELT xác nhận:** 1 dòng + URL.
5. **Market-impact nếu có:** kênh truyền dẫn + URL.
6. **Provenance:** mỗi mục bắt buộc event URL + tin URL.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Rủi ro chính trị toàn cầu
Output: Fed October 2026 "no change" 74.5% (volume 24h ~2.6M USD) · Brazil presidential event OK · mỗi mục đủ prob_pct + provenance event URL.
---

## 4 · danh-gia-tinh-hinh-xung-dot
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-xung-dot/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-tinh-hinh-xung-dot
description: Đánh giá 1 cuộc xung đột vũ trang (cường độ, giá dầu/vàng đã phản ánh chưa, kênh truyền dẫn, xác suất leo thang) trong tối đa 9 calls. Luôn dùng skill này khi user hỏi xung đột/chiến sự cụ thể và ảnh hưởng của nó tới thị trường — ví dụ "Trung Đông leo thang, dầu lên không", "Biển Đông căng thẳng ảnh hưởng gì" — ngay cả khi user không nói rõ muốn "đánh giá xung đột".
activation: auto
requires_tools: [mcp__opentrading__event_stats]
tool_budget: 9
triggers:
  keywords: [xung đột, chiến tranh, biển đông, trung đông, leo thang, dầu hay vàng lên, chiến sự]
version: 1.1.0
```

# Assessing Armed-Conflict Market Impact

Trả lời 5 mục cố định: cường độ → giá đã phản ánh → kênh truyền dẫn → xác suất leo thang → hàm ý vị thế. Không khuyến nghị mua/bán trực tiếp.

## When to Use

- Dùng khi: user nêu 1 xung đột/chiến sự cụ thể + hỏi cường độ, leo thang, giá đã phản ánh, kênh truyền dẫn, hàm ý vị thế.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Chính trị/bầu cử rộng → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.
  - Bất ổn 1 nước (biểu tình/đảo chính, chưa thành chiến sự) → dùng `bat-on-quoc-gia`.
  - Chỉ xin odds thuần → dùng `du-doan-polymarket`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: đo cường độ (GDELT, song song)
- [ ] Step 2: kiểm tra giá đã phản ánh (dầu/vàng, song song)
- [ ] Step 3: odds leo thang + xác minh (chỉ khi cần)
- [ ] Step 4: verdict 5 mục
```

**Step 1: Đo cường độ (bắt buộc, song song).**

Chạy `geo_intel` (topic xung đột) + `event_stats` (query) cùng lúc. Từ khóa thử cả tiếng Việt lẫn Anh; GDELT rỗng với tiếng Việt là đặc trưng data (ghi "query VN rỗng, dùng EN query X", retry tối đa 1 lần EN), không phải lỗi.

**Step 2: Kiểm tra giá đã phản ánh (song song, tuần tự sau Step 1).**

Chạy `yf_commodities` (dầu + vàng) + `assets_rotation`. Thiếu phiên mới thì dùng phiên gần nhất có + ghi rõ date, không bịa giá hiện tại. Đủ counts Step 1 + giá dầu/vàng Step 2 là đủ verdict cơ bản.

**Step 3: Odds leo thang + xác minh (chỉ khi cần).**

Chạy `world_prediction_odds` (từ khóa cuộc chiến) + `web_search`/`web_fetch` (chỉ 1-2 nguồn). Không có market cho cuộc chiến thì ghi "không có odds", không thay bằng nhận định riêng.

**Step 4: Validate trước khi chốt.**

Chỉ 1 topic/call; từ khóa tối đa 2 lần thử ("biển đông" → "south china sea") rồi chấp nhận "ít coverage". Không mở rộng sang nhiều cuộc chiến trong 1 run (user hỏi rộng thì đề nghị tách từng xung đột).

## Template

ALWAYS use this exact verdict structure:

1. **Cường độ:** event counts GDELT trend (đơn vị counts + trend tăng/giảm) + URL.
2. **Giá đã phản ánh chưa:** dầu/vàng move vs baseline (đơn vị USD/thùng, USD/oz, % move) + URL.
3. **Kênh truyền dẫn:** energy → inflation → rates, 1–2 dòng + URL.
4. **Xác suất leo thang:** odds prob_pct (đơn vị %) + end-date + URL event.
5. **Hàm ý vị thế:** cushion/size (tham chiếu leg 6 `danh-gia-truoc-bctc`), KHÔNG khuyến nghị mua/bán trực tiếp.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Xung đột ảnh hưởng dầu/vàng
Output: `geo_intel("Vietnam")` trả articles · `event_stats("vietnam")` articles >0 · gold 4,195 USD/oz cùng phiên → verdict đủ 5 mục, có số dầu/vàng phiên gần nhất.
---

## 5 · danh-gia-truoc-bctc
> File thật: `OpenTrading/skills/danh-gia-truoc-bctc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-truoc-bctc
description: Chấm grade A/B/C cho setup 1 mã trước thềm BCTC từ 6 leg (ngày công bố, trend, thao túng, kỳ vọng, positioning, đệm định giá). Luôn dùng skill này khi BCTC chưa ra mà user hỏi có nên mua/giữ qua báo cáo không — ví dụ "FPT sắp ra báo cáo có nên mua", "setup HPG trước BCTC ra sao" — ngay cả khi user không nói rõ muốn "đánh giá setup".
activation: auto
requires_tools: [mcp__opentrading__company_events]
tool_budget: 10
triggers:
  keywords: [trước bctc, sắp ra báo cáo, pre earnings, công bố lợi nhuận, setup bctc]
version: 1.1.0
```

# Grading Pre-Earnings Setup

Chấm grade cho setup trước BCTC. Không forecast KQKD — không bao giờ đưa số DT/LN dự báo. BCTC đã ra rồi thì dừng ngay, chuyển sang `co-ban-chuyen-sau`, không cố chấm grade.

## When to Use

- Dùng khi: BCTC chưa ra và user hỏi setup trước BCTC (`FPT sắp ra báo cáo`, `đánh giá setup HPG trước BCTC`, `pre-earnings`).
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Phân tích mã thường (không gắn BCTC) → `phan-tich-chuyen-sau-1-ma`.
  - BCTC đã công bố, cần đọc số/M-Score → `co-ban-chuyen-sau`.
  - Hỏi kỹ thuật lẻ → `ky-thuat-chuyen-sau`.
  - Hỏi định giá lẻ → `dinh-gia-chuyen-sau`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: chốt ngày BCTC (dated hay rumor)
- [ ] Step 2: reuse trend + thao túng từ co-ban-chuyen-sau
- [ ] Step 3: kỳ vọng + positioning (gọi trực tiếp)
- [ ] Step 4: reuse đệm định giá + grade A/B/C
```

**Step 1: Chốt ngày BCTC (bắt buộc, gọi trực tiếp đầu tiên).**

Chạy `company_events` + `event_calendar_vn`. Chưa rõ ngày thì các leg còn lại ghi `unknown ngày` và grade tối đa B.

**Step 2: Reuse trend + thao túng (không gọi tool gốc).**

LOAD `co-ban-chuyen-sau` aspect=baokao (trend) và aspect=chataluong (M-Score/Piotroski). Lý do reuse thay vì gọi trực tiếp `financial_detail`/`stock_forensic`: tránh gọi chồng chéo cùng nguồn số trong 1 run. Ghi rõ aspect reuse ở từng leg.

**Step 3: Kỳ vọng + positioning (gọi trực tiếp).**

Chạy `planned_targets` + `analyst_consensus` + `news_symbol` + `sentiment_score` (anchor = kế hoạch DN vì VN không có consensus EPS; sentiment là heuristic, không tính là leg xanh) và `insider_trading` + `money_flow` + `block_trades`.

**Step 4: Reuse đệm định giá + chấm grade.**

LOAD `dinh-gia-chuyen-sau` + chạy `scenario_simulate` (−5%) để lấy size gợi ý. Không gọi trực tiếp `valuation_run` ở đây. Đủ 6 leg evidence (kể cả partial) thì dừng — không gọi thêm vòng tin/dòng tiền thứ hai, không thêm leg thứ 7.

## Template

ALWAYS use this exact verdict structure:

1. Grade **A/B/C** (rubric: A = ≥5 leg xanh + M-Score sạch + KH rõ; B = 4–5 leg; C = <4 leg hoặc M-Score đỏ > −1.78).
2. 1 dòng evidence/leg (6 dòng, mỗi dòng số + trend + provenance).
3. Size đề xuất (từ `scenario_simulate` −5%).
4. Unknowns tường minh (liệt kê điều chưa biết).
5. Kết luận 1 câu: grade + có nên giữ/mua trước BCTC + rủi ro lớn nhất.

Partial data (thiếu positioning hoặc kỳ vọng) → verdict partial + unknowns. `sentiment_score` âm/dương nhẹ thì ghi đúng là heuristic, không nâng thành leg xanh/đỏ.

## Examples

**Example 1 (live 02-10-2026, FPT, không bịa số mới):**
Input: Đánh giá trước BCTC HPG
Output: M **−2.06** sạch · F 2/6 · KH DT 61,850/75,400/**58,580** · thưởng CP 10:1 ex 21-09 · sentiment heuristic −0.25 · NN bán ròng · pt 0% phiên → grade B + 6 leg evidence + unknowns, ≤10 calls (reuse legs).
---

## 6 · danh-gia-vi-mo-quoc-te
> File thật: `OpenTrading/skills/danh-gia-vi-mo-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-vi-mo-quoc-te
description: Đọc chu kỳ kinh tế Mỹ và chế độ rủi ro toàn cầu (soft/hard landing, đường cong lợi suất, RISK-ON/OFF, so VN-vs-global) trong tối đa 10 calls. Luôn dùng skill này khi user hỏi bối cảnh vĩ mô Mỹ/global, việc làm, GDP các nước, risk regime — ví dụ "kinh tế Mỹ soft landing không", "yield curve đảo chưa" — ngay cả khi user không nói rõ muốn "đánh giá vĩ mô".
activation: auto
requires_tools: [mcp__opentrading__fred_series]
tool_budget: 10
triggers:
  keywords: [kinh tế mỹ, recession, suy thoái, đường cong lợi suất, yield curve, risk-on, risk-off, fed bối cảnh, kinh tế toàn cầu]
version: 1.1.1
```


# Reading US and Global Macro Regime

Đi 3 wave tuần tự (mỗi wave song song bên trong): chu kỳ Mỹ → chế độ rủi ro → xác nhận toàn cầu. FRED gọi theo tên chuẩn; thiếu key thì chuyển nhánh không-FRED thay vì bỏ cả verdict.

## When to Use

- Dùng khi: user hỏi chu kỳ Mỹ (soft/hard landing), đường cong lợi suất, việc làm/GDP các nước, chế độ rủi ro toàn cầu, so sánh VN-vs-global.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Vĩ mô VN chi tiết (GDP/CPI/XNK/SBV) → dùng `danh-gia-vi-mo-viet-nam`.
  - Xác suất Fed cắt/giữ/tăng thuần odds + lịch FOMC → dùng `du-doan-fed`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: chu kỳ Mỹ (FRED + curve, song song)
- [ ] Step 2: chế độ rủi ro (song song)
- [ ] Step 3: xác nhận toàn cầu (song song)
- [ ] Step 4: verdict 5 mục
```

**Step 1: Chu kỳ Mỹ (song song).**

Chạy `fred_series` (DGS10) + `fred_series` (CPIAUCSL) + `yf_yield_curve`. CẤM đi web_search/web_fetch trước khi gọi tool chuyên — web chỉ bổ sung sau khi đã có số FRED. FRED thiếu key → trả unavailable → chuyển nhánh không-FRED (dùng `yf_yield_curve` + `yf_global_indices`) + ghi chú trung thực thiếu series nào. Curve flaky thì retry tối đa 1 lần sau backoff rồi bỏ.

**Step 2: Chế độ rủi ro (song song, tuần tự sau Step 1).**

Chạy `yf_regime_assets` + `assets_rotation` + `world_macro_country` (VN/CHINA theo câu hỏi). Nhóm `yf_*` tối đa 3 calls/wave; không gọi chồng chéo `yf_yield_curve` + `fred_series` quá 1 vòng. `world_macro_country` rỗng thì đổi mã nước 1 lần rồi chấp nhận "ít coverage".

**Step 3: Xác nhận toàn cầu (song song, tuần tự sau Step 2).**

Chạy `yf_global_indices` + `yf_commodities` + `world_fear_greed`. Đủ DGS10 + CPI + curve ở Step 1 mới sang Step 2; gọi ≥3 FRED series cùng lúc là dấu hiệu tràn lan → dừng.

## Template

ALWAYS use this exact verdict structure:

1. **Chu kỳ Mỹ:** soft/hard landing, dựa DGS10 + CPI + curve, đơn vị % lợi suất + % CPI + URL.
2. **Đường cong:** inverted hay không, chênh 10Y-2Y (đơn vị bps/%) + URL.
3. **Chế độ toàn cầu:** RISK-ON/OFF từ rotation/regime assets + URL.
4. **So VN-vs-global:** bắt buộc 1 dòng so sánh GDP VN (đơn vị % WorldBank) vs global + URL.
5. **Biến số theo dõi:** liệt kê CPI Mỹ, jobs, lợi suất cần watch tiếp theo.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Kinh tế Mỹ hiện tại
Output: US10Y 5.24% / 2Y 4.61%, không đảo chiều · WorldBank GDP VN 8.02% · fear/greed crypto 70-74 (tham lam) → verdict đủ 5 mục, curve + ≥2 series FRED có số.
---

## 7 · danh-gia-vi-mo-viet-nam
> File thật: `OpenTrading/skills/danh-gia-vi-mo-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-vi-mo-viet-nam
description: Đọc vĩ mô Việt Nam (GDP, CPI, XNK, tỷ giá USDVND, lãi suất SBV, câu chuyện dẫn dắt thị trường + lịch sự kiện) trong tối đa 12 calls. Luôn dùng skill này khi user hỏi số liệu, bối cảnh hoặc lịch công bố vĩ mô VN — ví dụ "GDP quý này bao nhiêu", "lãi suất SBV bao nhiêu" — ngay cả khi user không nói rõ muốn "đánh giá vĩ mô".
activation: auto
requires_tools: [mcp__opentrading__vs_indicator_data]
tool_budget: 12
triggers:
  keywords: [vĩ mô, GDP, CPI, lạm phát, xuất khẩu, nhập khẩu, lãi suất điều hành, sbv, xnk, cán cân, câu chuyện thị trường, dẫn dắt]
version: 1.2.0
```

# Reading Vietnam Macro

Mở đầu bắt buộc bằng pre-flight 2 calls (source_status + vs_auth_status) vì macro VN phụ thuộc JWT và HAR-session dễ chết. Cặp category/termType phải đúng tuyệt đối (sai là rows rỗng): GDP 73/tt3, CPI 15/tt7/sub2, XK 38/tt2.

## When to Use

- Dùng khi: user hỏi số liệu VN (GDP/CPI/XK/NK), lãi suất SBV, tỷ giá USDVND bối cảnh vĩ mô, lịch công bố NSO, báo cáo vĩ mô CTCK, câu chuyện dẫn dắt thị trường VN.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Vĩ mô Mỹ/toàn cầu, Fed bối cảnh, risk regime → dùng `danh-gia-vi-mo-quoc-te`.
  - Xác suất Fed cắt/giữ thuần odds → dùng `du-doan-fed`.
  - Thao tác vàng-tỷ giá chi tiết → dùng `phan-tich-vang-ty-gia`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 0: pre-flight nguồn (song song)
- [ ] Step 1: data VN bắt buộc (categories trước, indicators song song)
- [ ] Step 2: tin vĩ mô (song song)
- [ ] Step 3: báo cáo CTCK (1 call feed chung)
- [ ] Step 4: data bổ sung + lịch sự kiện
- [ ] Step 5: verdict 6 mục + câu chuyện
```

**Step 0: Pre-flight (song song, bắt buộc).**

Chạy `source_status` + `vs_auth_status` trước mọi wave.

**Step 1: Data VN bắt buộc.**

Chạy `vs_categories` trước (tra id nếu chưa chắc), rồi song song `vs_indicator_data` GDP + CPI + XK và `vs_xnk_detail` (chỉ 1 direction xk hoặc nk theo câu hỏi). Rows rỗng → kiểm tra lại cặp id, retry tối đa 1 lần → vẫn rỗng thì ghi "không có số liệu kỳ này".

**Step 2: Tin vĩ mô (song song).**

Chạy `news_market` (lọc vĩ mô/lãi suất/tỷ giá) + `macro_events_vn` + `economic_calendar`.

**Step 3: Báo cáo CTCK (1 call duy nhất).**

Chạy `analyst_consensus` (report_type=macro, limit=30) feed chung; lấy section pointers + dated reports. Không bắn theo từng từ khóa.

**Step 4: Data bổ sung + lịch (song song, mỗi thứ tối đa 1 call).**

Chạy `snapshot_history` (macro_curated) + `yf_yield_curve` + `sbv_rates` + `vn_retail_fx` + `macro_events_vn` (NSO) + kỳ họp Fed/Mỹ (cross-ref `du-doan-fed`). Thiếu HAR session → macro trả permission message: ghi trung thực "macro cần session", fallback sang `snapshot_history`, không diễn giải message permission thành dữ liệu. Curve/DXY flaky → retry 1 lần sau backoff rồi bỏ.

## Template

ALWAYS use this exact verdict structure:

1. **Tăng trưởng:** GDP, ≥8 điểm cuối, đơn vị % yoy + URL/provenance.
2. **Lạm phát:** CPI, ≥8 điểm cuối, đơn vị % yoy + URL.
3. **Thương mại:** XK/NK/XNK-detail, đơn vị triệu USD + URL.
4. **Tỷ giá:** USDVND (đơn vị VND), SBV rates (tái cấp vốn/tái chiết khấu, đơn vị %) + URL.
5. **Lãi suất:** lãi suất điều hành SBV + bối cảnh hút vốn ngoại (curve/DXY) + URL.
6. **Điểm tích cực / tiêu cực + triển vọng tương lai.**
7. **Câu chuyện dẫn dắt thị trường + lịch sự kiện** (mỗi câu chuyện: sự kiện nào, ngày nào, tác động gì).

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Vĩ mô VN
Output: GDP 504 rows tới Q2/2026 · CPI 1,839 · XK 2,941 · XNK-country 3,675 · SBV tái cấp vốn 4.5% / tái chiết khấu 3% · USDVND 25,970 · NSO lịch CPI tháng 8 → verdict đủ 6 mục + câu chuyện dẫn dắt có lịch sự kiện, ≤12 calls.
---

## 8 · devil-advocate
> File thật: `OpenTrading/skills/devil-advocate/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: devil-advocate
description: "Phản biện luận điểm đầu tư để chống thiên kiến xác nhận: tóm tắt luận điểm, nêu 3-5 lý do nó có thể SAI kèm dấu hiệu theo dõi, điều kiện phủ định. Luôn dùng skill này khi user hỏi về mã họ đang nắm hoặc đã thích, xin ý kiến mua/giữ, hoặc yêu cầu phản biện/bear case — ví dụ 'đang giữ HPG có nên giữ không', 'bear case cho VCB là gì' — ngay cả khi user không nói rõ muốn 'phản biện'."
activation: auto
triggers:
  keywords: [phản biện, bear case, có nên giữ, rủi ro gì, đang nắm, đang giữ]
version: 1.2.0
```

# Countering Investment Bias

Người dùng hỏi về cổ phiếu họ đã mua hoặc đã thích thì mặc định họ đang thiên kiến xác nhận — nhiệm vụ là phản biện, không phải chê bai hay kết luận thay. Giọng trung lập, không mỉa mai.

## When to Use

- Dùng khi: user nói đang nắm/đang giữ một mã, hỏi có nên giữ không, rủi ro gì, xin bear case, hoặc yêu cầu phản biện luận điểm mua/giữ.
- Khi KHÔNG dùng (dùng skill khác thay thế): hỏi định nghĩa thuật ngữ (dùng `explain-term`); xin chart/nến (dùng `ve-bieu-do-ky-thuat`); hỏi cơ chế sàn/phiên/biên độ (dùng `vn-market-basics`).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: tóm tắt luận điểm (xác nhận hiểu đúng)
- [ ] Step 2: 3-5 lý do có thể SAI + dấu hiệu theo dõi
- [ ] Step 3: điều kiện phủ định
```

**Step 1: Tóm tắt luận điểm trong 1–2 câu.**

Xác nhận hiểu đúng trước khi phản biện; không bóp méo luận điểm để dễ bác bỏ.

**Step 2: Liệt kê 3–5 lý do mạnh nhất khiến luận điểm có thể SAI.**

Phủ 5 mặt: ngành, doanh nghiệp, định giá, vĩ mô, thanh khoản. Mỗi lý do kèm 1 dấu hiệu cụ thể cần theo dõi (chỉ số/sự kiện nào cho thấy rủi ro đang xảy ra) — phản biện không có dấu hiệu theo dõi là phản biện chung chung, vô dụng.

**Step 3: Nêu điều kiện phủ định.**

Sự kiện nào xảy ra thì luận điểm nên bị bỏ. Không kết luận mua/bán thay user.

## Template

ALWAYS use this exact output structure: luận điểm tóm tắt (1–2 câu) · 3–5 rủi ro + dấu hiệu theo dõi từng cái · điều kiện phủ định (khi nào nên bỏ luận điểm).

## Examples

**Example 1:**
Input: đang giữ HPG, có nên giữ không
Output: tóm tắt 1–2 câu + 3–5 rủi ro có dấu hiệu + điều kiện phủ định, giọng trung lập, không khuyến nghị mua/bán.

**Anti-pattern (không làm thế này):** chỉ khen theo user để xác nhận thiên kiến; tự kết luận "nên bán".
---

## 9 · dinh-gia-chuyen-sau
> File thật: `OpenTrading/skills/dinh-gia-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: dinh-gia-chuyen-sau
description: "Tính vùng fair value và UPSIDE/DOWNSIDE % cho 1 mã (PER/PB, so lịch sử 2-3 năm). Luôn dùng skill này khi user hỏi mã đắt hay rẻ, fair value bao nhiêu, upside còn bao nhiêu — ví dụ 'FPT đắt chưa', 'VCB fair value' — ngay cả khi user không nói rõ muốn 'định giá'."
activation: auto
requires_tools: [mcp__opentrading__valuation_run]
tool_budget: 7
triggers:
  keywords: [định giá, fair value, dcf, per, đắt hay rẻ, upside, giá mục tiêu tự tính, valuation]
version: 1.1.0
```

# Valuing Single-Stock Fair Value

Trả về đúng 6 mục: giá vs vùng fair → PER/PB vs lịch sử → vì sao rẻ/đắt → UPSIDE/DOWNSIDE % → neo target CTCK → kết luận 1 câu. EPS âm (công ty lỗ) thì per_pb vô nghĩa — nói thẳng không đủ cơ sở định giá thay vì bịa fair value.

## When to Use

- Dùng khi: user hỏi định giá 1 mã (`FPT đắt chưa`, `VCB fair value`, `định giá theo PER`, `upside còn bao nhiêu`).
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - So sánh nhiều mã → `so-sanh-cung-nganh`.
  - Cơ bản thuần (BCTC, M-Score, sở hữu) → `co-ban-chuyen-sau`.
  - Kỹ thuật thuần → `ky-thuat-chuyen-sau`.
  - Giá mục tiêu của CTCK (tổng hợp báo cáo sẵn có) → `tim-co-hoi-bao-cao-ctck` (chỉ cross-ref để neo kỳ vọng, không thay thế định giá tự tính).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: fair value lõi (song song)
- [ ] Step 2: neo lịch sử (song song)
- [ ] Step 3: bối cảnh lãi suất (chỉ bank/PB-heavy)
- [ ] Step 4: verdict 6 mục
```

**Step 1: Fair value lõi (song song, gọi trực tiếp).**

Chạy `valuation_run` (symbol, method mặc định auto — chỉ đổi method khi user khăng khăng) + `vs_overview_trading` (symbol).

**Step 2: Neo lịch sử (song song, gọi trực tiếp).**

Chạy `financial_ratios` (symbol) + `vn_quote_history` (symbol, days=365), tự tính PER/PB trung bình 2–3 năm. Thiếu lịch sử giá thì bỏ so lịch sử, verdict partial + ghi thiếu.

**Step 3: Bối cảnh lãi suất (chỉ khi cần).**

Chạy `yf_yield_curve` + `vs_trading_info` khi mã PB-heavy (bank). Có fair value + so lịch sử thì dừng, không mở Step 3 để câu giờ. Một `method` mỗi run; `method` sai enum → warning → về auto, không retry method lạ.

**Step 4: Validate trước khi chốt.**

Không tự dựng lại DCF (đã tính sẵn trong `valuation_run`). Không gọi `signals_technical` / `financial_detail` / `stock_forensic` ở đây; cần chất lượng cơ bản thì cross-ref `co-ban-chuyen-sau`, không gọi lại tool của skill đó. Bank ưu tiên per_pb, ghi rõ lý do.

## Template

ALWAYS use this exact verdict structure, mỗi mục ghi số + trend + provenance:

1. Giá hiện tại vs vùng fair: method nào dẫn, chênh bao nhiêu % (`provenance: valuation_run` + `vs_overview_trading`).
2. PER/PB hiện tại vs trung bình 2–3 năm tự tính (`provenance: financial_ratios` + `vn_quote_history`).
3. Rẻ/đắt vì sao: tăng trưởng + chất lượng (cross-ref `co-ban-chuyen-sau`) + lãi suất.
4. UPSIDE/DOWNSIDE % + độ tin (cao nếu 2 method đồng thuận).
5. Dòng neo kỳ vọng: upside theo target CTCK (`provenance: tim-co-hoi-bao-cao-ctck` cross-ref, chỉ tham chiếu).
6. Kết luận 1 câu: ĐẮT/HỢP LÝ/RẺ + UPSIDE/DOWNSIDE %.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: FPT đắt chưa
Output: VCB per_pb @57,400 (2 method đồng thuận) · FPT per_pb @62,700 · US10Y 5.24% context · overview_trading VCB PE/PB/ROEA đủ → UPSIDE % + so lịch sử 2 dòng, ≤7 calls.
---

## 10 · du-doan-fed
> File thật: `OpenTrading/skills/du-doan-fed/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: du-doan-fed
description: Đọc xác suất và kịch bản lãi suất Fed kỳ tới (cắt/giữ/tăng) kèm đường cong lợi suất, lịch FOMC và hàm ý cho VN. Luôn dùng skill này khi user hỏi Fed, FOMC, dot plot hay xác suất lãi suất Mỹ — ví dụ "Fed tháng tới cắt hay giữ", "dot plot mới nhất" — ngay cả khi user không nói rõ muốn "dự đoán Fed".
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 8
triggers:
  keywords: [fed, fomc, cắt giảm lãi suất, dot plot, xác suất fed, lãi suất mỹ]
version: 1.1.0
```

# Reading the Next Fed Decision

Trả về đúng 5 mục: xác suất từng kịch bản → đường cong → lịch FOMC → biến số theo dõi → hàm ý VN. Chỉ drill 1 event Fed chính (slug mới nhất, đã sort vol24h) — không bắn 5 query biến thể.

## When to Use

- Dùng khi: user hỏi Fed kỳ tới (cắt/giữ/tăng), FOMC, dot plot, xác suất odds + đường cong + hàm ý VN.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Bối cảnh vĩ mô Mỹ chung (chu kỳ, việc làm, risk regime) không cần odds → dùng `danh-gia-vi-mo-quoc-te`.
  - Odds chủ đề ngoài Fed (bầu cử, BTC...) → dùng `du-doan-polymarket`.
  - Bản đồ rủi ro chính trị rộng → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: odds Fed (1 call, lấy event top)
- [ ] Step 2: drill-down + macro (song song)
- [ ] Step 3: curve + xác minh nguồn chính thức
- [ ] Step 4: verdict 5 mục
```

**Step 1: Odds Fed (bắt buộc).**

Chạy `world_prediction_odds` (query=fed). Có prob ≥2 kịch bản + lịch họp là đủ verdict; Step 3 sau đó chỉ để xác minh.

**Step 2: Drill-down + macro (song song, tuần tự sau Step 1).**

Chạy `polymarket_event` (slug fed-decision-*) + `fred_series` (DGS10, thêm EFFR/DFII nếu cần). Không drill quá 1 slug Fed/run.

**Step 3: Curve + xác minh (song song, tuần tự sau Step 2).**

Chạy `yf_yield_curve` + `web_fetch` (chỉ statement/nguồn chính thức fed.gov trong odds).

**Step 4: Validate trước khi chốt.**

Odds stale (end-date qua) → lọc `end > today`, bỏ event hết hạn, retry 1 lần query fed mới. Gamma chết cả proxy + direct thì ghi rõ "không có odds", không thay bằng nhận định riêng. Curve flaky → retry tối đa 1 lần sau backoff rồi bỏ, ghi chú thiếu curve. `fred_series` tối đa 3 series ngoài Fed thì dừng.

## Template

ALWAYS use this exact verdict structure:

1. **Xác suất từng kịch bản:** cắt/giữ/tăng, mỗi kịch bản prob_pct (đơn vị %) + volume (USD) + end-date + URL event.
2. **Đường cong ám chỉ:** US10Y/2Y (đơn vị %) + inverted hay không + URL.
3. **Lịch FOMC kế tiếp:** ngày họp (đơn vị ngày/tháng) + nguồn fed.gov URL.
4. **Biến số theo dõi:** CPI Mỹ, jobs, đơn vị %/K jobs + URL.
5. **Hàm ý cho VN:** tỷ giá/lãi suất, 1–2 dòng + URL.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Fed tháng tới
Output: "Fed Decision in October 2026": Yes(no change) 74.5% / No 25.5%, volume24h 2.6M · curve US10Y 5.24% không đảo → prob ≥2 kịch bản + lịch họp + 1 dòng hàm ý VN.
---

## 11 · du-doan-polymarket
> File thật: `OpenTrading/skills/du-doan-polymarket/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: du-doan-polymarket
description: Đọc xác suất Polymarket theo chủ đề (bảng event + prob_pct + volume + cờ tin cậy liquidity/end-date). Luôn dùng skill này khi user hỏi odds/xác suất, market nào đang nóng, hay "bao giờ X" — ví dụ "odds bầu cử Mỹ", "BTC bao giờ chạm 100k" — ngay cả khi user không nói rõ muốn "xem Polymarket". Không dùng cho Fed chuyên biệt (dùng du-doan-fed).
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 6
triggers:
  keywords: [polymarket, odds, xác suất, prediction market, bao giờ bitcoin, cá cược sự kiện]
version: 1.1.0
```

# Reading Polymarket Odds

Trả về bảng event có prob_pct + volume + liquidity + end-date, mỗi dòng đủ 2 cờ tin cậy. Drill-down tối đa 2 events/run — người dùng chọn, không tự mở cả top-10.

## When to Use

- Dùng khi: user hỏi odds/xác suất Polymarket theo chủ đề (kinh tế, bầu cử, crypto...), "market nào đang nóng", drill-down 1–2 events.
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Fed chuyên biệt (cần curve + FOMC + hàm ý VN) → dùng `du-doan-fed`.
  - Bản đồ chính trị rộng cần ghép odds + tin GDELT → dùng `danh-gia-tinh-hinh-chinh-tri-toan-cau`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: quét odds (1 call, lấy top đã sort vol24h)
- [ ] Step 2: drill-down event user quan tâm (tối đa 2)
- [ ] Step 3: bảng + cờ + kết luận 1 câu
```

**Step 1: Quét odds (bắt buộc).**

Chạy `world_prediction_odds` (query hoặc tag, limit=10). Query rỗng thì đổi tag tối đa 1 lần rồi kết luận "không có market cho chủ đề". User chỉ hỏi "đang nóng gì" và Wave 1 đủ ≥5 events thì dừng, không drill-down.

**Step 2: Drill-down (tuần tự sau Step 1, tối đa 2).**

Chạy `polymarket_event` cho slug user quan tâm (drill outcomes đầy đủ), event thứ 2 chỉ khi user hỏi rõ. Không chạy Step 2 + 3 song song.

**Step 3: Validate trước khi chốt.**

Slug sai/không tồn tại → đổi slug top kế tiếp 1 lần rồi ghi "không drill được event X". Jina proxy chậm thì tool tự fallback direct (xem warnings), chờ 1 lần, không retry dồn dập. Gamma chết cả 2 đường → ghi rõ "không có odds", không bịa xác suất.

## Template

ALWAYS use this exact verdict structure:

1. **Bảng event:** mỗi dòng {title · prob_pct từng outcome (đơn vị %) · volume24h (USD) · liquidity (USD) · end-date (ngày) · URL event}.
2. **Cờ tin cậy bắt buộc trên từng dòng:** (1) liquidity thấp (<50k USD) → "odds kém tin"; (2) end-date đã qua → LOẠI khỏi bảng.
3. **Kết luận:** 1 câu "thị trường đặt cược X với xác suất Y" (đơn vị %).
4. **Provenance:** mỗi dòng bắt buộc URL event.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Polymarket đang nóng gì về kinh tế
Output: Fed T10/2026 no-change 74.5% (vol 2.6M) · Brazil presidential detail OK · sort vol24h hoạt động → ≥5 events + cờ tin-cậy trên từng dòng.
---

## 12 · explain-term
> File thật: `OpenTrading/skills/explain-term/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: explain-term
description: "Giải thích thuật ngữ chứng khoán (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2) bằng tiếng Việt đơn giản: định nghĩa 1 câu + công thức bằng chữ + ví dụ giả định + bẫy hay gặp. Luôn dùng skill này khi user hỏi một chỉ số hoặc khái niệm là gì — ngay cả khi câu hỏi chỉ có 2-3 chữ như 'P/E là gì'."
activation: auto
triggers:
  keywords: [là gì, nghĩa là gì, giải thích, khái niệm, thuật ngữ]
version: 1.2.0
```

# Explaining Securities Terms Simply

Trả lời đúng 5 bước, gọn nhẹ, không lan sang phân tích mã hay khuyến nghị. Mọi số minh họa là số tròn giả định — bắt buộc ghi rõ "ví dụ giả định", không bao giờ để user tưởng là số thật.

## When to Use

- Dùng khi: user hỏi một thuật ngữ, chỉ số hoặc khái niệm là gì (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2...).
- Khi KHÔNG dùng (dùng skill khác thay thế): phản biện luận điểm mua/giữ (dùng `devil-advocate`); phân tích mã cụ thể (dùng `phan-tich-chuyen-sau-1-ma`); vẽ chart (dùng `ve-bieu-do-ky-thuat`).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: định nghĩa 1 câu, tiếng Việt đơn giản
- [ ] Step 2: công thức bằng chữ (nếu có)
- [ ] Step 3: ví dụ giả định (ghi rõ giả định)
- [ ] Step 4: cách dùng ở VN + 1 bẫy hay gặp
- [ ] Step 5: 1 câu hỏi gợi mở
```

**Step 1–2: Định nghĩa + công thức.**

Định nghĩa trong một câu, không dùng biệt ngữ khác chưa giải thích. Công thức viết bằng chữ, không tự thay số thật.

**Step 3: Ví dụ minh họa.**

Số tròn giả định, bắt buộc ghi rõ "ví dụ giả định".

**Step 4: Cách dùng thực tế ở VN + 1 bẫy hay gặp.**

Ví dụ: P/E thấp ảo do lợi nhuận đột biến, margin call, room ngoại khóa.

**Step 5: Kết thúc bằng 1 câu hỏi gợi mở.**

Giúp user đào sâu (ví dụ "bạn muốn xem P/E này so với ngành không?"). Chỉ giải thích 1 thuật ngữ/lượt.

## Template

ALWAYS use this exact output structure: định nghĩa 1 câu · công thức bằng chữ · ví dụ giả định (ghi rõ giả định) · cách dùng ở VN + bẫy hay gặp · 1 câu hỏi gợi mở.

## Examples

**Example 1:**
Input: P/E là gì
Output: định nghĩa 1 câu + công thức chữ + ví dụ giả định có ghi rõ + bẫy VN + 1 câu hỏi gợi mở.

**Anti-pattern (không làm thế này):** định nghĩa bằng biệt ngữ khó hơn; quên ghi "ví dụ giả định" khiến user tưởng số thật; trả lời dài như giáo trình.
---

## 13 · kiem-chien-luoc-backtest
> File thật: `OpenTrading/skills/kiem-chien-luoc-backtest/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: kiem-chien-luoc-backtest
description: Kiểm chứng chiến lược giao dịch bằng backtest code (SMA cross, RSI quá bán, momentum, param sweep kèm best VÀ worst, mùa vụ tháng, sau Tết/cổ tức, theo giá dầu/vàng). Luôn dùng skill này khi user hỏi chiến lược có ăn không, tháng/quý nào hay tăng — ví dụ "SMA20/50 FPT có ăn không", "mua RSI<30 có thắng không" — ngay cả khi user không nói rõ muốn "backtest".
activation: auto
requires_tools: [mcp__opentrading__quant_backtest]
tool_budget: 12
triggers:
  keywords: [backtest, kiểm chứng, chiến lược, sma cross, rsi dưới, quá bán, momentum chiến lược, param sweep, mùa vụ tháng, sau tết, sau chia cổ tức, theo giá dầu, theo giá vàng]
version: 1.2.2
```


# Backtesting Trading Strategies Honestly

Pipeline chuẩn mỗi run: baseline → chiến lược → sweep → seasonality/event → kết luận. Best bắt buộc kèm worst (chống overfit); thiếu worst hoặc thiếu caveat engine thì chưa đạt. Engine numpy-only, cost mặc định, T+2 VN chưa model — mọi kết luận đều kèm caveat này.

## When to Use

- Dùng khi: kiểm chứng điều kiện kỹ thuật (SMA/momentum/RSI), thời gian (tháng/quý), sau sự kiện (Tết/cổ tức/ĐHĐCĐ), theo giá hàng hóa (dầu/vàng).
- Khi KHÔNG dùng (dùng skill khác thay thế): sizing vị thế cụ thể → leg Đệm trong `danh-gia-truoc-bctc`; định giá → `dinh-gia-chuyen-sau`; tin/sentiment → `tim-kiem-tin-tuc` / `phan-tich-sentiment`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: dữ liệu + benchmark (1 symbol/lần)
- [ ] Step 2: điều kiện kỹ thuật
- [ ] Step 3: điều kiện thời gian
- [ ] Step 4: điều kiện sau sự kiện
- [ ] Step 5: điều kiện giá hàng hóa
- [ ] Step 6: sweep + tổng hợp best/worst
```

**Step 1: Dữ liệu (tuần tự đầu tiên).**

Chạy `vn_quote_history` (stock) hoặc `dnse_ohlc_history` (futures/index) + `vn_index_ohlcv` (benchmark). Chỉ 1 symbol mỗi lần sweep. Mã cổ phiếu VN thì dùng nến equity — CẤM dùng `vn_crypto_ohlcv`.

**Step 2: Điều kiện kỹ thuật.**

Chạy `backtest_strategies` (strategy=sma_cross/momentum/**rsi_meanrev** + rsi_low/rsi_high). rsi_meanrev: mua RSI<30, thoát RSI>70. `quant_backtest` đã deprecated cho chiến lược (chỉ còn baseline buy-hold) — mọi so sánh timing rule đi qua `backtest_strategies`, không gọi `quant_backtest` ở step này.

**Step 3: Điều kiện thời gian.**

Chạy `backtest_strategies` + `months`/`quarters` + `seasonality` (mô tả tháng/quý). Entries chỉ kỳ chọn, exits luôn mở. Months=[1] trên nến tháng 3 → 0 trades + warning là hợp lệ, không retry đổi timeframe.

**Step 4: Điều kiện sau sự kiện.**

Chạy `event_study` (symbol, dates, window ±N) — CAR quanh Tết/cổ tức/ĐHĐCĐ, ngày từ `event_calendar_vn`, nearest-day 3 phiên, kèm hit-rate/best-worst.

**Step 5: Điều kiện giá hàng hóa.**

Chạy `backtest_strategies` + `condition_symbol` (BZ=F/GC=F...) + `condition_rule` above_sma/rising. `condition_symbol` chết thì cả call unavailable — nói rõ, không thay symbol khác. Fallback vnstock→yfinance nằm trong tool, không tự đổi nguồn tay.

**Step 6: Tổng hợp.**

Chạy `param_sweep` (tối đa 30 combos có sẵn, không tự nới; passthrough months/quarters) + `correlation_matrix` + `portfolio_optimize` (nhiều mã). Không sweep quá 3 symbol/run.

## Template

ALWAYS use this exact verdict structure: baseline buy-hold → từng điều kiện (số trades/net/win) → best param + worst param → seasonality/event bias → kết luận "đáng tin / đáng nghi + lý do" + caveat engine (numpy-only, cost mặc định, T+2 chưa model) + provenance (nguồn nến, benchmark, ngày sự kiện).

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Backtest mua RSI<30 FPT + backtest sau Tết
Output: VCB buy-hold −4.9% gross · sma_cross 7 trades −10.4% · sweep best **+3.7%** · seasonality tháng 1 mean +4.67% · rsi_meanrev VCB 1 trade · months=[1] trên nến tháng 3 → 0 trades + warning · event_study VCB 2026-09-21: CAR +0.25% → bảng từng điều kiện (trades/net/win) + best/worst + kết luận, kèm caveat T+2/cost.
---

## 14 · kiem-tra-nguon-du-lieu
> File thật: `OpenTrading/skills/kiem-tra-nguon-du-lieu/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: kiem-tra-nguon-du-lieu
description: Quét sức khỏe toàn bộ upstream trong 1 lượt (bảng trạng thái từng nguồn + khuyến nghị skill nào chạy được). Luôn dùng skill này khi user hỏi nguồn sống không, check trước phiên, hoặc khi các skill khác báo unavailable hàng loạt — ví dụ "Vietstock chết chưa", "sáng nay data có đủ không" — ngay cả khi user không nói rõ muốn "check nguồn".
activation: manual
requires_tools: [mcp__opentrading__doctor]
tool_budget: 12
triggers:
  keywords: [check nguồn, kiểm tra nguồn, server sống không, vietstock chết, data có đủ không, health check, nguồn dữ liệu]
version: 1.1.0
```

# Checking Data-Source Health

Trả về bảng trạng thái 9 nguồn + 1 dòng khuyến nghị skill nào chạy được. Smoke ở đây là ping (limit/days nhỏ nhất), không lấy dữ liệu thật. Skill này không phân tích thị trường.

## When to Use

- Dùng khi: user hỏi server còn sống không, Vietstock chết chưa, sáng nay có đủ data không, check nguồn trước phiên, hoặc khi các skill khác báo unavailable hàng loạt.
- Khi KHÔNG dùng (dùng skill khác thay thế): phân tích mã/thị trường (dùng `phan-tich-chuyen-sau-1-ma`, `ky-thuat-chuyen-sau`).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 0: doctor local
- [ ] Step 1: tổng quan upstream + JWT (song song)
- [ ] Step 2: smoke từng upstream (limit/days nhỏ nhất)
- [ ] Step 3: bảng verdict + khuyến nghị
```

**Step 0: Doctor.**

Chạy `doctor` (env keys + versions local).

**Step 1: Tổng quan (song song).**

Chạy `source_status` + `vs_auth_status`: tổng quan upstream + hạn JWT.

**Step 2: Smoke từng upstream (song song, limit/days nhỏ nhất).**

`vn_quote_history` (VCB, days=5) · `vs_market_index` · `dnse_latest_trade` (VN30F1M) · `yf_market_pins` · `crypto_spot` (BTCUSDT), rồi `news_market` (limit=1) · `fred_series` (DGS10, limit=1) · `world_prediction_odds` (limit=1) · `sbv_rates`. Retry tối đa 1 lần/upstream. Tài khoản Vietstock login Google thì password fallback bị từ chối ("đăng nhập bằng Google!") — phải re-login Google + export HAR/cookie mới.

**Step 3: Validate trước khi chốt.**

Chính skill này cũng có thể partial (1–2 nguồn chết) — verdict vẫn ra đủ bảng, đánh dấu đỏ nguồn chết.

## Template

ALWAYS use this exact verdict structure — bảng {Nguồn · Trạng thái · Độ trễ · Skills ảnh hưởng nếu chết} cho đủ 9 nguồn: vnstock (ok/throttle/down) · Vietstock JWT (còn hạn tới.../HẾT) · Vietstock HAR-session (sống/chết) · DNSE (ok/lạnh) · yfinance/Binance/GDELT/Fireant/Gamma/FRED/SBV + 1 dòng khuyến nghị ("sáng nay đủ data chạy ..." hay "chỉ chạy legs không-Vietstock").

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: check nguồn trước phiên
Output: sự cố JWT hết hạn 19:15 bắt được ở Step 1 (`vs_auth_status` false) trước khi skills khác fail hàng loạt; HAR-session sống độc lập (macro vẫn available khi JWT chết) → bảng đủ 9 nguồn + khuyến nghị, ≤12 calls, ≤3 phút.
---

## 15 · ky-thuat-chuyen-sau
> File thật: `OpenTrading/skills/ky-thuat-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: ky-thuat-chuyen-sau
description: Đọc kỹ thuật thuần 1 mã đa khung 1D/1W/1M (RSI/MACD/BB/Ichimoku/ADX, Elliott/Wyckoff, hỗ trợ-kháng cự, higher-high hay lower-low) trong tối đa 8 calls. Luôn dùng skill này khi user hỏi kỹ thuật, breakout, đọc băng, sóng Elliott hay HH/LL của một mã — ví dụ "VCB kỹ thuật sao", "FPT có breakout không" — ngay cả khi user không nói rõ muốn "phân tích kỹ thuật".
activation: auto
requires_tools: [mcp__opentrading__signals_technical]
tool_budget: 8
triggers:
  keywords: [kỹ thuật, rsi, macd, bb, bollinger, ichimoku, elliott, wyckoff, hỗ trợ, kháng cự, breakout, pattern, orderbook, băng giá, chỉ báo, adx, ema, sma, higher high, lower low, đa khung]
version: 1.2.0
```

# Reading Single-Stock Technicals

Mặc định 2 khung (1D+1W); khung 1M chỉ khi user hỏi dài hạn. Một call `signals_technical` đã đủ 80% verdict — đây là skill "1 tool trụ cột" mẫu mực, đừng gọi thêm tool cho đủ số.

## When to Use

- Dùng khi: user hỏi kỹ thuật 1 mã (`VCB kỹ thuật đa khung sao`, `FPT có breakout không`, `đọc băng HPG`, `higher-high hay lower-low`, `sóng Elliott`).
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Hỏi BCTC/cơ bản/M-Score → `co-ban-chuyen-sau`.
  - Hỏi định giá/fair value/PER/upside → `dinh-gia-chuyen-sau`.
  - Phân tích toàn diện 1 mã → `phan-tich-chuyen-sau-1-ma` (skill đó sẽ dispatch skill này).
  - So sánh nhiều mã → `so-sanh-cung-nganh`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: nến đa khung (mỗi khung 1 call)
- [ ] Step 2: đọc cấu trúc sóng từ output Step 1 (không gọi tool mới)
- [ ] Step 3: xác nhận theo câu hỏi (tối đa 3 calls)
- [ ] Step 4: verdict từng khung + tổng hợp
```

**Step 1: Nến đa khung.**

Chạy `signals_technical` (symbol, interval=1D) + (interval=1W) [+ (interval=1M) nếu hỏi dài hạn]. Mỗi khung 1 call: RSI/MACD/BB/Ichimoku/S-R/patterns. Interval chỉ nhận 1D/1W/1M (1W cần ≥30 bars, 1M ≥24 bars); interval lạ → `unavailable`, không retry.

**Step 2: Đọc cấu trúc sóng (không gọi tool mới).**

Từ output Step 1 đọc swings + swing_trend + fib + elliott + wyckoff; tự dán nhãn HH/HL/LH/LL + Fibonacci 7 mức + Elliott (impulse/corrective/developing + invalidation) + Wyckoff phase.

**Step 3: Xác nhận theo câu hỏi (tối đa 3 calls).**

Chỉ gọi khi user hỏi tới: `pattern_match` (analogy lịch sử) · `dnse_latest_trade` / `dnse_orderbook` / `vn_trades` (intraday) · `vn_index_ohlcv` (trend index). Không gọi `financial_detail` / `valuation_run` / `stock_forensic` ở đây.

**Step 4: Validate trước khi chốt.**

Mã mới <60 nến → indicators null → báo "thiếu lịch sử", không bịa RSI/MACD. DNSE hết giờ → orderbook rỗng là đúng data, ghi rõ phiên đóng. `pattern_match` corr <0.4 = không có analogy đáng tin → ghi đúng. Giá theo kVND (`signals_technical.last 57.3` = 57,300đ) → bắt buộc qui đổi + ghi đơn vị. Khung nào thiếu → verdict partial khung còn lại + ghi khung thiếu. Elliott/Wyckoff là heuristic → bắt buộc ghi confidence + invalidation.

## Template

ALWAYS use this exact verdict structure, cho MỖI khung (1D/1W[/1M]), mỗi mục ghi số + trend + provenance:

1. Trend: SMA stack + ADX. 2. Momentum: RSI/MACD/stoch/CCI cụ thể từng chỉ báo. 3. S-R của khung đó. 4. Cấu trúc: HH/HL/LH/LL + Fibo + Elliott pattern/invalidation + Wyckoff phase + confidence. 5. Kết luận khung: higher-high hay lower-low. 6. Tổng hợp: đồng thuận đa khung hay phân kỳ + trigger giá → timing MUA/CHỜ/BÁN. 7. Kết luận 1 câu chốt toàn mã.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: FPT kỹ thuật 1D+1W
Output: VCB — RSI 39.2, ADX 12.1 (trend yếu), MACD −0.31/−0.13, EMA10 58.09, pos_52w 0.21 · HPG pattern best_corr 0.409 (yếu — ghi đúng) · VCB 1W bearish/lower-low/fib-down nhất quán → verdict 2 khung + HH/LL + Ichimoku signal, ≤8 calls.
---

## 16 · nhip-dap-crypto
> File thật: `OpenTrading/skills/nhip-dap-crypto/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: nhip-dap-crypto
description: "Nhịp đập crypto bằng ngôn ngữ thường cho người ít chuyên: xu hướng giá, đòn bẩy funding/OI có nóng không, fear/greed, giá quy VND. Luôn dùng skill này khi user hỏi BTC/ETH/SOL sao rồi, crypto lên hay xuống, funding rate, có nên quan tâm crypto không — ngay cả khi user không nói rõ muốn 'phân tích crypto'."
activation: auto
requires_tools: [mcp__opentrading__crypto_spot]
tool_budget: 6
triggers:
  keywords: [btc, bitcoin, eth, ethereum, crypto, tiền số, tiền ảo, funding]
version: 1.2.1
```


# Reading Crypto Pulse in Plain Language

Viết cho người ít chuyên crypto: mọi thuật ngữ bắt buộc giải thích 1 dòng kèm theo số. Trả lời đúng 3 câu. Crypto chạy 24/7 nên số "hôm nay" khác phiên chứng khoán VN — đừng so lệch phiên.

## When to Use

- Dùng khi: user hỏi BTC/ETH/SOL sao rồi, crypto lên hay xuống, funding/OI nói gì, giá crypto quy ra VND, crypto có liên thông gì tới chứng khoán VN.
- Khi KHÔNG dùng (dùng skill khác thay thế): bối cảnh regime vĩ mô toàn cầu (chỉ dùng `danh-gia-vi-mo-quoc-te`); odds xác suất sự kiện crypto (chỉ dùng `du-doan-polymarket`); phân tích vàng/tỷ giá (chỉ dùng `phan-tich-vang-ty-gia`).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: giá spot (tối đa 3 đồng)
- [ ] Step 2: đòn bẩy derivs
- [ ] Step 3: sentiment + giá VND
- [ ] Step 4: verdict 3 câu
```

**Step 1: Giá spot.**

Chạy `crypto_spot` (BTC ETH SOL — tối đa 3 đồng/wave 1). Giá + % 24h = "tăng/giảm bao nhiêu hôm nay". CẤM dùng `vn_crypto_ohlcv` thay thế (giá quy VND ≠ giá USD thật) — tool đó chỉ dùng ở Step 3 khi user hỏi giá VND.

**Step 2: Đòn bẩy derivs.**

Chạy `crypto_derivs` (BTC ETH). Giải thích kèm số: funding rate = "phe mua đang trả tiền cho phe bán (dương = đám đông cược lên)"; OI = "tổng tiền đang cược"; long/short = "bên nào đông hơn"; funding cao + OI cao = đòn bẩy nóng, dễ đảo chiều. Funding/OI rỗng do Binance geo-block từ worker Singapore thì ghi "không lấy được do giới hạn vùng", không kết luận thị trường chết.

**Step 3: Sentiment + giá VND.**

Chạy `world_fear_greed` + `vn_crypto_ohlcv` (path quy VND). Chỉ drill Polymarket crypto khi user hỏi xác suất; không tự lan sang odds/event-study.

## Template

ALWAYS use this exact verdict structure (đúng 3 câu):

1. Xu hướng gì (lên/xuống/đi ngang + %). 2. Đòn bẩy có nóng không (funding cao + OI cao = dễ đảo chiều). 3. Liên thông gì tới VN (giá VND + chứng khoán còn lại — không có thì ghi "độc lập").

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: BTC sao rồi
Output: BTC 83,476 (+0.33%) · funding 2.8e-05 (trung tính) · OI 95.7k · fear/greed 70-74 → 3 câu trả lời + 0 jargon không giải thích, ≤6 calls.
---

## 17 · phan-tich-chuyen-sau-1-ma
> File thật: `OpenTrading/skills/phan-tich-chuyen-sau-1-ma/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-chuyen-sau-1-ma
description: "Điều phối phân tích toàn diện 1 mã theo 8 bước: tự nhận diện mã/ngành/tin/sự kiện, gọi các skill chuyên (kỹ thuật, định giá) rồi gộp verdict bảng Tích cực/Tiêu cực/Động lực. Luôn dùng skill này khi user yêu cầu phân tích toàn diện 1 mã — ví dụ 'phân tích FPT', 'VCB thế nào', 'mã này sao' — ngay cả khi user không nói rõ muốn 'phân tích toàn diện'."
activation: auto
requires_tools: [mcp__opentrading__stock_overview]
tool_budget: 8
triggers:
  keywords: [phân tích, phân tích cổ phiếu, phân tích mã, toàn diện, chi tiết mã, mã này sao]
version: 1.2.2
```


# Coordinating Full Single-Stock Analysis

Skill điều phối 8 bước: tự làm nhận diện mã + ngành + tin + sự kiện, dispatch kỹ thuật/định giá sang sub-skill, rồi gộp verdict. Budget 8 chỉ đếm tool nhà của skill này; tool của sub-skill nằm trong budget của sub-skill, không cộng dồn.

## When to Use

- Dùng khi: user yêu cầu phân tích toàn diện 1 mã (`phân tích FPT`, `VCB thế nào`, `mã này sao`).
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Chỉ hỏi kỹ thuật (RSI, breakout, đa khung, higher-high/lower-low) → `ky-thuat-chuyen-sau`.
  - Chỉ hỏi BCTC/cơ bản (M-Score, cổ đông, cổ tức) → `co-ban-chuyen-sau`.
  - Chỉ hỏi định giá (fair value, PER, upside) → `dinh-gia-chuyen-sau`.
  - So sánh 2-6 mã cùng ngành → `so-sanh-cung-nganh`.
  - Đánh giá setup trước khi BCTC ra → `danh-gia-truoc-bctc`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: xác định mã (resolve tên nhập nhằng)
- [ ] Step 2: ngành + kiếm tiền nhờ đâu (gọi trực tiếp)
- [ ] Step 2b: chart giá (dùng lại nến đã có → chart_render local, đính kèm verdict)
- [ ] Step 3-4: dispatch kỹ thuật + định giá sang sub-skill
- [ ] Step 5-7: lợi nhuận quý + tin + sự kiện (gọi trực tiếp)
- [ ] Step 8: tổng hợp + khóa verdict
```

**Step 1: Xác định mã (gọi trực tiếp).**

Chạy `symbol_lookup` (tên công ty) · `symbol_resolve` (mã đa loại, có fallback xếp hạng). Mã nhập nhằng (vàng/BTC/USD) thì bắt buộc `symbol_resolve` trước. `symbol_resolve` trả nhiều ứng viên → chọn hạng cao nhất + ghi rõ đã resolve từ tên nào sang mã nào; thiếu mã thì dừng và hỏi lại, không đoán mã. Sau khi có mã: cổ phiếu VN → nến/tools `vn_*`/`vs_*`; crypto → `crypto_spot` (USD, không dùng `vn_crypto_ohlcv` trừ khi hỏi giá VND).

**Step 2: Ngành + kiếm tiền nhờ đâu (gọi trực tiếp).**

Chạy `vn_company` · `vs_company_info` · `vs_industry_tree`. Lấy ngành GICS, mô hình kinh doanh, nguồn thu chính. Mã mới chưa phân loại ngành (`vs_industry_tree` không match) → ghi "chưa phân loại", vẫn chạy các bước còn lại.

**Step 2b: Chart giá (tool local, không tốn budget remote).**

Dùng lại nến đã có trong context (từ Step 1 `vn_quote_history` hoặc sub-skill kỹ thuật) → gọi `chart_render` (local, kind=`candlestick` ≥5 nến) rồi đính kèm hình vào verdict cuối. Không fetch lại nến chỉ để vẽ; chưa có nến thì bỏ qua chart, không thêm call data. Chi tiết kind/màu xem `ve-bieu-do-ky-thuat`.

**Step 3-4: Dispatch kỹ thuật + định giá (không gọi tool gốc).**

Dispatch `ky-thuat-chuyen-sau` (trạng thái kỹ thuật) và `dinh-gia-chuyen-sau` (định giá). Không bao giờ gọi trực tiếp `signals_technical` / `valuation_run` / `stock_forensic` ở đây để thay thế — ai cần kỹ thuật/định giá thì đi qua sub-skill.

**Step 5-7: Lợi nhuận quý + tin + sự kiện (gọi trực tiếp).**

Chạy `financial_detail` (chỉ lấy số nhanh KQKD 4 quý + so QoQ/YoY/biên — không đào sâu BCTC/M-Score/F-score, đó là việc của `co-ban-chuyen-sau`), `news_symbol` + `company_events` (tin + công bố), `event_calendar_vn` (lịch 30–90 ngày: BCTC/ĐHĐCĐ/cổ tức).

**Step 8: Tổng hợp + validate.**

Chạy `evidence_bundle` để khóa verdict thành bảng Tích cực / Tiêu cực / Động lực tương lai. Sub-skill chết 1 chân thì vẫn ra verdict với leg còn sống + ghi rõ leg thiếu, không bù số. User hỏi 1 chiều (`RSI FPT`) thì bắt buộc trả lời bằng sub-skill tương ứng, không chạy đủ 8 bước. Đủ 8 bước hoặc đủ dữ liệu ra bảng 3 cột thì dừng, không gọi thêm vòng tin/sự kiện thứ hai.

## Template

ALWAYS use this exact verdict structure, mỗi mục ghi số + trend + provenance (tool/sub-skill nào ra số đó):

1. Nhận định 1 câu (khuyến nghị/tone chính).
2. Ngành + cách kiếm tiền (2 dòng, từ Step 2).
3. Kỹ thuật (`provenance: ky-thuat-chuyen-sau`, kèm khung 1D/1W).
4. Định giá (`provenance: dinh-gia-chuyen-sau`, kèm UPSIDE/DOWNSIDE % nếu có).
5. Lợi nhuận quý (số DT/LN 4 quý + trend QoQ/YoY + biên, từ `financial_detail` Step 5).
6. Tin + sự kiện sắp tới (từ `news_symbol` / `company_events` / `event_calendar_vn`).
7. Bảng Tích cực / Tiêu cực / Động lực tương lai (3 cột, khóa bằng `evidence_bundle`).
8. Chart nến đính kèm (từ Step 2b, nếu có).
9. Kết luận 1 câu chốt lại toàn mã.

## Examples

**Example 1:**
Input: Phân tích FPT
Output: đủ 8 bước, có bảng 3 cột tích cực/tiêu cực/động lực, ≤8 calls nhà (chưa tính calls trong sub-skill). Số liệu live nằm ở sub-skill `ky-thuat-chuyen-sau` và `dinh-gia-chuyen-sau` — không bịa số tại skill này.
---

## 18 · phan-tich-sentiment
> File thật: `OpenTrading/skills/phan-tich-sentiment/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-sentiment
description: Đo dư luận crowd về 1 mã trên Fireant (điểm sentiment + quotes + cảnh báo FOMO), trong tối đa 6 calls. Luôn dùng skill này khi user hỏi phố/crowd nói gì về một mã, sentiment hay FOMO — ví dụ "Phố nói gì về FPT", "crowd có FOMO HPG không" — ngay cả khi user không nói rõ muốn "đo sentiment".
activation: auto
requires_tools: [mcp__opentrading__sentiment_score]
tool_budget: 6
triggers:
  keywords: [sentiment, dư luận, phố nói gì, crowd, fomo, tâm lý nhà đầu tư, comment]
version: 1.1.0
```

# Measuring Single-Stock Crowd Sentiment

Đo *đám đông*, không đo *doanh nghiệp* — crowd có thể sai, sentiment không bao giờ là leg duy nhất của quyết định. Chỉ 1 symbol/run; limit 20 đủ 90% mẫu, không nới limit.

## When to Use

- Dùng khi: hỏi dư luận/crowd/FOMO/comment về 1 mã cụ thể trên Fireant.
- Khi KHÔNG dùng (dùng skill khác thay thế): tin chính thống/rumor → `tim-kiem-tin-tuc`; fear/greed chung → `danh-gia-vi-mo-quoc-te` / `nhip-dap-crypto`; rating CTCK → `tim-co-hoi-bao-cao-ctck`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: posts + điểm (song song)
- [ ] Step 2: đối chiếu công bố (chỉ khi mâu thuẫn)
- [ ] Step 3: verdict (điểm + quotes + FOMO + cảnh báo)
```

**Step 1: Posts + điểm (song song).**

Chạy `news_symbol` (symbol, limit=20) + `sentiment_score` (symbol, limit=20) — cùng nguồn Fireant. Đủ điểm + ≥3 quotes + nhãn nguồn thì dừng.

**Step 2: Đối chiếu công bố (chỉ khi mâu thuẫn, tuần tự).**

Chạy `company_events` (symbol) khi comment contradicts disclosures. Không dùng sentiment để "chốt luận" — chỉ confirm/deny.

**Step 3: Validate trước khi chốt.**

Thiếu Groq → `score_heuristic` + warning "groq unavailable" → bắt buộc nhãn `heuristic` trong verdict (heuristic thang khác, không chuẩn hóa chéo 2 mode Groq/heuristic). Posts rỗng = mã ít bàn (empty hợp lệ), không bịa quotes, ghi rõ "ít bàn luận". Fireant chết → fallback duy nhất: GDELT titles qua `tim-kiem-tin-tuc` (1 call), ghi rõ nguồn thay thế. Không diễn giải heuristic thành "nên mua/bán".

## Template

ALWAYS use this exact verdict structure:

- **Điểm sentiment** (Groq hoặc heuristic — bắt buộc ghi nhãn nguồn).
- **3–5 trích comment tiêu biểu** (positive / negative / repeat-thuyết) + provenance Fireant.
- **Nhận diện FOMO/hoảng loạn** (tần suất symbol tag + likes); ngưỡng heuristic: <−0.3 hoảng loạn · >+0.3 FOMO · giữa = trung tính.
- **Cảnh báo vòng lặp bắt buộc:** crowd có thể sai — sentiment không được là leg duy nhất của quyết định.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Phố nói gì về FPT
Output: FPT — 20 posts, heuristic **−0.25**, trong khi M −2.06 sạch (điển hình crowd≠fundamentals) · VCB posts lãi suất 0.1-6% → điểm + ≥3 quotes + nhãn nguồn, ≤4 calls. Thiếu nhãn nguồn hoặc thiếu cảnh báo vòng lặp thì chưa đạt.
---

## 19 · phan-tich-vang-ty-gia
> File thật: `OpenTrading/skills/phan-tich-vang-ty-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-vang-ty-gia
description: "Phân tích vàng SJC, premium SJC-thế giới, tỷ giá USDVND và lãi suất 2 đầu SBV-Fed (tối đa 10 calls). Luôn dùng skill này khi user hỏi vàng SJC đắt hơn thế giới bao nhiêu, tỷ giá có áp lực không, hay dự đoán khung vàng VN — ngay cả khi user không nói rõ muốn 'phân tích vàng'."
activation: auto
requires_tools: [mcp__opentrading__vn_retail_gold]
tool_budget: 10
triggers:
  keywords: [vàng sjc, vàng miếng, giá vàng, usdvnd, tỷ giá, premium vàng, vàng thế giới, xauusd, dự đoán vàng]
version: 1.2.0
```

# Analyzing Gold Premium and USDVND Pressure

Trả về: giá TG + TA 3 dòng · premium % + dự đoán khung vàng VN (theo TG / ngược TG khi premium nở) · lãi suất 2 đầu + hàm ý tỷ giá · kịch bản odds. Không point-forecast giá cụ thể ("vàng sẽ lên X triệu") — chỉ nêu premium + driver + kịch bản odds.

## When to Use

- Dùng khi: user hỏi giá vàng SJC/vàng miếng, chênh lệch (premium) VN–TG, giá vàng thế giới + TA vàng, áp lực tỷ giá USDVND, dự đoán khung vàng VN, lãi suất 2 đầu SBV–Fed và hàm ý tỷ giá.
- Khi KHÔNG dùng (dùng skill khác thay thế): lãi suất điều hành VN chung (chỉ dùng `danh-gia-vi-mo-viet-nam`); nhịp đập crypto (chỉ dùng `nhip-dap-crypto`); TA mã chứng khoán VN (chỉ dùng `ky-thuat-chuyen-sau`).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: giá vàng quốc tế + TA vàng
- [ ] Step 2: rủi ro địa chính trị (cross-ref, không gọi lại)
- [ ] Step 3: so lệch VN–TG → premium
- [ ] Step 4: lãi suất 2 đầu
- [ ] Step 5: kịch bản odds + verdict
```

**Step 1: Giá vàng quốc tế + TA vàng.**

Chạy `yf_commodities` (GC — 1 call đã gồm GC+DXY, không tách tick riêng lẻ) + `vn_msn_fx_gold`. Đọc trend/momentum trên nến daily (giá vs SMA20/50 + RSI ước từ series). `signals_technical` chỉ hỗ trợ mã VN — không ép dùng cho GC=F, đọc TA từ series có sẵn.

**Step 2: Rủi ro địa chính trị (cross-ref, không gọi lại).**

Tham chiếu `danh-gia-tinh-hinh-xung-dot` / `bat-on-quoc-gia` nếu vừa chạy ở skill trước (leo thang = vàng lên); không gọi lại tốn budget.

**Step 3: So lệch VN–TG → premium.**

Chạy `vn_retail_gold` (SJC mua/bán). Premium = (SJC mua vào − giá TG quy đổi) / giá TG — bắt buộc ghi giả định quy đổi đơn vị (SJC VND/lượng vs XAUUSD USD/oz). Premium nở = vàng VN khó giảm theo TG.

**Step 4: Lãi suất 2 đầu.**

Chạy `sbv_rates` + `fred_series` (DGS10) + `yf_yield_curve`: SBV (tái cấp vốn/chiết khấu) vs US (DGS10/curve) — chênh lệch hút vốn, hàm ý tỷ giá.

**Step 5: Kịch bản odds + validate.**

Tham chiếu `world_prediction_odds` (cross-ref `du-doan-fed`) + `macro_events_vn` cho bối cảnh. Chỉ nêu premium + driver + kịch bản odds, không point-forecast.

## Template

ALWAYS use this exact verdict structure: giá TG + TA 3 dòng · premium % + dự đoán khung vàng VN (theo TG / ngược TG khi premium nở) · lãi suất 2 đầu + hàm ý tỷ giá · kịch bản odds · KHÔNG point-forecast giá.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Vàng SJC hôm nay đắt hơn thế giới bao nhiêu
Output: VÀNG MIẾNG SJC 999.9 (BTMC live) · XAUUSD 4,195 · USDVND 25,970 (MSN) · SBV 4.5% tái cấp vốn · Fed giữ 74.5% → số premium % + giả định + 2 driver, ≤10 calls.
---

## 20 · so-sanh-cung-nganh
> File thật: `OpenTrading/skills/so-sanh-cung-nganh/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: so-sanh-cung-nganh
description: "Xếp hạng 2-6 mã cùng ngành và chọn leader (chất lượng × momentum) trong tối đa 8 calls nhà. Luôn dùng skill này khi user hỏi so sánh mã cùng ngành, mã nào mạnh nhất/đáng mua — ví dụ 'VCB vs BID vs CTG', 'steel mạnh nhất là ai' — ngay cả khi user không nói rõ muốn 'so sánh cùng ngành'."
activation: auto
requires_tools: [mcp__opentrading__compare_equities]
tool_budget: 8
triggers:
  keywords: [so sánh, vs, so với, cùng ngành, mạnh nhất, leader, hơn kém, xếp hạng mã]
version: 1.2.0
```

# Ranking Same-Sector Stocks

Skill điều phối thứ hai (cùng họ `phan-tich-chuyen-sau-1-ma`): xác định mã cùng ngành, gọi 1 sub-skill cho từng mã, gộp xếp hạng. Mỗi mã chỉ 1 sub-skill theo câu hỏi (momentum → kỹ thuật; chất lượng → cơ bản; đắt rẻ → định giá) — không chạy full 3 chiều/mã, không chạy vòng sub-skill thứ hai.

## When to Use

- Dùng khi: user hỏi so sánh/xếp hạng 2–6 mã cùng ngành (`VCB vs BID vs CTG`, `steel mạnh nhất là ai`, `ngân hàng nào đáng mua nhất`).
- Khi KHÔNG dùng (dùng skill khác thay thế):
  - Chỉ 1 mã → `phan-tich-chuyen-sau-1-ma`.
  - Hỏi lẻ 1 chiều 1 mã (RSI → `ky-thuat-chuyen-sau`; BCTC → `co-ban-chuyen-sau`; fair value → `dinh-gia-chuyen-sau`).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 0: xác định mã cùng ngành (tối đa 6 mã)
- [ ] Step 1: bảng nhanh (overview + momentum + giá 1 shot)
- [ ] Step 2: 1 sub-skill/mã, song song tối đa 4
- [ ] Step 3: nền ngành + verdict xếp hạng
```

**Step 0: Xác định mã cùng ngành (gọi trực tiếp).**

Chạy `vn_reference` (industry) hoặc `vs_industry_tree` (tra GICS) → chọn tối đa 6 mã; chỉ cho tên ngành thì dùng `stock_screener` (filter ngành, pool hẹp). Trên 6 mã thì yêu cầu thu hẹp, không tự mở rộng. `vn_reference` industry không match → thử `vs_industry_tree` 1 lần, vẫn không ra thì hỏi lại ngành, không đoán mã.

**Step 1: Bảng nhanh (gọi trực tiếp).**

Chạy `compare_equities` (≤4 mã/lần; 5–6 mã thì chia 4+2 với `peer_compare`) + `vn_equity_quote_batch` (≤6 mã, 1 call): overview + momentum + bảng giá 1 shot.

**Step 2: Gọi sub-skill cho từng mã (dispatch, song song tối đa 4).**

Dispatch `ky-thuat-chuyen-sau` HOẶC `co-ban-chuyen-sau` HOẶC `dinh-gia-chuyen-sau` cho mỗi mã theo câu hỏi. Không gọi trực tiếp `signals_technical` / `financial_detail` / `valuation_run` ở đây.

**Step 3: Nền ngành + validate.**

Chạy `vs_gics_index` (group) làm nền index ngành (1 call). Enrich throttle giờ cao điểm → ratios rỗng → verdict kỹ thuật-only + ghi chú thiếu, không bịa PE/ROE. Thiếu dữ liệu 1 tiêu chí → xếp hạng partial + ghi "n/6 mã có đủ", không loại mã âm thầm.

## Template

ALWAYS use this exact verdict structure, mỗi mục ghi số + provenance:

1. Bảng xếp hạng {mã · PE · ROE · momentum · RS · giá} (`provenance: compare_equities` / `peer_compare` / `vn_equity_quote_batch` + sub-skill Step 2).
2. 1 dòng luận chọn: leader = chất lượng × momentum; định giá tốt = PE thấp trong nhóm ROE cao.
3. Cảnh báo tương quan nhóm khi chia tiền cả nhóm (cross-ref `correlation_matrix`, chỉ tham chiếu).
4. Kết luận 1 câu: chọn mã nào + vì sao.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: So sánh bank
Output: compare_equities VCB-vs-HPG 2.8s · peer_compare cap 6 · vs_gics_index 3 nhóm live · quote_batch 1 request VN30 · HOSE universe 757 mã → peer list ≤6 + sub-skill calls có giới hạn + bảng xếp hạng, ≤8 calls nhà.
---

## 21 · tim-co-hoi-bao-cao-ctck
> File thật: `OpenTrading/skills/tim-co-hoi-bao-cao-ctck/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tim-co-hoi-bao-cao-ctck
description: "Săn cơ hội theo báo cáo phân tích CTCK: bảng rating + giá mục tiêu + upside % đã kiểm chứng giá hiện tại. Luôn dùng skill này khi user hỏi CTCK khuyên mua gì, target mới cho mã nào, hay báo cáo của CTCK nói gì — ví dụ 'CTCK gần đây khuyên mua gì', 'có target mới cho MSN không' — ngay cả khi user không nói rõ muốn 'tìm báo cáo CTCK'."
activation: auto
requires_tools: [mcp__opentrading__analyst_consensus]
tool_budget: 8
triggers:
  keywords: [ctck, khuyên mua, giá mục tiêu, target, báo cáo phân tích, khuyến nghị, rating]
version: 1.2.0
```

# Hunting Broker-Report Opportunities

Khuyến nghị CTCK là INPUT, không phải chân lý — bắt buộc kiểm chứng upside bằng giá hiện tại và kèm disclaimer. Không bao giờ suy diễn khuyến nghị thành "nên mua", không bịa giá mục tiêu khi feed không có.

## When to Use

- Dùng khi: hỏi rating/target/báo cáo CTCK theo feed chung hoặc theo mã cụ thể, cần bảng upside %.
- Khi KHÔNG dùng (dùng skill khác thay thế): rumor/crowd → `phan-tich-sentiment` / `tim-kiem-tin-tuc`; tự định giá → `dinh-gia-chuyen-sau`; backtest → `kiem-chien-luoc-backtest`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: feed chung (1 call duy nhất)
- [ ] Step 2: mã cụ thể + tài liệu gốc + đọc PDF
- [ ] Step 3: kiểm chứng upside 1-2 mã top
- [ ] Step 4: bảng + disclaimer
```

**Step 1: Feed chung (1 call duy nhất).**

Chạy `analyst_consensus` (limit=30) — feed chung không symbol, parse rating + giá mục tiêu từ titles. Báo cáo vĩ mô thì thêm `analyst_consensus` (report_type=macro): lọc báo cáo vĩ mô CTCK (entry section/report); không có dated reports thì dùng số liệu gốc. Feed rỗng thật (cuối tuần) → empty hợp lệ, nới `days` 1 lần duy nhất rồi kết luận.

**Step 2: Mã cụ thể + tài liệu gốc (tuần tự sau Step 1).**

Chạy `analyst_consensus` (symbol, limit=15) + `vs_documents` (symbol, chỉ lấy 1 mã đáng giá nhất) + `web_fetch` (format=pdf, URL báo cáo — đọc nội dung PDF stdlib-only, scan báo trung thực, cap 10 trang/20k ký tự). Hỏi mã cụ thể mà `analyst_consensus` (symbol) empty → đọc feed chung và lọc title chứa mã (title-scrape filter có thể sót), không retry đổi limit.

**Step 3: Kiểm chứng upside (tuần tự, 1–2 mã nổi bật nhất).**

Chạy `stock_overview` (1–2 call) so giá hiện tại vs mục tiêu → upside %. Chỉ kiểm chứng top, không kiểm chứng tất cả.

## Template

ALWAYS use this exact verdict structure:

- Bảng {mã · CTCK · rating · giá mục tiêu · ngày · upside % so giá hiện tại}, lọc trong `days` (default 7).
- Top 3 cơ hội (upside lớn + rating MUA + còn hiệu lực).
- Cột **"đã kiểm chứng"** bắt buộc = Step 3 chạy cho 1–2 mã nổi bật nhất (có `stock_overview`); mã chưa kiểm chứng ghi rõ "chưa kiểm chứng giá hiện tại".
- Disclaimer bắt buộc: khuyến nghị CTCK là INPUT, không phải chân lý — không suy diễn thành "nên mua".
- Provenance: nguồn ngày từ URL/title; nếu `source/date null` (đặc trưng parse titles) → suy ngày từ URL/title + ghi rõ nguồn ngày "không chắc chắn". Đủ bảng ≥5 dòng + kiểm chứng 2 mã top thì dừng, không đào thêm mã ngoài top.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: CTCK khuyên mua gì tuần này
Output: Feed chung **7 reports** — MBB MUA 28,200 · **MSN MUA 89,200 (30/09)** · VPB KHẢ QUAN 30,500 · MSB GIẢM TỶ TRỌNG 13,200 · FRT THEO DÕI 157,000 · filter symbol=VCB/FPT từng empty đúng hiện tượng → bảng ≥5 dòng có upside %, kiểm chứng 2 mã top, ≤8 calls. Thiếu cột "đã kiểm chứng" hoặc thiếu disclaimer thì chưa đạt; bịa target khi feed rỗng thì chưa đạt.
---

## 22 · tim-kiem-tin-tuc
> File thật: `OpenTrading/skills/tim-kiem-tin-tuc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tim-kiem-tin-tuc
description: Săn tin theo từ khóa/mã/phạm vi VN-toàn cầu kể cả rumor (săn web + comments, đối chiếu công bố, verdict 4 cột + nhãn CHƯA XÁC NHẬN). Luôn dùng skill này khi user nêu mã/từ khóa cụ thể hoặc muốn xác minh tin đồn — ví dụ "tin về FPT", "nghe đồn HPG, có thật không" — ngay cả khi user không nói rõ muốn "tìm tin".
activation: auto
requires_tools: [mcp__opentrading__news_symbol]
tool_budget: 10
triggers:
  keywords: [tin về, tìm tin, tin tức về, news về, tin trên, dư luận về, nghe đồn, tin đồn, có thật không]
version: 1.2.1
```


# Hunting News Including Rumors

Rumor có trước tin chính thống — săn cả hai nhưng bắt buộc phân loại rõ chính thống vs CHƯA XÁC NHẬN. Không bao giờ suy diễn rumor thành sự thật, không bỏ nhãn độ tin.

## When to Use

- Dùng khi: user nêu mã/từ khóa/phạm vi cụ thể, muốn săn tin + rumor + dư luận, muốn xác minh tin đồn, muốn phân tích chi tiết 1 tin.
- Khi KHÔNG dùng (dùng skill khác thay thế): digest mặc định không từ khóa → `tin-tuc-nong-viet-nam` / `tin-tuc-nong-quoc-te`; chỉ hỏi crowd/FOMO → `phan-tich-sentiment`; chỉ hỏi rating/target CTCK → `tim-co-hoi-bao-cao-ctck`; chỉ hỏi backtest chiến lược → `kiem-chien-luoc-backtest`.

## Workflow

Copy checklist và tick theo tiến độ (chọn ĐÚNG 1 mode):

```
Task Progress:
- [ ] Mode A (theo mã): news_symbol → săn web + comments → đối chiếu → sentiment
- [ ] Mode B (VN): news_market + corporate → 2-3 mã nổi bật
- [ ] Mode C (toàn cầu): news_market gdelt → geo/event + web EN
- [ ] Verdict 4 cột + nhãn xác nhận
```

**Mode A — Theo mã (+ rumor).**

1. Chạy `news_symbol` (symbol, limit=20) trước. CẤM đi web_search trước khi có kết quả `news_symbol` — web chỉ để xác minh chéo sau.
2. Săn web + comments song song: `web_search` ("tên mã" + "đồn"/"tin đồn"/rumor, tối đa 2 query) → `web_fetch` 1–2 URL đáng ngờ nhất + `fireant_thread` (post_id từ bước 1 — rumor nằm ở replies; Fireant posts giờ có id thật, không bịa post_id).
3. Đối chiếu tuần tự: `corporate_calendar` (symbol) + `company_events` (symbol) — tin có khớp công bố không?
4. Dư luận: `sentiment_score` (symbol). Đủ ≥5 tin đạt chuẩn thì dừng.

**Mode B — VN.**

1. Chạy song song `news_market` (limit=15) + `corporate_calendar` (limit=20).
2. Tuần tự: `news_symbol` × 2–3 mã nổi bật + `web_search` tin nóng nhất để xác minh chéo. Không đào thêm mã ngoài 2–3 mã.

**Mode C — Toàn cầu.**

1. Chạy song song `news_market` (sources=gdelt, limit=10).
2. Song song: `geo_intel` (topic) / `event_stats` (query) + `web_search` (từ khóa EN). GDELT rỗng → thử English 1 lần rồi kết luận "ít coverage ngôn ngữ đó".

**Validate chung.**

`web_search` ẩn khi thiếu key → chỉ dùng Fireant+GDELT + ghi rõ "chưa quét web". Cả 2 nguồn news chết → đọc `snapshot_history` (kind=news_feed), bắt buộc ghi rõ "cache <ngày>".

## Template

ALWAYS use this exact verdict structure:

| Tiêu đề | Tuổi tin | Độ tin cậy + provenance | Triển vọng |
- **Tiêu đề** đầy đủ, có mã liên quan. **Tuổi tin** (mấy giờ/ngày trước — tin cũ >3 ngày với bluechip coi như đã phản ánh giá). **Độ tin cậy** (chính thống / CTCK / Fireant-crowd / ẩn danh-nguồn mở) + provenance (`news_symbol`/`news_market`/Fireant/GDELT/web). **Triển vọng** (tác động tới DN: doanh thu/lợi nhuận/giá — hay chỉ là noise). Tin đồn bắt buộc nhãn `CHƯA XÁC NHẬN` + điều kiện xác nhận (chờ công bố nào, ngày nào).
- Phân tích chi tiết tin quan trọng nhất: Ai nói → nói gì → bằng chứng kèm theo → tác động định lượng được không (VD cổ tức bao nhiêu đồng, thương vụ bao nhiêu tỷ) → kịch bản nếu đúng/sai.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Nghe đồn HPG ... thật không
Output: `news_symbol("VCB")` → lãi suất VCB 0.1-6% posts · GDELT "dầu" live · corporate VCB 487 docs · `fireant_thread` (post PNJ 42088453) → root + 2 replies thật → verdict 4 cột + phân tích chi tiết + nhãn xác nhận, ≤10 calls. Thiếu 1 trong 4 cột verdict → chưa đạt; thiếu nhãn `CHƯA XÁC NHẬN` cho rumor → chưa đạt.
---

## 23 · tin-tuc-nong-quoc-te
> File thật: `OpenTrading/skills/tin-tuc-nong-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tin-tuc-nong-quoc-te
description: Digest tin thế giới tác động thị trường (5 headline + market reaction xác nhận bằng số). Luôn dùng skill này khi user hỏi tin quốc tế/Mỹ/Trung hôm nay — ngay cả khi user không nói rõ muốn "digest tin nóng".
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 8
triggers:
  keywords: [tin quốc tế, tin thế giới, thị trường mỹ, fed tin, wall street, nasdaq]
version: 1.1.0
```

# Digesting Global Hot News With Market Reaction

Tin thế giới + market reaction xác nhận bằng SỐ — không đưa tin suông. Tin chưa có reaction thì bắt buộc ghi "thị trường chưa phản ánh", không bịa reaction. Tin đồn quốc tế bắt buộc nhãn `CHƯA XÁC NHẬN`.

## When to Use

- Dùng khi: tin quốc tế/Mỹ/Trung, Fed, Wall Street, cần headline + số liệu thị trường xác nhận.
- Khi KHÔNG dùng (dùng skill khác thay thế): tin VN → `tin-tuc-nong-viet-nam`; từ khóa riêng/rumor → `tim-kiem-tin-tuc` chế độ C; vĩ mô chuyên sâu (curve, flows, fear/greed riêng lẻ) → `danh-gia-vi-mo-quoc-te`; crypto → `nhip-dap-crypto`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: tin global (song song)
- [ ] Step 2: reaction bằng số (song song, sau Step 1)
- [ ] Step 3: xác minh 1 tin nổi bật nhất
- [ ] Step 4: verdict 5 headline + reaction
```

**Step 1: Tin global (song song).**

Chạy `news_market` (sources=gdelt) + `geo_intel` (không topic = global coverage). Không tự thêm topic hẹp nếu user hỏi chung. GDELT rỗng → thử từ khóa English 1 lần rồi kết luận "ít coverage".

**Step 2: Reaction bằng số (song song, tuần tự sau Step 1 để soi đúng tin).**

Chạy `yf_mega_flows` + `world_fear_greed`.

**Step 3: Xác minh 1 tin nổi bật nhất (tuần tự).**

Chạy `event_stats` cho đúng 1 từ khóa nổi bật nhất, không chạy cho mọi headline. Cả 2 nguồn news chết → đọc `snapshot_history` (kind=news_feed), bắt buộc ghi rõ "cache <ngày>". Feed rỗng cuối tuần → empty hợp lệ, ghi rõ phiên nghỉ.

## Template

ALWAYS use this exact verdict structure: 5 headline, mỗi tin gồm **tiêu đề + tuổi tin + provenance** (GDELT/`geo_intel`) + **market reaction bằng SỐ** (mega-cap flows, fear/greed, curve nếu liên quan rates).

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Tin thế giới
Output: mega_flows AAPL/MSFT/NVDA OK · fear/greed 70-74 Greed 7 ngày → ≥5 headline + ≥2 mục reaction định lượng, ≤8 calls. Thiếu reaction số mà không ghi "thị trường chưa phản ánh" → chưa đạt.
---

## 24 · tin-tuc-nong-viet-nam
> File thật: `OpenTrading/skills/tin-tuc-nong-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tin-tuc-nong-viet-nam
description: Digest tin nóng VN trong ngày (5-7 headline + phân loại + sentiment + provenance). Luôn dùng skill này khi user hỏi chung về tin chứng khoán/thị trường/doanh nghiệp VN hôm nay — ví dụ "tin nóng hôm nay", "có tin gì về VN30" — ngay cả khi user không nói rõ muốn "digest tin nóng".
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 9
triggers:
  keywords: [tin nóng, tin chứng khoán, tin hôm nay, tin vn, tin doanh nghiệp, headline]
version: 1.1.0
```

# Digesting Daily Vietnam News

Digest nhanh tin VN trong ngày — headline + phân loại + sentiment, có provenance rõ ràng. Không suy diễn sentiment heuristic thành khuyến nghị mua/bán.

## When to Use

- Dùng khi: hỏi tin nóng VN hôm nay, VN30, thị trường/doanh nghiệp VN, cần 5–7 headline nhanh.
- Khi KHÔNG dùng (dùng skill khác thay thế): có mã/từ khóa cụ thể hoặc rumor → `tim-kiem-tin-tuc`; tin Mỹ/Trung/toàn cầu → `tin-tuc-nong-quoc-te`; đào sâu crowd/FOMO 1 mã → `phan-tich-sentiment`; rating/target CTCK → `tim-co-hoi-bao-cao-ctck`.

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: tin chung + lịch công bố (song song)
- [ ] Step 2: đào 2-3 mã xuất hiện nhiều nhất
- [ ] Step 3: sentiment + đối chiếu mã nóng nhất
- [ ] Step 4: verdict 5-7 headline
```

**Step 1: Tin chung + lịch công bố (song song).**

Chạy `news_market` (limit=15) + `corporate_calendar` (limit=20).

**Step 2: Đào mã nổi bật (tuần tự sau Step 1).**

Chạy `news_symbol` × 2–3 mã xuất hiện nhiều nhất trong tin — chọn theo tần suất xuất hiện, không theo cảm tính, tối đa 3 mã.

**Step 3: Sentiment + đối chiếu (song song).**

Chạy `sentiment_score` (mã nóng nhất) + `company_events` (mã đó, chỉ để đối chiếu, không đào toàn bộ lịch sử). Thiếu Groq → dùng heuristic + warning, bắt buộc nhãn `heuristic` trong verdict.

**Step 4: Validate trước khi chốt.**

Fireant chết → tự GDELT fallback trong tool, không retry Fireant vô hạn. Cả hai chết → đọc `snapshot_history` (kind=news_feed) cache 1 ngày, bắt buộc ghi rõ là cache + ngày cache. Feed rỗng cuối tuần/nghỉ lễ → empty hợp lệ, ghi rõ "phiên nghỉ, ít tin mới". Đủ 5 headline có provenance thì dừng; đủ verdict Step 3 cho mã nóng nhất thì dừng. Không call lại `sentiment_score` với limit lớn hơn.

## Template

ALWAYS use this exact verdict structure, mỗi headline gồm: **tiêu đề + mã liên quan + phân loại** (catalyst / đồn đoán / tin vĩ mô) + **sentiment** nếu đủ dữ kiện + **provenance** (Fireant/GDELT) + **tuổi tin**. Tin đồn bắt buộc nhãn `CHƯA XÁC NHẬN`.

## Examples

**Example 1 (live 02-10-2026, không bịa số mới):**
Input: Tin nóng hôm nay
Output: Fireant posts 02-10 (quỹ bình ổn xăng dầu về KBNN; đất nền HN đổi tâm lý; chiến dịch làm sạch mã số thuế) · `news_symbol("VCB")` → posts lãi suất 0.1-6% → ≥5 headline có provenance, ≤9 calls. Thiếu provenance hoặc thiếu phân loại thì chưa đạt; sentiment không nhãn nguồn thì chưa đạt.
---

## 25 · ve-bieu-do-ky-thuat
> File thật: `OpenTrading/skills/ve-bieu-do-ky-thuat/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: ve-bieu-do-ky-thuat
description: "Vẽ biểu đồ ngay trong TUI (nến, đường giá, sparkline, bar, gauge, heatmap, donut, histogram, so sánh nhiều mã, depth orderbook) có màu ANSI. Luôn dùng skill này khi user nói vẽ, chart, nến, candlestick hay xin xem bias giá bằng hình — ví dụ 'vẽ nến VCB', 'so chart VCB vs HPG' — ngay cả khi user không nói rõ muốn 'vẽ biểu đồ'."
activation: auto
requires_tools: [chart_render]
triggers:
  keywords: [vẽ, chart, nến, candlestick, đường giá, sparkline, biểu đồ, đồ thị, so sánh, bar, gauge, heatmap, donut, histogram, fear, greed, tương quan, tỷ trọng]
tool_budget: 8
version: 1.2.1
```


# Drawing Charts Inside the TUI

Skill thuần hiển thị: số liệu lấy từ tool dữ liệu mỗi lần gọi, không có số live cố định — không bịa số minh họa thành số thật. Dùng lại dữ liệu đã có trong context, không fetch lại.

## When to Use

- Dùng khi: user nói vẽ, chart, nến, candlestick, đường giá, sparkline, so sánh 2–5 mã, bar ngành/top tăng giảm, gauge fear/greed, heatmap tương quan, donut tỷ trọng, histogram phân phối, depth orderbook.
- Khi KHÔNG dùng (dùng skill khác thay thế): phân tích chữ thuần (chỉ dùng `ky-thuat-chuyen-sau`); định giá chi tiết (chỉ dùng `dinh-gia-chuyen-sau`).

## Lookup: Data Tool to Chart Kind

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

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: lấy dữ liệu (dùng lại trong context nếu có)
- [ ] Step 2: vẽ (đúng kind + màu)
- [ ] Step 3: verdict 2-3 câu
```

**Step 1: Lấy dữ liệu.**

Lấy tool dữ liệu theo bảng tra trên. Chọn nguồn đúng trước khi vẽ: mã VN → `vn_equity_ohlcv`/`vn_quote_history` (KHÔNG dùng `vn_crypto_ohlcv` cho cổ phiếu); crypto USD → `crypto_spot`. Thiếu thì báo trung thực, không vẽ chay. Ngưỡng tối thiểu: candlestick ≥5 nến; line/sparkline/area/winloss ≥2 điểm; histogram ≥5 điểm; heatmap matrix phi rỗng; gauge/donut cần value+max. Chưa đủ thì không vẽ, báo thiếu data.

**Step 2: Vẽ.**

Chạy `chart_render` (+symbol) hoặc `chart_compare`. Màu ANSI tự theo chiều (tăng xanh/giảm đỏ); `color=never` khi user copy text thuần. Rộng mặc định 64 ký tự (không vượt 100 để khỏi vỡ wrap TUI); cao nến 14, line 10, compact 1–8.

**Step 3: Verdict.**

Đọc từ hình + số: trend, HH/LL, vị trí giá vs range. 2–3 câu, ghi đơn vị kVND (57.3 = 57,300đ). Chart dài tự collapse sau 3 dòng (ctrl+o mở rộng) — không tóm tắt hình bằng lời dài. Ngoài giờ DNSE thì orderbook rỗng là đúng, `chart_depth` báo rỗng, không retry.

## Template

ALWAYS use this output structure: hình chart (giữ nguyên ký tự ANSI) + verdict 2–3 câu (trend, HH/LL, vị trí giá vs range, đơn vị kVND).

## Examples

**Example 1:**
Input: vẽ nến VCB 30 phiên
Output: 1 call data + 1 call `chart_render` + hình nến màu + verdict ≤3 câu, ≤8 calls.
---

## 26 · vn-market-basics
> File thật: `OpenTrading/skills/vn-market-basics/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: vn-market-basics
description: "Giải thích cơ chế giao dịch chứng khoán Việt Nam (sàn HOSE/HNX/UPCoM, phiên ATO/liên tục/ATC, biên độ, bước giá, lô, chu kỳ thanh toán T+2, loại lệnh LO/MP). Luôn dùng skill này khi user hỏi quy định/cơ chế giao dịch — ví dụ 'biên độ HOSE bao nhiêu', 'lô chẵn lô lẻ là sao' — ngay cả khi user không nói rõ muốn 'hỏi cơ chế'."
activation: auto
triggers:
  keywords: [biên độ, bước giá, lô chẵn, lô lẻ, ATO, ATC, loại lệnh, thanh toán T, phiên giao dịch]
version: 1.2.0
```

# Explaining Vietnam Market Mechanics

Trả lời gọn theo từng sàn (nếu khác nhau) + ghi chú KRX/CCP/nâng hạng có thể đã cũ + 1 dòng khuyên đối chiếu nguồn chính thức. Không bao giờ đưa ra con số giá hay chỉ số thị trường hiện tại trong skill này.

## When to Use

- Dùng khi: user hỏi sàn HOSE/HNX/UPCoM, phiên ATO/liên tục/ATC, biên độ giá, bước giá, lô chẵn/lẻ, chu kỳ thanh toán, loại lệnh (LO, MP, ATO, ATC...).
- Khi KHÔNG dùng (dùng skill khác thay thế): hỏi P/E, EPS, ROE, margin là gì (chỉ dùng `explain-term`); hỏi mã đang nắm có nên giữ không (chỉ dùng `devil-advocate`); xin giá/chỉ số hiện tại (chỉ dùng skill phân tích).

## Workflow

Copy checklist và tick theo tiến độ:

```
Task Progress:
- [ ] Step 1: xác định sàn liên quan (tách HOSE/HNX/UPCoM)
- [ ] Step 2: trả lời theo quy tắc KRX hiện hành + ghi chú có thể đã cũ
- [ ] Step 3: khuyên đối chiếu nguồn chính thức
```

**Step 1: Xác định sàn liên quan.**

Phân biệt rõ HOSE/HNX/UPCoM khi quy định khác nhau; không gộp biên độ/bước giá/lô cả 3 sàn thành 1 số.

**Step 2: Trả lời theo quy tắc KRX hiện hành.**

Quy định thay đổi theo thời gian (hệ thống KRX, lộ trình CCP, nâng hạng FTSE) — bắt buộc nói rõ thông tin theo hiểu biết của model, có thể đã cũ. Nói chắc chắn về quy định mới mà không ghi chú này là sai.

**Step 3: Khuyên đối chiếu nguồn chính thức.**

Bắt buộc khuyên user đối chiếu thông báo của sở giao dịch hoặc CTCK. Không tiện trả lời kèm giá hiện tại — chỉ cơ chế, không số thị trường.

## Template

ALWAYS use this exact output structure: trả lời gọn theo từng sàn (nếu khác nhau) · ghi chú KRX/CCP/nâng hạng có thể đã cũ · 1 dòng khuyên đối chiếu nguồn chính thức.

## Examples

**Example 1:**
Input: Biên độ HOSE bao nhiêu
Output: số theo sàn + ghi chú KRX có thể cũ + dòng khuyên đối chiếu sở/CTCK, không kèm giá thị trường.
---
