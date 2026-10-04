# Skills Design cho Harness — opentrading-mcp (2026-10-02, rev.3)

**Mục đích**: spec hoàn chỉnh để team harness TỰ BUILD **22 skills** trên nền 135 MCP tools.
Không cần code thêm phía server — mọi workflow đã verify live 2026-10-02 (số liệu thật
trong từng skill là evidence thật, không minh họa).

**rev.3**: còn **22 skills** — xóa S2/S10/S11/S12/S14/S18 (tools chuyển home hoặc park
"chờ duyệt" trong ma trận); S1/S13/S15/S16/S17/S19/S21/S22/S25 viết lại theo workflow mới;
thêm S28 kiểm tra nguồn dữ liệu 1 lượt. (rev.2 trước đó: tách S1 thành điều phối + 6 skill
chuyên S22–S27, thêm S20/S21.)

- Nguồn tool catalog chi tiết: `docs/tools-review-2026-09-24.md` (bảng 135 tools + 6 workflows).
- Nguồn kiến trúc/bảo mật/kết nối: `docs/architecture-review-2026-09-30.md`.
- Skill format theo chuẩn opencode skills: `SKILL.md` frontmatter + body markdown.

---

# PHẦN 0 — CONTRACT CHUNG (mọi skill phải theo)

## 0.1 Kết nối MCP

```json
{
  "mcp": {
    "servers": {
      "opentrading": {
        "type": "remote",
        "url": "https://opentrading-mcp-web.onrender.com/mcp",
        "headers": { "Authorization": "Bearer <TEAM_TOKEN>" },
        "oauth": false,
        "timeout": 120000
      }
    }
  }
}
```

- `type: "remote"` (KHÔNG phải `streamable-http`); `oauth: false` (BẮT BUỘC — server là
  resource-server thuần, không OAuth endpoints).
- Prod serve preset `all` = 136 tools (135 + web_search khi có key).
- Timeout call ≥120s (nhiều tool upstream chậm; opencode mặc định 30s là NGUYÊN NHÂN
  timeout oan — đã kết luận từ live run).

## 0.2 Envelope contract — branch theo availability

Mọi tool trả `{data, provenance{source,as_of,tz=Asia/Ho_Chi_Minh}, warnings[], availability}`:

| availability | Skill phải làm gì |
|---|---|
| `available` | dùng số liệu, trích provenance vào output |
| `partial` | dùng leg còn sống, ghi rõ leg nào chết vì sao (từ warnings) |
| `empty` | báo "không có" — ĐÂY LÀ KẾT QUẢ HỢP LỆ, không retry, không bịa |
| `stale` | dùng nhưng ghi timestamp + cờ cảnh báo |
| `unavailable` | đọc `warnings[]` lấy tool fallback được gợi ý, thử fallback 1 lần duy nhất |

Quy tắc vàng: **không bao giờ available-giả** — server đã thiết kế honest-availability,
skill không được đấm ngược lại (vd fill PE null bằng số suy đoán).

## 0.3 Ngân sách & chống gọi tràn lan (lý do tồn tại của skills)

- `tool_budget` ghi trong frontmatter từng skill: số call tối đa mỗi run (6–12 tùy skill).
  **Nguyên tắc rev.2: một skill không dùng quá ~8 tools trong một run điển hình** — skill nào
  phình (bản S1 cũ 14 tools) phải tách thành skill điều phối + skill chuyên (xem S22–S27).
- **CHỈ gọi tools có trong home list của skill** (cross-ref cho phép, ngoài bảng = từ chối
  hoặc đề nghị chuyển skill).
- Mỗi wave xong mới xét wave sau — bước sau dùng dữ kiện bước trước, không gọi dự phòng.
- `empty` = không có thì dừng nhánh đó, không đổi params retry liên tục.
- LLM KHÔNG cần đọc hết 136 descriptors: trigger `description` của skill chọn đúng 1 skill,
  làm theo bảng workflow trong skill.

## 0.4 Song song hóa

- Các call độc lập trong cùng wave → dispatch đồng thời, **≤5 call/wave** (vnstock
  throttle khi burst >5 — evidence live).
- Cùng upstream `vs_*` (Vietstock) → ≤4/wave. `yf_*` (Yahoo) → ≤3/wave.
- Tools batch có sẵn, ƯU TIÊN thay vì bắn lẻ: `market_candles_batch`,
  `vn_equity_quote_batch`, `compare_equities`, `correlation_matrix`, `signals_technical`
  (đã gồm nhiều indicator 1 call).
- Rate-limit server 120 req/phút → burst ≤20; gặp 429 chờ đúng `Retry-After`, không spam.

## 0.5 Pre-flight (2 call, đếm vào budget, chạy đầu MỌI skill)

1. `source_status` — upstream nào chết? (JWT hết hạn, vnstock throttle, WS cold)
2. `vs_auth_status` — chỉ khi skill dùng `vs_*`/BCTC: JWT còn hạn không? Hết → switch
   sang nhánh `vs_financeinfo` (mirror free) và ghi chú trong output.

## 0.6 Quy ước đặt tên skill

- Slug KHÔNG dấu, kebab-case: `phan-tich-chuyen-sau-1-ma` (an toàn filesystem/git).
- Title + body tiếng Việt; description frontmatter 1–2 câu, có "Dùng khi…" và
  "Không dùng khi…" (skill sau phải tự loại khỏi scope skill trước).

---

# PHẦN 1 — 22 SKILLS (rev.3)

Mỗi skill: frontmatter → workflow bảng → verdict → chống tràn lan → failure modes →
evidence live → acceptance test.

## S1. `phan-tich-chuyen-sau-1-ma` (rev.3 — workflow mới của bạn)

```yaml
name: phan-tich-chuyen-sau-1-ma
description: >
  Dùng khi yêu cầu phân tích TOÀN DIỆN một mã cụ thể ("phân tích FPT").
  Skill ĐIỀU PHỐI: tự làm nhận diện + ngành + tin + sự kiện, dispatch kỹ thuật/
  định giá sang sub-skills rồi gộp verdict. Không dùng khi: sàng lọc nhiều mã,
  hỏi thị trường chung.
tool_budget: 8 / 2 song song
inputs: symbol (bắt buộc)
```

| Bước | Việc | Tools |
|---|---|---|
| 1. Xác định mã | Chuẩn hóa mã CK (VCB, BID...) | `symbol_lookup` (khi nghi tên) |
| 2. Ngành + kiếm tiền nhờ đâu | Ngành (GICS), mô hình kinh doanh, nguồn thu chính | `vn_company` · `vs_company_info` · `vs_industry_tree` |
| 3. Trạng thái kỹ thuật | Dispatch S22 | reuse `ky-thuat-chuyen-sau` |
| 4. Định giá | Dispatch S24 | reuse `dinh-gia-chuyen-sau` |
| 5. Lợi nhuận các quý gần đây | KQKD 4 quý + so QoQ/YoY, biên | `financial_detail` (cross-ref S23) |
| 6. Tin tức doanh nghiệp | Tin + công bố | `news_symbol` (cross-ref S26) · `company_events` |
| 7. Sự kiện tương lai | Lịch 30–90 ngày (BCTC/ĐHĐCĐ/cổ tức) | `event_calendar_vn` |
| 8. Tổng hợp | **Điểm tích cực + tiêu cực + động lực tương lai của mã** | `evidence_bundle` (khóa verdict) |

**Verdict template**: 1 câu nhận định · ngành + cách kiếm tiền (2 dòng) · kỹ thuật (từ S22)
· định giá (từ S24) · lợi nhuận quý (số + trend) · tin + sự kiện sắp tới · **bảng Tích cực /
Tiêu cực / Động lực tương lai**.

**Chống tràn lan**: S1 KHÔNG gọi trực tiếp tools của sub-skills (trừ `financial_detail`
bước 5 — vì cần số quý nhanh, không cần full S23); user chỉ hỏi 1 chiều → chạy sub-skill
đó, không chạy S1.

**Failure modes**: thiếu mã ngành (mã mới) → ghi "chưa phân loại", vẫn chạy các bước còn.

**Evidence live**: VCB — bank, thu từ tín dụng; RSI 39.2; per_pb 57.3k; F 4/6; cổ tức 450đ
ex 23-07; FPT — công nghệ, M −2.06 sạch, KH 58,580.

**Acceptance**: "phân tích FPT" → đủ 8 bước, bảng 3 cột tích cực/tiêu cực/động lực, ≤8 calls S1.

## S3. `danh-gia-vi-mo-viet-nam` (rev.3 — Vietstock bắt buộc + câu chuyện dẫn dắt)

```yaml
name: danh-gia-vi-mo-viet-nam
description: >
  Dùng khi hỏi vĩ mô VN: GDP, CPI, xuất nhập khẩu, tỷ giá, lãi suất điều hành, lịch
  công bố số liệu, câu chuyện dẫn dắt thị trường. Không dùng khi: vĩ mô Mỹ/toàn cầu.
tool_budget: 12 / 4 song song
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 | `source_status`, `vs_auth_status` | pre-flight |
| 1. Dữ liệu vĩ mô VN chi tiết từ Vietstock (BẮT BUỘC) | `vs_categories` (tra id nếu cần) → `vs_indicator_data` GDP(73,tt3) · CPI(15,tt7,sub2) · XK(38,tt2) · `vs_xnk_detail` (xk + nk) | cặp category/termType phải đúng |
| 2. Tin tức vĩ mô kinh tế | `news_market` (lọc vĩ mô/lãi suất/tỷ giá) · `macro_events_vn` · `economic_calendar` | Fireant/GDELT + NSO |
| 3. Báo cáo vĩ mô của CTCK | `analyst_consensus` (limit=30, lọc title chứa GDP/CPI/lãi suất/tỷ giá/vĩ mô) | đặc trưng title-scrape: lọc client-side |
| 4. Data bổ sung | `snapshot_history` (macro_curated — baseline so sánh số mới/cũ) · `yf_yield_curve` + DXY (bối cảnh hút vốn ngoại) · `sbv_rates` · `vn_retail_fx` | mỗi thứ 1 call |
| 5. Lịch sự kiện câu chuyện | `macro_events_vn` (NSO) + kỳ họp Fed/Mỹ từ S9 cross-ref | lịch VN + lịch ngoại tác động VN |

**Verdict**: tăng trưởng · lạm phát · thương mại · tỷ giá · lãi suất · **điểm tích cực /
tiêu cực · triển vọng tương lai · câu chuyện dẫn dắt thị trường + lịch sự kiện của câu
chuyện đó** (mỗi câu chuyện: sự kiện nào, ngày nào, tác động gì).

**Chống tràn lan**: không quét 60 categories — 4–6 series đủ; `analyst_consensus` 1 call
feed chung rồi lọc, không bắn theo từng từ khóa.

**Failure modes**: thiếu HAR session → macro trả permission message → nói trung thực +
dùng `snapshot_history`; feed CTCK cuối tuần rỗng = empty hợp lệ.

**Evidence live**: GDP 504 rows tới Q2/2026 · CPI 1,839 · XK 2,941 · XNK 3,675 · SBV 4.5%/3% ·
USDVND 25,970.

**Acceptance**: "vĩ mô VN" → đủ 6 mục + câu chuyện dẫn dắt có lịch sự kiện, ≤12 calls.

## S4. `danh-gia-vi-mo-quoc-te`

```yaml
name: danh-gia-vi-mo-quoc-te
description: >
  Dùng khi hỏi kinh tế Mỹ/toàn cầu: Fed ngoài bối cảnh dự đoán xác suất, lợi suất,
  việc làm, GDP các nước, chế độ risk. Không dùng khi: VN (→ S3), xác suất Fed (→ S9).
tool_budget: 10 / 3 song song (yf)
```

| Wave | Tools |
|---|---|
| 1 | `fred_series`(DGS10) · `fred_series`(CPIAUCSL) · `yf_yield_curve` |
| 2 | `yf_regime_assets` · `assets_rotation` · `world_macro_country`(VN/CHINA theo câu hỏi) |
| 3 | `yf_global_indices` · `yf_commodities` · `world_fear_greed` |

**Verdict**: chu kỳ Mỹ (soft/hard landing, dựa DGS10+CPI+curve) · đường cong (inverted?) ·
chế độ toàn cầu (RISK-ON/OFF từ rotation) · **so sánh VN-vs-global 1 dòng bắt buộc**
(GDP VN từ S3 cross-ref vs Mỹ/CN) · biến số theo dõi.

> Review rev.3: ỔN, giữ nguyên + dòng VN-vs-global trên.

**Chống tràn lan**: fred series GỌI THEO TÊN (≥3 series cùng lúc là dấu hiệu đọc descriptor
tràn lan — dừng). yf wave ≤3.

**Failure modes**: FRED thiếu key → `unavailable`, chuyển nhánh không-FRED và ghi chú;
curve từng flaky (live run thấy fail→tự hồi) → retry 1 lần sau backoff, rồi bỏ.

**Evidence live**: US10Y 5.24% / 2Y 4.61%, không đảo chiều · WorldBank GDP VN 8.02% ·
fear/greed crypto 70–74 (tham lam).

**Acceptance**: "kinh tế Mỹ hiện tại" → 5 mục verdict, curve + ≥2 series fred có spark.


## S5. `danh-gia-tinh-hinh-chinh-tri-toan-cau`

```yaml
name: danh-gia-tinh-hinh-chinh-tri-toan-cau
description: >
  Dùng khi hỏi rủi ro chính trị/bầu cử/căng thẳng quốc tế ("địa chính trị tuần này",
  "bầu cử Brazil", "rủi ro chính sách"). Xung đột vũ trang cụ thể → S6. Fed → S9.
  Bất ổn một quốc gia → S20. Chỉ xin odds → S21.
tool_budget: 8
```

| Wave | Tools |
|---|---|
| 1 | `world_prediction_odds`(tag=fed/politics/elections theo câu hỏi) · `geo_intel`(topic) — 2 tool này home ở S21/S20, S5 dùng cross-ref |
| 2 | `polymarket_event`(slug top 1–2) · `event_stats`(query) |
| 3 | `news_market(sources=gdelt)` · `web_fetch`(1–2 nguồn chính thức trong tin) |

**Verdict**: bản đồ rủi ro 4–6 mục: sự kiện + xác suất (prob_pct) + volume thanh khoản
(độ tin của odds) + tin GDELT xác nhận + market-impact nếu có (cross-ref S4 bối cảnh toàn cầu).

**Chống tràn lan**: odds sort vol24h mặc định — lấy top 5, không kéo cả 20 event;
`polymarket_event` chỉ cho event THẬT SỰ liên quan câu hỏi.

**Failure modes**: GDELT rate-limit (đã gặp live: fail → backoff 20s → hồi) — 1 lần;
Gamma proxy (jina) chậm → fallback direct, chờ 1 lần.

**Evidence live**: Fed October 2026: "no change" **74.5%** (volume 24h ~2.6M USD) ·
Brazil presidential event detail OK.

**Acceptance**: "rủi ro chính trị toàn cầu" → ≥4 mục có prob_pct + provenance event URL.

> Review rev.3: ỔN — S5 là skill tổ chức cross-ref (tools home ở S20/S21), giữ nguyên thiết kế.


## S6. `danh-gia-tinh-hinh-xung-dot`

```yaml
name: danh-gia-tinh-hinh-xung-dot
description: >
  Dùng khi hỏi xung đột/chiến tranh cụ thể ("Trung Đông", "Biển Đông", "chiến sự
  X ảnh hưởng gì thị trường"). Chính trị bầu cử → S5.
tool_budget: 9
```

| Wave | Tools |
|---|---|
| 1 | `geo_intel`(topic xung đột) · `event_stats`(query) |
| 2 | `yf_commodities`(dầu + vàng) · `assets_rotation` |
| 3 | `world_prediction_odds`(từ khóa cuộc chiến) · `web_search`(nếu có key)/`web_fetch` |

**Verdict**: cường độ (event counts GDELT trend) · giá đã phản ánh chưa (dầu/vàng move
vs baseline) · kênh truyền dẫn (energy→inflation→rates) · xác suất leo thang (odds) ·
hàm ý vị thế (cross-ref S13 điểm 6 cushion/size trước khi hành động).

**Chống tràn lan**: 1 topic/call; từ khóa THỬ cả tiếng Việt lẫn Anh ("biển đông" →
"south china sea") — tối đa 2 lần thử rồi chấp nhận "ít coverage".

**Failure modes**: GDELT rỗng với từ khóa VN → chuyển English query là ĐẶC TRƯNG data,
không phải lỗi, ghi chú.

**Evidence live**: geo_intel("Vietnam") trả articles (ĐT Việt Nam...); event_stats("vietnam")
articles >0; gold 4,195 USD/oz live cùng phiên.

**Acceptance**: "xung đột X ảnh hưởng gì" → 5 mục verdict, có số dầu/vàng phiên gần nhất.

> Review rev.3: ỔN, giữ nguyên.


## S7. `tin-tuc-nong-viet-nam`

```yaml
name: tin-tuc-nong-viet-nam
description: >
  Dùng khi hỏi tin nóng trong ngày về thị trường/doanh nghiệp VN ("tin chứng khoán
  hôm nay", "có tin gì về VN30"). Tin theo TỪ KHÓA/mã cụ thể → S19. Tin thế giới → S8.
tool_budget: 9
```

| Wave | Tools |
|---|---|
| 1 | `news_market`(limit=15) · `corporate_calendar`(limit=20) |
| 2 | `news_symbol` × 2–3 mã xuất hiện nhiều nhất trong tin |
| 3 | `sentiment_score`(mã nóng nhất) · `company_events`(mã đó) |

**Verdict**: 5–7 headline, mỗi tin: tiêu đề + mã liên quan + phân loại
(catalyst/đồnđãi/tinvĩmô) + sentiment nếu đủ dữ kiện + provenance (Fireant/GDELT).

**Chống tràn lan**: tối đa 3 mã được đào thêm ở wave 2 (chọn theo tần suất xuất hiện,
không theo cảm tính); `sentiment_score` heuristic fallback (thiếu Groq) → ghi nhãn
"heuristic" vào output, không diễn giải thành "phố tin/bán".

**Failure modes**: Fireant chết → tự GDELT fallback (bên trong tool); cả hai chết →
`snapshot_history(kind=news_feed)` đọc cache 1 ngày, GHI RÕ là cache.

**Evidence live**: Fireant posts 02-10 (quỹ bình ổn xăng dầu về KBNN; đất nền HN đổi
tâm lý; chiến dịch làm sạch mã số thuế); `news_symbol("VCB")` → posts lãi suất 0.1–6%.

**Acceptance**: "tin nóng hôm nay" → ≥5 headline có provenance, ≤9 calls.

> Ghi chú rev.3: S7/S8 KHÔNG liên quan server 8010 cũ — 8010 đã retire (dbinit.py:3),
> nguồn tin là Fireant→GDELT hoàn toàn mới.


## S8. `tin-tuc-nong-quoc-te`

```yaml
name: tin-tuc-nong-quoc-te
description: >
  Dùng khi hỏi tin thế giới tác động thị trường ("tin quốc tế", "thị trường Mỹ/Trung
  hôm nay"). VN → S7. Từ khóa riêng → S19 chế độ C.
tool_budget: 8
```

| Wave | Tools |
|---|---|
| 1 | `news_market(sources=gdelt)` · `geo_intel`(không topic = global coverage) |
| 2 | `yf_mega_flows` · `world_fear_greed` |
| 3 | `event_stats`(từ khóa tin nổi bật nhất) |

**Verdict**: 5 headline + market reaction xác nhận bằng SỐ (mega-cap flows, fear/greed,
curve nếu liên quan rates) — tin chưa có reaction thì ghi "thị trường chưa phản ánh".

**Evidence live**: mega_flows AAPL/MSFT/NVDA OK; fear/greed 70–74 Greed 7 ngày.

**Acceptance**: "tin thế giới" → ≥5 headline + ≥2 mục reaction định lượng.

> Ghi chú rev.3: như S7 — không kế thừa gì từ 8010 (đã retire).


## S9. `du-doan-fed`

```yaml
name: du-doan-fed
description: >
  Dùng khi hỏi xác suất/kịch bản lãi suất Fed ("Fed tháng tới", "cắt hay giữ",
  "dot plot", "FOMC"). Bối cảnh vĩ mô Mỹ chung → S4.
tool_budget: 8
```

| Wave | Tools |
|---|---|
| 1 | `world_prediction_odds`(query=fed) |
| 2 | `polymarket_event`(slug fed-decision-*) · `fred_series`(DGS10 [+ EFFR/DFII nếu cần]) |
| 3 | `yf_yield_curve` · `web_fetch`(fed.gov statement/nguồn chính thức trong odds) |

**Verdict**: xác suất từng kịch bản (cắt/giữ/tăng, prob_pct + volume + end-date) · đường
cong thị trường ám chỉ (curve, kỳ hạn cắt qua giá) · lịch FOMC kế tiếp · biến số theo dõi
(CPI Mỹ, jobs) · hàm ý cho VN (tỷ giá, cross-ref S3/S16).

**Chống tràn lan**: CHỈ 1 event fed chính (slug mới nhất, sort vol24h đã tự xếp) — không
bắn 5 query biến thể.

**Failure modes**: odds stale (end date qua) → lọc theo `end > today`; Gamma chết cả
proxy+lần → nói rõ "không có odds", KHÔNG thay bằng nhận định riêng.

**Evidence live**: "Fed Decision in October 2026": Yes(no change) **74.5% / No 25.5%**,
volume24h 2.6M; curve US10Y 5.24% không đảo.

**Acceptance**: "Fed tháng tới" → prob ≥2 kịch bản + lịch họp + 1 dòng hàm ý VN.


## S13. `danh-gia-truoc-bctc` (rev.3 — 6 điểm kiểm tra quý hiện tại)

```yaml
name: danh-gia-truoc-bctc
description: >
  Dùng khi mùa BCTC cận kề: kiểm tra setup quý HIỆN TẠI của 1 mã ("FPT quý này sao",
  "HPG có bị phân phối không"). Phân tích mã không liên quan earnings → S1.
tool_budget: 10
inputs: symbol
```

| # | Điểm kiểm tra | Tools |
|---|---|---|
| 1. Tăng giá quý hiện tại | % tăng từ đầu quý tới nay, so VNINDEX cùng kỳ | `vn_quote_history` (cross-ref S22) + `vn_index_ohlcv` |
| 2. Phân phối (vol cao bất thường) | Volume các phiên gần nhất vs trung bình 20 phiên; giá đi ngang/giảm trong khi vol cao = dấu hiệu phân phối | volume trong nến `vn_quote_history` (tính local, không tool mới) |
| 3. Định giá rẻ/đắt vs lịch sử | PER/PB hiện tại vs dải 2 năm | reuse `dinh-gia-chuyen-sau` (S24) |
| 4. BCTC quý trước bất thường? | M-Score/F-score + đọc dòng bất thường | reuse `co-ban-chuyen-sau` (S23, aspect=chataluong) |
| 5. Dự đoán quý này (giá hàng hóa theo ngành) | Map ngành → hàng hóa ảnh hưởng, lấy giá quốc tế làm input đoán KQKD | bảng map dưới + `yf_commodities`/`compare_assets` (cross-ref S16) |
| 6. Tin tức quý này | Tin + rumor + sentiment để dự đoán | `news_symbol` + `phan-tich-sentiment` (S26) |

**Bảng map ngành → hàng hóa (dùng cho điểm 5)**:

| Ngành VD | Mã VD | Hàng hóa xem | Tool |
|---|---|---|---|
| Thép | HPG, HSG, NKG | Giá thép HRC, quặng sắt | `yf_commodities` + `compare_assets` |
| Dầu khí | GAS, PVD, PVS | Brent/WTI, giá dầu | `yf_commodities` (oil tickers) |
| Cao su | GVR, DPR, PHR | Giá cao su TOCOM/SICOM | `yf_commodities` |
| Cà phê/nông sản | — | Coffee C (KC=F), lúa mì | `yf_commodities` |
| Ngân hàng | VCB, BID, CTG | Lãi suất (SBV + US10Y), tăng trưởng tín dụng | `sbv_rates` + `fred_series` |
| BĐS/KCN | VIC, VHM, KBC | Lãi suất + giải ngân đầu tư công (tin vĩ mô) | `sbv_rates` + S3 cross-ref |
| Khác | — | Mặc định: giá dầu + vàng + USD (bối cảnh chung) | `yf_commodities` |

**Verdict**: grade **A/B/C** + 6 dòng evidence (mỗi điểm 1 dòng) + dự đoán quý này
(TỐT/XẤU/TRUNG TÍNH + lý do giá hàng hóa) + unknowns.

**Chống tràn lan**: không forecast số EPS (VN không consensus) — chỉ nêu hướng;
commodity chỉ lấy tickers trong map, không quét cả bảng.

**Failure modes**: ngành chưa có trong map → dùng mặc định dầu/vàng/USD + ghi chú;
nến quý hiện tại <10 phiên → điểm 1–2 "thiếu dữ liệu", vẫn chấm 4 điểm còn.

**Evidence live**: FPT — M −2.06 sạch · KH 58,580 · pt 0% (không phân phối) · sentiment
−0.25 → grade B (bản cũ).

**Acceptance**: "HPG quý này sao" → đủ 6 điểm + bảng commodity của ngành thép, ≤10 calls.

## S15. `kiem-chien-luoc-backtest` (rev.3 — code + pipeline 4 loại điều kiện)

```yaml
name: kiem-chien-luoc-backtest
description: >
  Dùng khi kiểm chứng chiến lược: trạng thái kỹ thuật, theo thời gian, sau sự kiện,
  theo giá hàng hóa. Rủi ro vị thế cụ thể → S13/S14-logic trong S13.
tool_budget: 12 / timeout-call 120s
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Dữ liệu | `vn_quote_history` (stock) hoặc `dnse_ohlc_history` (futures/index) · `vn_index_ohlcv` (benchmark) | 1 symbol/lần |
| 2. Điều kiện KỸ THUẬT | `backtest_strategies` (sma/momentum/buy_hold — engine hiện tại) | **Phase B**: thêm strategy `rsi_threshold` (vd mua khi RSI<30) + params |
| 3. Điều kiện THỜI GIAN | `seasonality` (tháng/quý nào thường tăng giảm) | **Phase B**: thêm filter `months`/`quarters` vào engine (chỉ giao dịch kỳ chọn) |
| 4. Điều kiện SAU SỰ KIỆN | `event_calendar_vn` (ngày chia cổ tức/ĐHĐCĐ) + lịch Tết (local: Tết Nguyên đán ±N phiên) | **Phase B**: thêm `event_window` engine (list ngày + offsets, vd T-10→T+5) |
| 5. Điều kiện GIÁ HÀNG HÓA | `yf_commodities`/`compare_assets` (lấy series dầu/vàng/thép theo map S13) | **Phase B**: thêm `condition_asset` + rule vào engine (join 2 series) |
| 6. Tổng hợp | `param_sweep` (≤30 combos) · `correlation_matrix` · `portfolio_optimize` (nhiều mã) | best KÈM worst (chống overfit) |

**Pipeline chuẩn mỗi run**: baseline buy-hold → chiến lược → sweep → seasonality →
kết luận "đáng tin / đáng nghi + lý do". Ghi rõ engine numpy-only, cost mặc định, T+2 VN
chưa model.

**Chống tràn lan (hiện tại, trước Phase B)**: 4 loại điều kiện trên — engine MỚI làm được
(1) sma/momentum + (3-nửa: seasonality mô tả); các điều kiện (2-RSI/thời gian/sự kiện/
hàng hóa) skill PHẢI nói rõ "chưa backtest được bằng engine, mới phân tích mô tả" —
không giả vờ đã test. Sau Phase B: chạy đủ pipeline.

**Failure modes**: sweep >3 symbol/run → từ chối; combos vượt 30 → engine tự cap.

**Evidence live**: VCB buy-hold −4.9% · sma_cross 6 trades −8.7% · sweep best +7.1% (fast
10/slow 20) · seasonality tháng 1 mean +4.67%.

**Acceptance**: "backtest mua RSI<30 FPT" → hiện tại: trả lời trung thực "engine chưa hỗ
trợ, mới có seasonality + gợi ý"; sau Phase B: full pipeline + bảng kết quả.

## S16. `phan-tich-vang-ty-gia` (rev.3 — 5 điểm)

```yaml
name: phan-tich-vang-ty-gia
description: >
  Dùng khi hỏi vàng/tỷ giá: giá vàng TG + TA vàng + rủi ro địa chính trị, so lệch
  VN–TG để dự đoán vàng VN, lãi suất 2 đầu, dự đoán polymarket, bối cảnh macro.
tool_budget: 10
```

| # | Điểm | Tools |
|---|---|---|
| 1. Giá vàng quốc tế + TA vàng | Giá XAUUSD + đọc trend/momentum trên nến daily (S22-logic thủ công: giá vs SMA20/50, RSI ước từ `yf_commodities` series) | `yf_commodities` (GC) · `vn_msn_fx_gold` |
| 2. Rủi ro địa chính trị + xung đột | Yếu tố đẩy giá vàng (leo thang = vàng lên) | cross-ref S5/S6 (không gọi lại nếu vừa chạy) |
| 3. So lệch VN–TG → dự đoán vàng VN | Premium = (giá SJC mua vào − giá TG quy đổi) / giá TG; premium nở = vàng VN khó giảm theo TG | `vn_retail_gold` (SJC mua/bán) · giá TG wave 1 |
| 4. Lãi suất 2 đầu | SBV (tái cấp vốn/chiết khấu) vs US (DGS10/curve) — chênh lệch hút vốn | `sbv_rates` · `fred_series` (DGS10) · `yf_yield_curve` |
| 5. Dự đoán + macro | Odds Fed/căng thẳng + bối cảnh vĩ mô | `world_prediction_odds` (cross-ref S9/S21) · `macro_events_vn` |

**Verdict**: giá TG + TA 3 dòng · premium % + dự đoán vàng VN (theo TG / ngược TG khi
premium nở) · lãi suất 2 đầu + hàm ý tỷ giá · kịch bản odds · KHÔNG point-forecast giá.

**Chống tràn lan**: 1 call `yf_commodities` (đã gồm GC+DXY); TA vàng đọc từ series có sẵn,
không bắn thêm tools.

**Failure modes**: BTMC chết → `vnstock Retail` fallback (trong tool); premium âm (hiếm) →
ghi "bất thường", không diễn giải.

**Evidence live**: XAUUSD 4,195 · SJC 999.9 BTMC live · USDVND 25,970 · SBV 4.5%/3% · Fed giữ 74.5%.

**Acceptance**: "vàng SJC đắt hơn TG bao nhiêu" → premium % + dự đoán hướng + 2 driver, ≤10 calls.

## S17. `nhip-dap-crypto` (rev.3 — đơn giản hóa cho người ít chuyên crypto)

```yaml
name: nhip-dap-crypto
description: >
  Dùng khi hỏi giá/độ nóng thị trường crypto (BTC, ETH...). Asset allocation → skill
  rotation (đã xóa S11 — dùng S4/S16 bối cảnh). Viết bằng ngôn ngữ thường, mỗi thuật
  ngữ giải thích 1 dòng.
tool_budget: 6
```

| Wave | Tools | Đọc thế nào (diễn giải sẵn) |
|---|---|---|
| 1 | `crypto_spot` (BTC ETH SOL) | Giá + % 24h = "tăng/giảm bao nhiêu hôm nay" |
| 2 | `crypto_derivs` | funding rate = "phe mua đang trả tiền cho phe bán (dương = đám đông cược lên)"; OI = "tổng tiền đang cược"; long/short = "bên nào đông hơn" |
| 3 | `world_fear_greed` · `vn_crypto_ohlv` | Tham lam/Sợ hãi (0–100) + giá quy VND cho người VN |

**Verdict (3 câu hỏi)**: 1. Xu hướng gì (lên/xuống/đi ngang + %) · 2. Đòn bẩy có nóng không
(funding cao + OI cao = dễ đảo chiều) · 3. Liên thông gì tới VN (giá VND + chứng khoán còn
lại — không thì ghi "độc lập").

**Cảnh báo bắt buộc trong skill**: Binance có thể geo-block từ worker Singapore (funding
rỗng = ghi chú, không phải thị trường chết); crypto chạy 24/7 — số "hôm nay" khác phiên
chứng khoán VN, đừng so lệch phiên.

**Chống tràn lan**: tối đa 3 đồng/wave 1; không drill polymarket crypto trừ khi user hỏi xác suất.

**Evidence live**: BTC 83,476 (+0.33%) · funding 2.8e-05 (trung tính) · OI 95.7k · fear/greed 70–74.

**Acceptance**: "BTC sao rồi" → 3 câu trả lời + 0 jargon không giải thích, ≤6 calls.

## S19. `tim-kiem-tin-tuc` (rev.3 — săn rumor + đánh giá độ tin)

```yaml
name: tim-kiem-tin-tuc
description: >
  Dùng khi TÌM tin theo từ khóa/mã/phạm vi, KỂ CẢ tin đồn ("nghe đồn FPT ... có thật
  không", "tin VN hôm nay", "tin thế giới về dầu"). Digest tin nóng mặc định → S7/S8.
tool_budget: 10 / 4 song song
inputs: mode (symbol|vn|global), query
```

| Chế độ | Wave | Tools |
|---|---|---|
| **A. Theo mã (+ rumor)** | 1 | `news_symbol`(symbol, limit=20) — Fireant-first |
| | 2. Săn web + comments | `web_search`("tên mã" + "đồn"/"tin đồn"/rumor) → `web_fetch` 1–2 URL đáng ngờ nhất · đọc comments/posts liên quan trong `news_symbol` (rumor có TRƯỚC tin chính thống) |
| | 3. Đối chiếu | `corporate_calendar`(symbol) + `company_events`(symbol) — tin có khớp công bố không? |
| | 4. Dư luận | `sentiment_score`(symbol) |
| **B. VN** | 1 | `news_market`(limit=15) + `corporate_calendar`(limit=20) |
| | 2 | `news_symbol` × 2–3 mã nổi bật + `web_search` tin nóng nhất (xác minh chéo) |
| **C. Toàn cầu** | 1 | `news_market`(sources=gdelt) |
| | 2 | `geo_intel`(topic) / `event_stats`(query) + `web_search`(từ khóa EN) |

**Verdict mỗi tin (4 cột bắt buộc)**: tiêu đề · **tuổi tin** (mấy giờ/ngày trước — tin cũ
>3 ngày với mã bluechip coi như đã phản ánh giá) · **độ tin cậy** (chính thống / CTCK /
Fireant-crowd / ẩn danh-nguồn mở) · **triển vọng** (tác động tới DN: doanh thu/lợi nhuận/
giá — hay chỉ là noise). Tin đồn → nhãn "CHƯA XÁC NHẬN" + điều kiện xác nhận (chờ công bố
nào, ngày nào).

**Phân tích chi tiết tin quan trọng nhất**: ai nói → nói gì → bằng chứng kèm theo →
tác động định lượng được không (vd cổ tức bao nhiêu đồng, thương vụ bao nhiêu tỷ) →
kịch bản nếu đúng/sai.

**Chống tràn lan**: mode A dừng khi đã ≥5 tin đạt chuẩn; `web_search` tối đa 2 query/mode;
không fetch quá 2 URL.

**Failure modes**: web_search ẩn (thiếu key) → chỉ dùng Fireant+GDELT + ghi chú "chưa quét
web"; Fireant posts id/user null là đặc trưng payload.

**Evidence live**: VCB lãi suất 0.1–6% posts · GDELT "dầu" live 02-10 · corporate VCB 487 docs.

**Acceptance**: "nghe đồn HPG ... thật không" → verdict 4 cột + phân tích chi tiết + nhãn xác nhận.

## S20. `bat-on-quoc-gia`

```yaml
name: bat-on-quoc-gia
description: >
  Dùng khi hỏi bất ổn/ổn định của MỘT QUỐC GIA cụ thể ("Thái Lan đang bất ổn gì",
  "đo độ ổn định Trung Quốc", "biểu tình Bangladesh"). Nhiều quốc gia so sánh →
  chạy lặp skill mỗi nước. Bầu cử/chính sách toàn cầu → S5; chiến sự → S6.
tool_budget: 6 / 2 song song
inputs: country (tên VN hoặc EN)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `geo_intel`(topic=tên nước EN) · `event_stats`(query=tên nước EN) | 2 call song song, cùng upstream GDELT — ≤2 |
| 2 | `news_market`(sources=gdelt, giới hạn đọc theo tên nước) | chỉ khi wave 1 mỏng |
| 3 (tùy chọn impact) | `yf_commodities` hoặc `assets_rotation` 1 call | khi user hỏi "ảnh hưởng thị trường" |

**Verdict**: chỉ báo bất ổn 4 mức (ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG) dựa:
tần suất event GDELT (so với baseline chính query đó — run này là baseline, run sau so sánh) ·
mức độ (protest/conflict/coup keywords trong titles) · coverage nước láng giềng ·
transmission sang giá (dầu/vàng/rotation nếu leg 3 chạy). Mỗi mục 1 dòng evidence + URL.

**Chống tràn lan**: 1 nước/run; query EN 1 lần + 1 biến thể (tên thủ đô chỉ khi GDELT
yêu cầu); tối đa 1 lần đổi từ khóa (đặc trưng live: từ khóa VN mỏng → English); KHÔNG quét
nhiều nước trong 1 run (budget sẽ nổ) — user hỏi "ASEAN" → đề nghị tách từng nước.

**Failure modes**: GDELT rate-limit → 1 retry sau backoff (server đã cache 600s, gọi lại
ngay vẫn chạy); coverage mỏng là KẾT QUẢ (nước ít tin = ổn định truyền thông, ghi chú
"low-coverage ≠ stable").

**Evidence live**: geo_intel("Vietnam") + event_stats("vietnam") trả articles counts OK
ngày 02-10; pipeline EN-query đã thông trong full-135 run.

**Acceptance**: "bất ổn Thái Lan" → 4 mức verdict + ≥3 evidence lines có URL, ≤6 calls.


## S21. `du-doan-polymarket` (rev.3 — tìm sự kiện + hiển thị)

```yaml
name: du-doan-polymarket
description: >
  Dùng khi hỏi/xuất XÁC SUẤT từ Polymarket ("market nào đang nóng", "odds bầu cử",
  "Bitcoin bao giờ chạm 100k"). Fed chuyên biệt → S9.
tool_budget: 6
inputs: query hoặc tag
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Tìm sự kiện | `world_prediction_odds`(query/tag, limit=10) | đã sort vol24h — hiển thị tối đa 10 |
| 2. Hiển thị chi tiết | `polymarket_event`(slug — tối đa 2 event user chọn) | outcomes + prob + volume + end-date đầy đủ |

**Verdict (bảng hiển thị)**: {sự kiện · outcome · prob % · volume24h · liquidity · end-date}
+ 2 cờ: liquidity <50k = "odds kém tin" · end-date đã qua = loại. Kết luận 1 câu.

**Chống tràn lan**: hiển thị 10, drill 2 — không mở thêm; query rỗng → đổi tag 1 lần rồi kết luận.

**Failure modes**: Gamma chết cả proxy+direct → "không có odds", không bịa xác suất.

**Evidence live**: Fed T10 no-change 74.5% (vol 2.6M) · Brazil detail OK.

**Acceptance**: "polymarket nóng gì về kinh tế" → bảng ≤10 dòng + drill 1 event, ≤6 calls.

## S22. `ky-thuat-chuyen-sau` (rev.3 — đa khung + Ichimoku/Elliott/Wyckoff)

```yaml
name: ky-thuat-chuyen-sau
description: >
  Dùng khi hỏi THUẦN kỹ thuật một mã đa khung thời gian: RSI/MACD/BB/Ichimoku,
  Elliott/Wyckoff, hỗ trợ-kháng cự, higher-high vs lower-low ("VCB kỹ thuật đa khung",
  "FPT có breakout không", "HPG đang higher-high hay lower-low"). Săn toàn thị trường → skill đã xóa (dùng signals_scan trực tiếp khi cần).
tool_budget: 8 / 3 song song
inputs: symbol, timeframes (default 1D+1W, thêm 1M khi hỏi dài hạn)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1. Nến đa khung | `vn_quote_history`(symbol, 1D) · `vn_quote_history`(symbol, 1W) · [`vn_quote_history`(1M) nếu hỏi dài hạn] | interval 1D/1W/1M đã có từ P15 |
| 2. Chỉ báo mỗi khung | `signals_technical`(symbol, interval tương ứng) | RSI/MACD/BB/Stoch/ADX/patterns/S-R/RS/pos_52w — **Phase B**: thêm **Ichimoku** (Tenkan/Kijun/Senkou/Chikou) vào provider + expose ở đây |
| 3. Cấu trúc sóng | đọc swing từ nến wave 1 (local): đỉnh/đáy → nhãn **HH/HL/LH/LL** + Fibonacci retracement | **Phase B**: code swing-structure (~100 dòng); **Phase 2**: nhãn sóng Elliott/Wyckoff heuristic (khó — làm sau) |
| 4. Xác nhận | `pattern_match`(analogy lịch sử) · `dnse_latest_trade`/`dnse_orderbook`/`vn_trades` (intraday) · `vn_index_ohlcv` (trend index) | ≤3, theo câu hỏi |

**Verdict mỗi khung (1D/1W[/1M])**: trend (SMA stack + ADX) · momentum (RSI/MACD/BB +
Ichimoku sau Phase B) · S-R của khung · cấu trúc (HH/HL/LH/LL + Fibo — sau Phase B;
trước đó: S-R + pattern hiện có) · **kết luận higher-high hay lower-low**. Tổng hợp:
đồng thuận đa khung hay phân kỳ + trigger giá.

**Chống tràn lan (hiện tại)**: Elliott/Wyckoff/Ichimoku CHƯA có trong tools → skill PHẢI
ghi "chưa phân tích được, chờ Phase B", không diễn giải sóng bằng lời văn suông; 1W/1M qua
`vn_quote_history` (không qua `signals_technical` cho tới khi provider mở interval — docstring
hiện ghi "daily only").

**Failure modes**: mã <60 nến → indicators null; DNSE hết giờ → orderbook rỗng là đúng.

**Evidence live**: VCB RSI 39.2/ADX 12.1/MACD −0.31 · HPG dưới sma50/150/200, RS −7.32,
pos_52w 0.008, support 19.9 · pattern best_corr 0.409 (yếu — ghi đúng).

**Acceptance**: "FPT kỹ thuật 1D+1W" → verdict 2 khung + HH/LL (sau Phase B; trước đó: S-R +
patterns), ≤8 calls.

## S23. `co-ban-chuyen-sau`

```yaml
name: co-ban-chuyen-sau
description: >
  Dùng khi hỏi THUẦN cơ bản một mã: BCTC từng dòng, chỉ số tài chính, chất lượng lợi nhuận,
  kế hoạch kinh doanh, sở hữu, giao dịch nội bộ, cổ tức ("đọc BCTC FPT", "VCB có dấu hiệu
  thao túng không", "cổ đông lớn HPG"). Kỹ thuật/định giá → S22/S24.
tool_budget: 9 / 4 song song
inputs: symbol, optional aspect (baokao|chataluong|sohuu|kehoach)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 | `vs_auth_status` | JWT sống = được dùng `financial_detail`; chết → nhánh mirror |
| 1 | `financial_detail`(statement=KQCD, periods_n=4) · `stock_forensic`(symbol) | song song 2 |
| 2 (chọn) | `financial_statements` · `financial_ratios` · `vn_fundamentals` | trend + ratios; 3 call max |
| 3 (chọn) | `planned_targets` · `holders` · `insider_trading` · `dividends_splits` | sở hữu/kế hoạch/chia cổ tức |
| 4 (tham chiếu) | `vs_financial_norms`/`vs_financial_terms`/`vs_company_info` | CHỈ khi cần giải thích norm_id/kỳ |

**Verdict**: chất lượng tăng trưởng (DT/LN 4 quý, biên) · bảng ratios chủ chốt · M-Score +
F-score + flags (red flag list) · so với kế hoạch (planned_targets: vượt/hụt %) · cấu trúc
sở hữu + thay đổi insider · chính sách cổ tức. Kết luận 1 câu: CƠ BẢN TỐT/TRUNG BÌNH/YẾU
+ 3 rủi ro lớn nhất.

**Chống tràn lan (HOME 14 TOOLS NHƯNG RUN TYPICAL 4–7)**: aspect nào mới chạy leg đó —
"chataluong" chỉ wave 1; "sohuu" chỉ wave 3 phải; `vs_financeinfo` chỉ là fallback JWT-chết;
`vs_documents` KHÔNG thuộc skill này (→ S27). LCTT/CDKT chỉ gọi khi user hỏi dòng tiền/bảng
cân đối (statement param).

**Failure modes**: bank m_partial (SGAI null do LCTT rỗng — VCB live) → "M không kết luận";
`financial_detail` periods vượt quyền gói → rows rỗng + warning package → degrade
`vs_financeinfo` 1 lần; vn_company chậm 30s khi throttle → đặt cuối wave, thiếu được.

**Evidence live**: FPT detail 25 norms × 138 số · M **−2.06**, F 2/6 · KH DT 61,850/75,400/
58,580 · VCB holders SBV 74.8% · VCB cổ tức 450đ · insider empty là đúng data.

**Acceptance**: "BCTC FPT có gì lạ" → wave 1 (2 calls) đủ ra M/F + 4 quý; "toàn cảnh cơ bản
VPL" → ≤9 calls, không leg nào gọi 2 lần.

> Review rev.3: ỔN — aspect-gating giữ run điển hình 4–7/14 tools, giữ nguyên.


## S24. `dinh-gia-chuyen-sau`

```yaml
name: dinh-gia-chuyen-sau
description: >
  Dùng khi hỏi ĐỊNH GIÁ một mã: vùng giá hợp lý, PER/PB/DCF, rẻ/đắt so với lịch sử và
  mặt bằng lãi suất ("FPT đắt chưa", "VCB fair value"). So sánh nhiều mã → S25;
  cơ bản thuần → S23.
tool_budget: 7 / 3 song song
inputs: symbol, optional method (per|pb|dcf|auto)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `valuation_run`(symbol, method) · `vs_overview_trading`(symbol) | ensemble + PE/PB/EPS snapshot |
| 2 | `financial_ratios`(symbol) · `vn_quote_history`(symbol, days=365) | biên nhiều năm + vùng giá 52w |
| 3 (bối cảnh) | `yf_yield_curve` · `vs_trading_info`(symbol) | lãi suất chiết khấu + trần sàn tham chiếu |

**Verdict**: giá hiện tại vs vùng fair (method nào dẫn, khoảng bao nhiêu %) · PER/PB hiện vs
trung bình 2–3 năm (tự tính từ wave 2) · rẻ/đắt hợp lý vì sao (tăng trưởng, chất lượng S23
cross-ref, mặt bằng lãi suất leg 3) · **UPSIDE/DOWNSIDE %** + độ tin (cao nếu 2 method đồng
thuận).

**Chống tràn lan**: DCF-lite trong `valuation_run` đã tính sẵn — skill KHÔNG tự dựng lại DCF;
1 `method` per run (auto trừ khi user khăng khăng per/pb); bond context chỉ khi PB-heavy.

**Failure modes**: `method` sai enum → warning, về auto; EPS âm (công ty lỗ) → per_pb vô
nghĩa, nói thẳng "không đủ cơ sở định giá"; bank (đặc thù PB) → ưu tiên per_pb.

**Evidence live**: VCB per_pb @57,400 (live 2 method đồng thuận) · FPT per_pb @62,700 ·
US10Y 5.24% context · overview_trading VCB PE/PB/ROEA đủ.

**Acceptance**: "FPT đắt chưa" → UPSIDE % + so lịch sử 2 dòng, ≤7 calls.

> Review rev.3: ỔN — mỏng nhưng đúng bản chất định giá; bổ sung duy nhất: verdict thêm dòng
> "upside theo target CTCK" (cross-ref S27) để neo kỳ vọng.


## S25. `so-sanh-cung-nganh` (rev.3 — điều phối: xác định mã cùng ngành → gọi skills trên)

```yaml
name: so-sanh-cung-nganh
description: >
  Dùng khi so sánh 2–6 mã CÙNG NGÀNH hoặc chọn leader ("VCB vs BID vs CTG",
  "thép ai mạnh nhất"). Skill ĐIỀU PHỐI: xác định mã cùng ngành rồi gọi S22/S23/S24
  cho từng mã, gộp xếp hạng. 1 mã → S1.
tool_budget: 6 (của S25) + budget các sub-skill (mỗi mã ≤1 sub-skill/lượt)
inputs: symbols (2–6) hoặc sector/industry name
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 0. Xác định mã cùng ngành | `vn_reference`(exchange/industry) hoặc `vs_industry_tree` (tra GICS) → chọn ≤6 mã · `stock_screener` (filter ngành, pool hẹp) khi user chỉ cho tên ngành | cap tuyệt đối 6 mã — trên 6 thì yêu cầu thu hẹp |
| 1. Bảng nhanh | `compare_equities`(≤4) + `peer_compare` (chia 4+2 khi 5–6 mã) · `vn_equity_quote_batch` (1 shot giá) | overview + momentum |
| 2. Gọi skills trên | Mỗi mã: S22 (kỹ thuật) HOẶC S23 (cơ bản) HOẶC S24 (định giá) — theo câu hỏi, song song ≤4 | đây là lý do điều phối |
| 3. Bối cảnh ngành | `vs_gics_index`(group) — index ngành làm nền | 1 call |

**Verdict**: bảng xếp hạng {mã · PE · ROE · momentum · RS · giá} + **1 dòng luận chọn**
+ cảnh báo tương quan nhóm (cross-ref `correlation_matrix` khi chia tiền cả nhóm).

**Chống tràn lan**: không chạy cả 3 sub-skills cho cả 6 mã (6×3=18 calls) — mỗi mã 1 sub-skill
theo trọng tâm câu hỏi; thiếu 1 tiêu chí → xếp hạng partial + ghi "n/6 mã đủ dữ liệu".

**Failure modes**: enrich throttle → ratios rỗng → xếp hạng kỹ thuật-only + ghi chú.

**Evidence live**: compare VCB-HPG 2.8s · peer cap 6 · HOSE 757 mã universe · quote_batch 1 request.

**Acceptance**: "so sánh bank" → peer list ≤6 + sub-skill calls có giới hạn + bảng xếp hạng.

## S26. `phan-tich-sentiment`

```yaml
name: phan-tich-sentiment
description: >
  Dùng khi hỏi DƯ LUẬN/COMMENT của cộng đồng về một mã trên Fireant ("phố nói gì về FPT",
  "sentiment VCB", "crowd có đang FOMO HPG không"). Tin tức chính thống → S19;
  sentiment thị trường chung (fear/greed) → S4/S17.
tool_budget: 6 / 2 song song
inputs: symbol
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `news_symbol`(symbol, limit=20) · `sentiment_score`(symbol, limit=20) | song song — 2 call cùng nguồn Fireant, server cache dùng chung |
| 2 (chọn khi mâu) | `company_events`(symbol) | đối chiếu cmt với công bố chính thức |

**Verdict**: điểm sentiment (Groq hoặc heuristic — **bắt buộc ghi nhãn nguồn**, heuristic
thang khác) + 3–5 trích comment tiêu biểu (positive/negative/repeat-thuyết) + nhận diện
FOMO/hoảng loạn (tần suất symbol tag +_likes) + **cảnh báo vòng lặp**: crowd có thể sai
(heuristic −0.25 live trên FPT dù forensic sạch) → sentiment KHÔNG được là leg duy nhất
của quyết định.

**Chống tràn lan**: 1 symbol/run; limit 20 đủ 90% mẫu — không call lại limit lớn hơn;
`company_events` chỉ khi comment contradicts disclosures; không dùng sentiment để
"chốt luận" — chỉ dùng làm confirm/deny.

**Failure modes**: thiếu Groq → `score_heuristic` + warning "groq unavailable" (live) →
hiện nhãn "heuristic" trong verdict; posts rỗng = mã ít bàn (empty hợp lệ); Fireant chết →
`unavailable`, fallback duy nhất: GDELT titles qua S19 mode C (1 call).

**Evidence live**: FPT — 20 posts, heuristic **−0.25**, trong khi M −2.06 sạch (điển hình
crowd≠fundamentals); VCB posts lãi suất 0.1–6%; Groq key có trên prod, thiếu trên local dev.

**Acceptance**: "phố nói gì về FPT" → điểm + ≥3 quotes + nguồn-heuristic label, ≤4 calls.

> Ghi chú rev.3 — dữ liệu CÓ ý nghĩa nếu đọc đúng: sentiment đo *đám đông*, không đo
> *doanh nghiệp* (live: FPT heuristic −0.25 trong khi M −2.06 sạch). Ngưỡng diễn giải
> heuristic: <−0.3 hoảng loạn · >+0.3 FOMO · giữa = trung tính; KHÔNG chuẩn hóa chéo 2 mode
> Groq/heuristic; không bao giờ dùng sentiment làm leg duy nhất của quyết định.


## S27. `tim-co-hoi-bao-cao-ctck`

```yaml
name: tim-co-hoi-bao-cao-ctck
description: >
  Dùng khi săn/cơ hội theo BÁO CÁO PHÂN TÍCH của CTCK trên Vietstock ("CTCK gần đây
  khuyên mua gì", "có target mới cho MSN không", "báo cáo VPS/SSI nói gì về HPG").
  Tin đồn/crowd → S26/S19; tự định giá → S24.
tool_budget: 8 / 3 song song
inputs: symbol (optional — bỏ trống = quét feed chung), days (default 7)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `analyst_consensus`(limit=30) | **feed chung không symbol** — parse rating (MUA/KHẢ QUAN/THEO DÕI/GIẢM TỶ TRỌNG) + giá mục tiêu từ titles, sort ngày |
| 2 (mã cụ thể) | `analyst_consensus`(symbol, limit=15) · `vs_documents`(symbol) | report cho mã + tài liệu gốc |
| 3 (xác nhận) | `stock_overview`(mã target) 1–2 call | so giá hiện tại vs mục tiêu → upside % |

**Verdict**: bảng {mã · CTCK · rating · giá mục tiêu · ngày · upside % so giá hiện tại} lọc
trong `days`; top 3 cơ hội (upside lớn + rating MUA + còn hiệu lực); **cột "đã kiểm
chứng"** = leg 3 chạy cho 1–2 mã nổi bật nhất, không kiểm chứng tất cả. Disclaimer:
khuyến nghị CTCK là input, không phải chân lý — skill không tự suy diễn thành "nên mua".

**Chống tràn lan**: feed chung 1 call (symbol-less feed CÓ dữ liệu — evidence dưới);
khi user hỏi "HPG" mà `analyst_consensus(symbol=HPG)` empty → **đọc feed chung và lọc
client-side lấy title chứa HPG** (đặc trưng title-scrape: filter mã có thể sót), không
retry đổi limit. `vs_documents` chỉ lấy 1 mã đáng giá nhất.

**Failure modes**: `source/date null` trong reports (đặc trưng parse titles — live) → suy
ngày từ URL/title, ghi chú nguồn ngày "không chắc chắn"; feed rỗng thật (cuối tuần không
báo cáo mới) → empty hợp lệ, nới days 1 lần.

**Evidence live (02-10)**: feed chung **7 reports** — MBB MUA 28,200 · **MSN MUA 89,200
(30/09)** · VPB KHẢ QUAN 30,500 · MSB GIẢM TỶ TRỌNG 13,200 · FRT THEO DÕI 157,000;
filter symbol=VCB/FPT từng empty đúng hiện tượng trên.

**Acceptance**: "CTCK khuyên mua gì tuần này" → bảng ≥5 dòng có upside %, kiểm chứng 2 mã
top, ≤8 calls.

---


## S28. `kiem-tra-nguon-du-lieu` (MỚI — check toàn bộ nguồn trong 1 lượt)

```yaml
name: kiem-tra-nguon-du-lieu
description: >
  Dùng khi cần ĐÁNH GIÁ các nguồn dữ liệu có hoạt động ổn không ("server còn sống
  không", "Vietstock chết chưa", "sáng nay data có đủ không"). Chạy định kỳ mỗi phiên
  hoặc khi skills khác báo unavailable hàng loạt. Không dùng để phân tích thị trường.
tool_budget: 12 / 5 song song
```

| Wave | Tools | Nguồn kiểm tra |
|---|---|---|
| 0 | `doctor` | env keys + versions local |
| 1 (song song 5) | `source_status` · `vs_auth_status` | tổng quan upstream + hạn JWT |
| 2 (smoke mỗi upstream, song song 5) | `vn_quote_history`(VCB, days=5) · `vs_market_index` · `dnse_latest_trade`(VN30F1M) · `yf_market_pins` · `crypto_spot`(BTCUSDT) | vnstock · Vietstock · DNSE · yfinance · Binance |
| 3 (smoke tiếp, song song 4) | `news_market`(limit=1) · `fred_series`(DGS10, limit=1) · `world_prediction_odds`(limit=1) · `sbv_rates` | Fireant/GDELT · FRED · Gamma · SBV scrape |

**Verdict (bảng bắt buộc)**:

| Nguồn | Trạng thái | Độ trễ | Skills ảnh hưởng nếu chết |
|---|---|---|---|
| vnstock | ok/throttle/down | giây | S22/S23/S25/S15... |
| Vietstock JWT | còn hạn tới.../HẾT | — | S23/S27/S3... (chuyển mirror/HAR) |
| Vietstock HAR-session | sống/chết | — | S3 macro/S13-CTKH... |
| DNSE | ok/lạnh | — | S22-intraday... (WS trio cần worker) |
| yfinance/Binance/GDELT/Fireant/Gamma/FRED/SBV | ... | ... | ... |

+ 1 dòng khuyến nghị ("sáng nay đủ data chạy S1/S13/S22" hay "chỉ chạy legs không-Vietstock").

**Chống tràn lan**: smoke dùng limit/days NHỎ NHẤT có thể (limit=1, days=5) — mục đích là
ping, không phải lấy dữ liệu; không retry quá 1 lần/upstream.

**Failure modes**: chính skill này cũng có thể partial (1–2 nguồn chết) — verdict vẫn ra đủ
bảng, đánh dấu đỏ nguồn chết.

**Evidence live**: sự cố JWT 02-10 (hết hạn 19:15, Google-SSO chặn password fallback) —
skill này sẽ bắt được ở wave 1 (`vs_auth_status` false) trước khi skills khác fail hàng loạt;
HAR-session sống độc lập (macro vẫn available khi JWT chết).

**Acceptance**: chạy 1 lượt → bảng đủ 9 nguồn + khuyến nghị, ≤12 calls, ≤3 phút.

## Phụ lục dùng chung — watchlist/alert (không phải skill, rev.3)

S18 đã xóa theo yêu cầu. 12 tools watchlist/alert (`watchlist_create/list/get/add/
update/remove/delete`, `alert_create/list/pause/resume/delete`) + `alert_check` KHÔNG
thuộc skill nào — mọi skill được phép gọi trực tiếp khi cần LƯU kết quả, với 3 luật:
(1) luôn `watchlist_list`/`alert_list` trước khi tạo (tránh trùng); (2) 1 watchlist cho
1 chủ đề; (3) không xóa khi user chưa xin. Vòng đời đầy đủ xem git history rev.2
(commit trước) của file này.

# PHẦN 2 — MA TRẬN BAO PHỦ 135 TOOLS (rev.3)

Mỗi tool có đúng **1 HOME**. S5/S9 là skill tổ chức (0 home, chỉ cross-ref).
Tools của skills đã xóa (S2/S10/S11/S12/S14/S18) hoặc đã chuyển home, hoặc park ở
bảng CHỜ DUYỆT để bạn tự điều chỉnh (đúng yêu cầu rev.3).

| Skill (home) | Số tool | Tools home |
|---|---|---|
| S1 điều phối | 4 | `stock_overview`• `symbol_lookup`• `event_calendar_vn`• `evidence_bundle`• |
| S3 macro VN | 9 | `vs_categories`• `vs_indicator_data`• `vs_xnk_detail`• `sbv_rates`• `macro_events_vn`• `economic_calendar`• `snapshot_history`• `vs_currency`• `vn_retail_fx`• |
| S4 macro global | 9 | `fred_series`• `world_macro_country`• `yf_yield_curve`• `yf_regime_assets`• `yf_world_indices`• `yf_global_indices`• `assets_rotation`• `world_fear_greed`• `vn_global_index`• |
| S5 chính trị (0 home — cross-ref) | 0 | — (pure cross-ref) |
| S6 xung đột | 1 | `event_stats`• |
| S7 tin nóng VN | 3 | `news_market`• `corporate_calendar`• `brief_build`• |
| S8 tin nóng global | 1 | `yf_mega_flows`• |
| S9 fed (0 home — cross-ref) | 0 | — (pure cross-ref) |
| S13 trước BCTC | 3 | `company_events`• `quant_risk`• `scenario_simulate`• |
| S15 backtest | 12 | `quant_backtest`• `quant_factors`• `backtest_strategies`• `param_sweep`• `seasonality`• `correlation_matrix`• `portfolio_optimize`• `dnse_ohlc_history`• `vn_equity_ohlcv`• `vn_futures_ohlcv`• `vn_index_ohlcv`• `dnse_vn30f1m_live`• |
| S16 vàng tỷ giá | 4 | `vn_retail_gold`• `vn_forex_ohlcv`• `vn_msn_fx_gold`• `yf_commodities`• |
| S17 crypto | 3 | `crypto_spot`• `crypto_derivs`• `vn_crypto_ohlv`• |
| S19 tìm tin | 1 | `web_fetch`• |
| S20 bất ổn quốc gia | 1 | `geo_intel`• |
| S21 polymarket | 2 | `world_prediction_odds`• `polymarket_event`• |
| S22 kỹ thuật sâu | 7 | `signals_technical`• `pattern_match`• `dnse_orderbook`• `vn_trades`• `dnse_latest_trade`• `vn_quote_history`• `signals_scan`• |
| S23 cơ bản sâu | 14 | `financial_detail`• `financial_statements`• `financial_ratios`• `planned_targets`• `vs_financeinfo`• `vs_financial_terms`• `vs_financial_norms`• `vs_company_info`• `vn_fundamentals`• `vn_company`• `holders`• `insider_trading`• `dividends_splits`• `stock_forensic`• |
| S24 định giá sâu | 3 | `valuation_run`• `vs_overview_trading`• `vs_trading_info`• |
| S25 so sánh ngành | 7 | `compare_equities`• `peer_compare`• `vn_reference`• `vs_industry_tree`• `stock_screener`• `signals_screener_columns`• `vn_equity_quote_batch`• |
| S26 sentiment | 2 | `sentiment_score`• `news_symbol`• |
| S27 cơ hội CTCK | 2 | `analyst_consensus`• `vs_documents`• |
| S28 kiểm tra nguồn | 1 | `doctor`• |
| Contract chung (pre-flight/ops) | 5 | `source_status`• `vs_auth_status`• `oracle_meta`• `runs_list`• `run_get`• |
| Phụ lục dùng chung (không phải skill) | 12 | `watchlist_create`• `watchlist_list`• `watchlist_get`• `watchlist_add`• `watchlist_update`• `watchlist_remove`• `watchlist_delete`• `alert_create`• `alert_list`• `alert_pause`• `alert_resume`• `alert_delete`• |

**Tổng gán home: 106** + **chờ duyệt: 29** = 135/135, không trùng, không mồ côi.**

## Bảng CHỜ DUYỆT (tools của S2/S10/S11/S12/S14/S18 cũ — bạn tự điều chỉnh sau)

| Tool | Nguồn cũ | Gợi ý gán khi bạn duyệt |
|---|---|---|
| `market_overview` | ex-skill đã xóa | S7/S13 |
| `market_snapshot` | ex-skill đã xóa | S7 |
| `market_movers` | ex-skill đã xóa | S7 |
| `breadth_scan` | ex-skill đã xóa | S7 |
| `market_candles_batch` | ex-skill đã xóa | S22 |
| `vs_market_info` | ex-skill đã xóa | S7 |
| `vs_market_price` | ex-skill đã xóa | S7 |
| `vs_market_index` | ex-skill đã xóa | S7 |
| `exchange_calendar` | ex-skill đã xóa | S28 |
| `dnse_market_status` | ex-skill đã xóa | S28 |
| `dnse_working_dates` | ex-skill đã xóa | S28 |
| `vs_selftrading` | ex-skill đã xóa | S13 |
| `vs_nn_flow` | ex-skill đã xóa | S13 |
| `money_flow` | ex-skill đã xóa | S13 |
| `futures_basis` | ex-skill đã xóa | S13 |
| `block_trades` | ex-skill đã xóa | S13 |
| `dnse_foreign_flow` | ex-skill đã xóa | S28 (cần worker) |
| `dnse_ws_snapshot` | ex-skill đã xóa | S28 |
| `dnse_indices` | ex-skill đã xóa | S28 |
| `sector_performance` | ex-skill đã xóa | S25 |
| `vs_industry_heatmap` | ex-skill đã xóa | S25 |
| `vs_gics_index` | ex-skill đã xóa | S25 |
| `ipo_calendar_vn` | ex-skill đã xóa | S25 |
| `vn_listing` | ex-skill đã xóa | S25 |
| `alert_check` | ex-skill đã xóa | phụ lục dùng chung |
| `yf_oracle_markets` | ex-skill đã xóa | S4 |
| `yf_alloc_history` | ex-skill đã xóa | S4 |
| `yf_market_pins` | ex-skill đã xóa | S4 |
| `compare_assets` | ex-skill đã xóa | S4 |

Cross-ref đáng nhớ: `news_market`•(S7) — S5/S6/S8/S19/S20 · `geo_intel`•(S20) —
S5/S6/S8/S19 · `event_stats`•(S6) — S5/S19/S20 ·
`world_prediction_odds`/`polymarket_event`•(S21) — S5/S9/S16/S17 ·
`yf_commodities`•(S16) — S4/S6/S13/S17 · `stock_forensic`/`financial_*`•(S23) —
S13 reuse · `valuation_run`•(S24) — S1/S13 · `sentiment_score`•(S26) — S7/S13 ·
`analyst_consensus`•(S27) — S3/S13 · `signals_technical`•(S22) — S1/S25 ·
`vn_quote_history`•(S22) — S13/S15/S24 · `pattern_match`•(S22) — S15 ·
`evidence_bundle`•(S1) — mọi verdict cuối · `snapshot_history`•(S3) — cache khi
upstream chết · `quant_risk`/`scenario_simulate`•(S13) — cushion pre-BCTC.

Ghi chú 3 WS tools (home S2 cũ → park chờ duyệt): remote không worker →
`unavailable`; mọi skill đã thiết kế đi qua `money_flow` (tự fallback vs_nn_flow).

# PHẦN 3 — QUY TRÌNH HARNESS BUILD & ACCEPTANCE

1. **Kết nối trước**: config 0.1, chạy `mcp probe` + `tools/list` = 136 tools.
2. **Scaffold**: 22 thư mục `skills/<slug>/SKILL.md` theo template Phần 1 (frontmatter +
   bảng workflow + verdict + budget + failure + evidence + acceptance).
3. **Test nghiệm thu per skill**: bảng `Acceptance` tương ứng — chạy input mẫu, đối chiếu:
   đủ số mục verdict · trong budget · không có số bịa · xử lý đúng `empty/unavailable`.
4. **Test chống tràn lan (global)**: input mở ("phân tích FPT") → đếm `tools/call` trong
   trace ≤ budget skill đó; burst song song ≤5; 0 call ngoài home list.
5. **Definition of Done** = evidence runtime (trace + output), không phải "tin là đúng".

## Ghi chú vận hành harness

- Giá VN stock trong vài tool theo **kVND** (`signals_technical.last 57.3` = 57,300đ;
  `scenario_simulate.last_close 62.7`) — skill nào in giá phải tự qui đổi + ghi đơn vị.
- `financial_statements` warning `statement 'KQKD' not found, returning all pages` —
  filter statement không khớp sẽ trả all pages (đặc trưng v3-compat), skill đọc trang
  `statement` trong data, đừng abort vì warning.
- M-Score `null` + `m_partial: [...]` = thiếu chỉ số (bank LCTT rỗng) → verdict ghi
  "không kết luận thao túng", không được gán M=0.
- Giờ cao điểm vnstock throttle (~10:00–11:30, 14:00–15:00 VN) → S2/S12 degrade nhiều;
  đó là lý do S12 có pool-narrowing. Không retry chống throttle.
