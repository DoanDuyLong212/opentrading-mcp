# Skills Design cho Harness — opentrading-mcp (2026-10-02, rev.2)

**Mục đích**: spec hoàn chỉnh để team harness TỰ BUILD **27 skills** trên nền 135 MCP tools.
Không cần code thêm phía server — mọi workflow đã verify live 2026-10-02 (số liệu thật
trong từng skill là evidence thật, không minh họa).

**rev.2**: tách skills nhồi quá nhiều tools (S1 14 calls → điều phối 6 + 6 skill chuyên
S22–S27) và thêm 8 skills theo yêu cầu: bất ổn quốc gia (S20), dự đoán polymarket (S21),
kỹ thuật chuyên sâu (S22), cơ bản chuyên sâu (S23), định giá chuyên sâu (S24), so sánh
cùng ngành (S25), sentiment Fireant (S26), săn cơ hội báo cáo CTCK (S27).

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

# PHẦN 1 — 27 SKILLS

Mỗi skill: frontmatter → workflow bảng → verdict → chống tràn lan → failure modes →
evidence live → acceptance test.

## S1. `phan-tich-chuyen-sau-1-ma` (điều phối — đã tách nhỏ)

```yaml
name: phan-tich-chuyen-sau-1-ma
description: >
  Dùng khi người dùng yêu cầu phân tích TOÀN DIỆN một mã cụ thể ("phân tích FPT").
  Skill này ĐIỀU PHỐI các skill chuyên (S22 kỹ thuật, S23 cơ bản, S24 định giá,
  S25 so sánh, S26 sentiment, S27 báo cáo CTCK) rồi gộp verdict — KHÔNG tự gọi
  chồng chéo 14 tools như bản cũ.
tool_budget: 6 / 2 song song
inputs: symbol, optional focus (kythuat|dinhgia|baokao|dongtien|toan-dien)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 | `source_status` · `vs_auth_status` | pre-flight |
| 1 | `stock_overview` · `symbol_lookup`(nếu nghi tên) | snapshot nhanh |
| 2 | `event_calendar_vn`(symbol) | lịch sự kiện 30 ngày tới |
| 3 | **dispatch theo focus**: toan-dien → chạy S22→S23→S24 (tuần tự, mỗi skill tự lo budget của nó); focus đơn → chỉ chạy 1 skill tương ứng | đây là lý do skill tách nhỏ |
| 4 | `evidence_bundle` | khóa verdict từ các leg đã chạy |

**Verdict template**: gộp 6 mục từ sub-skill verdicts (kỹ thuật · cơ bản · định giá ·
dòng tiền/sự kiện · sentiment/cơ hội · bull-bear + đổi nhận định), mỗi mục 1–2 dòng + provenance.

**Chống tràn lan (nguyên tắc điều phối)**: skill này **cấm** gọi trực tiếp
`signals_technical`/`financial_detail`/`valuation_run`/`stock_forensic`... — ai cần chiều nào
thì kích sub-skill đó; nếu user chỉ hỏi 1 chiều ("RSI FPT bao nhiêu") → trả lời bằng sub-skill
tương ứng, không chạy S1. Budget 6 chỉ cho tools nhà; tool của sub-skill tính vào budget
sub-skill (tổng toàn phiên có thể >6 nhưng mỗi skill ≤8 — mục tiêu "không ép nhiều tools
trong MỘT skill").

**Failure modes**: sub-skill chết 1 chân → S1 vẫn ra verdict với leg còn + ghi leg thiếu.

**Evidence live**: bản điều phối = chính 8/8 calls của WF2 ngày 02-10 nhưng phân bổ vào
sub-skill; VCB RSI 39.2/F 4-6/57,400; FPT M −2.06/KH 58,580.

**Acceptance**: input "phân tích FPT" → verdict 6 mục; S1 chỉ dùng ≤6 calls của chính nó;
mỗi sub-skill chạy trong budget riêng; 0 tool trùng giữa S1 và sub-skill trong 1 run.

## S2. `danh-gia-tinh-hinh-thi-truong`

```yaml
name: danh-gia-tinh-hinh-thi-truong
description: >
  Dùng khi hỏi phiên/sức khỏe thị trường VN hôm nay ("thị trường sao rồi", "phiên sáng",
  "độ rộng thị trường"). Không dùng khi: hỏi 1 mã (→ S1), hỏi ngành (→ luan-chuyen-nganh).
tool_budget: 12 / 5 song song
```

| Wave | Tools |
|---|---|
| 0 | `source_status` |
| 1 | `brief_build` · `market_overview` · `breadth_scan` · `futures_basis` · `money_flow` |
| 2 | `market_movers` · `vs_market_info` · `market_snapshot`(VN30 default) |
| 3 (nếu hỏi sâu) | `dnse_orderbook`(mã lớn) · `vn_trades`(băng) · `signals_scan`(dòng đầu cơ) · `vs_selftrading`+`vs_nn_flow`(đào dòng tiền sau money_flow) |

**Verdict**: báo cáo phiên 6 mục: xu hướng index · độ rộng (adv/dec/trần/sàn) · phái sinh
(basis ± bps) · khối ngoại (mua/bán tỷ) · nhóm dẫn–dở · nhận định sức khỏe phiên (1 câu).
`market_overview` partial (session leg chết khi thiếu WS worker) → DÙNG 3 leg còn + ghi
"session từ nguồn khác"; `vs_market_info` bù breadth từng sàn. `brief_build` cho luôn tin
+ world pins trong 1 call (đã gồm fear/greed).

**Chống tràn lan**: `signals_scan` full HOSE ~40s — CHỈ bắn khi user hỏi "momentum/breakout",
cap `max_symbols=100`. Không gọi `dnse_foreign_flow` trực tiếp (sẽ unavailable ở remote
không worker) — `money_flow` đã tự fallback vs_nn_flow bên trong.

**Failure modes**: ngoài giờ → board rows cũ là đúng (as_of cho biết), không "làm mới"
vô ích; basis tool `unavailable` (cả DNSE chết) → bỏ mục phái sinh, nói rõ.

**Evidence live**: breadth 1 tăng/6 giảm (rổ bluechip), VCB −0.35%, HPG −0.50%,
**basis +6.95 (+37bps)**, NN bán ròng (mua 1,814 vs bán 2,268 tỷ).

**Acceptance**: "thị trường hôm nay" → 6 mục verdict với ≥4 mục có số; budget ≤10.

## S3. `danh-gia-vi-mo-viet-nam`

```yaml
name: danh-gia-vi-mo-viet-nam
description: >
  Dùng khi hỏi vĩ mô VN: GDP, CPI, xuất nhập khẩu, tỷ giá, lãi suất điều hành, lịch
  công bố số liệu. Không dùng khi: vĩ mô Mỹ/toàn cầu (→ S4), chính sách VN chung
  (→ S19 chế độ B).
tool_budget: 12 / 4 song song
```

| Wave | Tools |
|---|---|
| 0 | `source_status`, `vs_auth_status` |
| 1 (catalog) | `vs_categories` (tra category_id nếu chưa chắc) |
| 2 (series) | `vs_indicator_data`(GDP: 73,tt3) · `vs_indicator_data`(CPI: 15,tt7,sub2) · `vs_indicator_data`(XK: 38,tt2) · `vs_xnk_detail`(xk) |
| 3 (rate/_fx/calendar) | `sbv_rates` · `macro_events_vn` · `vn_msn_fx_gold` · `vn_retail_fx` · `economic_calendar` |
| 4 (lịch sử) | `snapshot_history`(macro_curated) khi live fail |

**Verdict**: tăng trưởng (q/dư + trend) · lạm phát (yoy) · thương mại (cán cân, đối tác
lớn) · tỷ giá (USDVND + spread SBV) · lãi suất điều hành · kỳ công bố sắp tới (ngày).
GDP/CPI/XK mỗi chuỗi: lấy ≥8 điểm cuối, nói rõ đơn vị (vs IndicatorData trả value thô
kèm unit từ parser).

**Chống tràn lan**: CẶP category/termType phải ĐÚNG (sai là rows rỗng — từng trả giá
bằng chứng: GDP đúng tt3 không phải tt2). Không quét cả 60 categories — chỉ 4–6 cần thiết.
`vs_xnk_detail` theo direction riêng (xk/xk ngược) — chọn 1 direction theo câu hỏi.

**Failure modes**: thiếu HAR session (env `VIETSTOCK_HAR_FILE`/cookie) → macro trả
permission message → skill BẢO TRUNG THỰC "macro cần session", fallback `snapshot_history`;
không được diễn giải message permission thành dữ liệu.

**Evidence live**: GDP 504 rows tới Q2/2026 · CPI 1,839 · XK 2,941 · XNK-country 3,675 ·
SBV tái cấp vốn 4.5% / tái chiết khấu 3% · USDVND 25,970 · NSO lịch CPI tháng 8.

**Acceptance**: "đánh giá vĩ mô VN" → đủ 6 mục, GDP+CPI có số quý gần nhất; thiếu session →
output nêu đúng tình trạng + dùng snapshot cache.

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
chế độ toàn cầu (RISK-ON/OFF từ rotation) · so sánh VN-vs-global (GDP VN S3 cross-ref) ·
biến số theo dõi.

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
(độ tin của odds) + tin GDELT xác nhận + market-impact nếu có (cross-ref S11).

**Chống tràn lan**: odds sort vol24h mặc định — lấy top 5, không kéo cả 20 event;
`polymarket_event` chỉ cho event THẬT SỰ liên quan câu hỏi.

**Failure modes**: GDELT rate-limit (đã gặp live: fail → backoff 20s → hồi) — 1 lần;
Gamma proxy (jina) chậm → fallback direct, chờ 1 lần.

**Evidence live**: Fed October 2026: "no change" **74.5%** (volume 24h ~2.6M USD) ·
Brazil presidential event detail OK.

**Acceptance**: "rủi ro chính trị toàn cầu" → ≥4 mục có prob_pct + provenance event URL.

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
hàm ý vị thế (cross-ref S14 trước khi hành động).

**Chống tràn lan**: 1 topic/call; từ khóa THỬ cả tiếng Việt lẫn Anh ("biển đông" →
"south china sea") — tối đa 2 lần thử rồi chấp nhận "ít coverage".

**Failure modes**: GDELT rỗng với từ khóa VN → chuyển English query là ĐẶC TRƯNG data,
không phải lỗi, ghi chú.

**Evidence live**: geo_intel("Vietnam") trả articles (ĐT Việt Nam...); event_stats("vietnam")
articles >0; gold 4,195 USD/oz live cùng phiên.

**Acceptance**: "xung đột X ảnh hưởng gì" → 5 mục verdict, có số dầu/vàng phiên gần nhất.

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

## S10. `luan-chuyen-nganh-viet-nam`

```yaml
name: luan-chuyen-nganh-viet-nam
description: >
  Dùng khi hỏi ngành nào đang hút/ra tiền ở VN ("ngành nào mạnh", "rotation ngành",
  "cổ phiếu ngành ngân hàng ra sao"). Toàn cầu → S11. 1 mã → S1.
tool_budget: 10
```

| Wave | Tools |
|---|---|
| 1 | `sector_performance`(level 1) · `vs_industry_heatmap` |
| 2 | `money_flow` · `futures_basis` · `vs_gics_index`(group của ngành nóng) |
| 3 | `compare_equities`(≤4 leaders ngành top) · `ipo_calendar_vn`(áp lực supply) |
| 4 (đào sâu) | `vs_industry_tree` → `stock_screener`(universe ngành, filters nhỏ) |

**Verdict**: tên rotation ("ngân hàng → vật liệu") bằng số PerChange trong phiên + YTD ·
xác nhận dòng tiền (NN, basis) · leaders so sánh · cảnh báo supply (IPO/thỏa thuận lớn).

**Chống tràn lan**: top 2 ngành tăng + top 1 giảm, MỖI ngành 1 call `vs_gics_index`;
`compare_equities` cap 4 — không liệt kê cả 11 ngành.

**Failure modes**: `ipo_calendar_vn` auctions rỗng = bình thường (HNX ít lịch) — ghi
"không có đấu giá sắp tới", đừng diễn giải thành tín hiệu.

**Evidence live**: Vật liệu **+1.12%** (YTD +8.9) hút tiền; Tài chính −0.8%, BĐS −1.33%
bị bán; YTD leader Năng lượng +48.2%, Dịch vụ truyền thông +39.8%; HPG 19,950 −0.50% vol 9.6tr.

**Acceptance**: "ngành nào rotation" → tên rotation + ≥6 con số chứng minh, ≤10 calls.

## S11. `luan-chuyen-tai-san-toan-cau`

```yaml
name: luan-chuyen-tai-san-toan-cau
description: >
  Dùng khi hỏi phân bổ tài sản toàn cầu ("allocation", "rủi ro hay trú ẩn", "asset
  nào mạnh", "regime"). Ngành VN → S10.
tool_budget: 10
```

| Wave | Tools |
|---|---|
| 1 | `assets_rotation` · `yf_oracle_markets` |
| 2 | `yf_global_indices` · `yf_commodities` · `crypto_derivs`(funding = risk appetite) |
| 3 | `yf_alloc_history`(2–3 asset xếp hạng cao/thấp) · `compare_assets` · `yf_market_pins` |

**Verdict**: xếp hạng 1y momentum các nhóm (RISK-ON/OFF kết luận 1 câu) · đường
allocation history của 3 asset trọng yếu · dòng mega-cap + funding xác nhận · đề xuất
khung phân bổ (KHÔNG số dư tài khoản cá nhân — disclaimer).

**Chống tràn lan**: `yf_alloc_history` 1 asset/call → cap 3 asset, chọn theo verdict wave 1.

**Failure modes**: yfinance từng flaky (curve live fail→hồi) → retry 1 lần/wave, rồi
degrade về phần còn lại; DNSE/Binance geo-block (Singapore worker) — funding có thể rỗng
→ ghi chú, dùng fear/greed bù.

**Evidence live**: S&P 7,651 (1y +14.4%), VIX 16.3 · vàng 4,195 · BTC 83,476 (+0.33%)
funding 2.8e-05 · oracle BTC +7.8%/30d, ETH +11% · rotation: Neutral/mixed.

**Acceptance**: "phân bổ tài sản toàn cầu" → bảng xếp hạng + kết luận RISK + 3 asset path.

## S12. `san-loc-co-phieu`

```yaml
name: san-loc-co-phieu
description: >
  Dùng khi cần TÌM danh sách mã theo tiêu chí ("PE thấp ROE cao", "RSI quá bán",
  "breakout", "mã ngành ngân hàng"). 1 mã đã biết → S1.
tool_budget: 12 / 5 song song
```

| Wave | Tools |
|---|---|
| 1 | `signals_screener_columns`(tra field nếu chưa chắc) · `vn_reference`(exchange/sector pool nhỏ) |
| 2 | `stock_screener` — **LUÔN truyền filters hẹp + limit ≤20** (xem chống tràn lan) |
| 3 | `signals_technical` × 5 candidates top (parallel ≤5) |
| 4 | `peer_compare`(nhóm đạt) · `watchlist_add`(lưu, hỏi user) |

**Verdict**: bảng ≤10 mã × {tiêu chí đạt, RSI/trend, PE/ROE nếu có, 1 dòng lý do} +
cảnh báo lọc (enrich ratio).

**Chống tràn lan (QUY TẮC SỐ 1 CỦA SKILL)**:
- `filters=null` full 1522 mã = ~60s → TIMEOUT đã ghi nhận live. Skill phải TRÁY:
  không có filter → truyền `vn_reference` pool (ngành/sàn) hoặc `universe` nhỏ.
- `technical:{rsi_lt:30}` chạy trên candidates đã lọc, không trên cả universe.
- `max_pe/min_roe` kéo enrich tới 30 mã — chỉ dùng khi user thật sự cần valuation;
  nếu throttle warning "<50% enriched" xuất hiện → CHỐT kết quả, không retry.
- keys `technical` chỉ 4 cái: rsi_lt/rsi_gt/above_sma20/below_sma20 — sai key là tool trả
  `unavailable` cả call.

**Failure modes**: stage 0/20 enriched (giờ cao điểm vnstock) → output vẫn có technical
stage, ghi "định giá chưa kiểm tra"; `signals_scan` 40s cap 300 mã → chỉ khi hỏi "săn
breakout", cap `max_symbols=100`.

**Evidence live**: screener RSI<70 trên HOSE trả SDA/CLH; scan 5 mã (HPG VCB FPT SSI VIC)
→ 0 hits (đúng — Donchian không có breakout hôm đó); enrich 0/20 từng xảy ra, degrade đúng.

**Acceptance**: "tìm mã RSI<30 PE<20 ngành ngân hàng" → ≤10 mã + lý do, ≤12 calls,
0 timeout kể cả giờ cao điểm (có pool-narrowing).

## S13. `danh-gia-truoc-bctc`

```yaml
name: danh-gia-truoc-bctc
description: >
  Dùng khi mùa BCTC cận kề ("FPT sắp ra báo cáo, đánh giá setup"). Phân tích mã
  không liên quan earnings → S1. Đây là bản MCP của pre_earnings prompt, có grading.
tool_budget: 10 / reuse sub-skill leg
```

| Leg | Tools | Ghi chú |
|---|---|---|
| 1 Ngày | `company_events` + `event_calendar_vn` | dated hay rumor? |
| 2 Trend | chạy `co-ban-chuyen-sau`(S23, aspect=baokao) | reuse leg, không gọi lại financial_* chồng chéo |
| 3 Thao túng | S23 aspect=chataluong trả sẵn | M-Score/Piotroski |
| 4 Kỳ vọng | `planned_targets` (S23) + `analyst_consensus` (S27) + `news_symbol` + `sentiment_score` (S26) | anchor = kế hoạch DN (VN không consensus EPS) |
| 5 Positioning | `insider_trading` (S23) + `money_flow` + `block_trades` | |
| 6 Đệm | chạy `dinh-gia-chuyen-sau`(S24) + `scenario_simulate`(-5%) | size gợi ý |

**Verdict**: grade **A/B/C** + 1 dòng evidence/leg + size đề xuất + unknowns tường minh.
Rubric: A = ≥5 leg xanh + M-Score sạch + KH rõ; B = 4–5 leg; C = <4 leg hoặc M-Score đỏ
(> −1.78).

**Chống tràn lan**: không forecast KQKD (prompt cấm, skill giữ nguyên); `sentiment_score`
heuristic không được tính là leg xanh đầy đủ.

**Evidence live (FPT)**: M **−2.06** sạch · F 2/6 · KH DT 61,850/75,400/**58,580** ·
thưởng CP 10:1 ex 21-09 · sentiment heuristic −0.25 · NN bán ròng · pt 0% phiên →
grade B.

**Acceptance**: "đánh giá trước BCTC HPG" → grade + 6 leg evidence + unknowns, ≤10 calls (reuse legs từ S23/S24/S26/S27).

## S14. `kiem-tra-rui-ro-vi-the`

```yaml
name: kiem-tra-rui-ro-vi-the
description: >
  Dùng TRƯỚC khi vào vị thế: "mua X size Y được không". Không dùng để backtest
  (→ S15) hay phân tích thuần (→ S1).
tool_budget: 12
inputs: symbols (csv), side, size_vnd
```

| Wave | Tools |
|---|---|
| 1 | `vn_quote_history`(mã 1, days=90) → `quant_risk`(returns, 252) |
| 2 | `scenario_simulate`(−5%, scale size) · `correlation_matrix`(symbols) |
| 3 | `stock_forensic` × từng mã (≤4) |
| 4 | `company_events` + `event_calendar_vn` (blackout 10 ngày) · `valuation_run` ×mã |

**Verdict**: **GO / HALF / NO-GO** + max size VND + giá invalidation + 3 unknowns.
Rubric: M-Score đỏ → skip/halve; Sharpe âm + win <45% → HALF trở xuống; blackout
(BCTC/ĐHĐCĐ ≤10 ngày) → halve; cushion định giá quyết định GO.

**Chống tràn lan**: `quant_risk` nhận returns từ wave 1 — KHÔNG gọi 90 ngày cho 8 mã
(>4 mã → từ chối, yêu cầu chọn); correlation cap 8.

**Evidence live**: VCB 63 phiên — Sharpe **−1.15**, maxDD 12.3%, win 41.3% · corr
VCB-HPG **0.50** · VCB M partial/F 4/6, HPG M −2.24/F 2/6 · cổ tức VCB ex 23-07 (không
blackout) · −5% = −2,870đ/1000cp ⇒ ~−5tr trên 100tr → HALF.

**Acceptance**: "mua 100tr VCB HPG được không" → verdict 3 thành phần + rubric chỉ ra leg nào quyết định.

## S15. `kiem-chien-luoc-backtest`

```yaml
name: kiem-chien-luoc-backtest
description: >
  Dùng khi kiểm chứng chiến lược/khung tham số ("SMA20/50 FPT có ăn không", "mùa vụ
  tháng mấy", "backtest VN30F1M"). Rủi ro vị thế cụ thể → S14.
tool_budget: 12 / timeout-call 120s
```

| Wave | Tools |
|---|---|
| 1 | `vn_quote_history`(stock) hoặc `dnse_ohlc_history`(futures/index) · `vn_index_ohlcv`(benchmark) |
| 2 | `quant_backtest`(baseline buy-hold) · `quant_factors` |
| 3 | `backtest_strategies` (sma/momentum) · `param_sweep` (fast×slow ≤30 combos) |
| 4 | `seasonality` · `correlation_matrix` · `portfolio_optimize`(nếu nhiều mã) · `pattern_match` |

**Verdict**: baseline → chiến lược → best param **KÈM worst param** (chống overfit) →
seasonality bias → kết luận "đáng tin / đáng nghi + lý do". Ghi rõ engine: numpy-only,
cost mặc định, T+2 VN chưa model trong backtest.

**Chống tràn lan**: 1 symbol mỗi lần sweep; `param_sweep` cap 30 combos đã có sẵn — skill
không tự nới; không chạy sweep >3 symbol trong 1 run.

**Evidence live**: VCB buy-hold −4.9% gross · sma_cross HPG-family: 7 trades −10.4% ·
param_sweep best **+3.7%** · seasonality bucket theo tháng · basis F1M 31–37bps.

**Acceptance**: "backtest SMA FPT 1 năm" → baseline+strategy+sweep bảng, kèm caveat.

## S16. `phan-tich-vang-ty-gia`

```yaml
name: phan-tich-vang-ty-gia
description: >
  Dùng khi hỏi giá vàng SJC/thế giới, tỷ giá USDVND, chênh lệch vàng nội-ngoại,
  áp lực tỷ giá. Lãi suất điều hành VN chung → S3.
tool_budget: 10
```

| Wave | Tools |
|---|---|
| 1 | `vn_retail_gold`(SJC+nhẫn) · `vn_msn_fx_gold`(XAUUSD+USDVND) · `sbv_rates` |
| 2 | `yf_commodities`(GC) · `fred_series`(DGS10) · `world_prediction_odds`(fed) |
| 3 | `vn_forex_ohlcv`(USDVND path) · `macro_events_vn` · `vn_retail_fx`(spreads VCB) |

**Verdict**: premium SJC vs thế giới (qui đổi: giá thế giới × (1+thuế/phí đơn giản hóa)
so mua vào BTMC — skill tự tính, ghi giả định) · trend tỷ giá + khoảng cách trần ·
điều khiển (DGS10, Fed odds, SBV) · dự báo khung (KHÔNG point-forecast).

**Chống tràn lan**: 1 call `yf_commodities` (đã gồm GC+DXY) thay vì tick riêng lẻ.

**Evidence live**: VÀNG MIẾNG SJC 999.9 (BTMC live) · XAUUSD 4,195 · USDVND 25,970 (MSN) ·
SBV 4.5% tái cấp vốn · Fed giữ 74.5%.

**Acceptance**: "vàng SJC hôm nay đắt hơn thế giới bao nhiêu" → số premium % + giả định +
2 driver.

## S17. `nhip-dap-crypto`

```yaml
name: nhip-dap-crypto
description: >
  Dùng khi hỏi BTC/ETH/crypto: giá, funding, open interest, sentiment, nến quy VND.
  Asset allocation toàn cầu → S11.
tool_budget: 8
```

| Wave | Tools |
|---|---|
| 1 | `crypto_spot`(≤5 symbols) · `crypto_derivs`(BTC ETH SOL) · `world_fear_greed` |
| 2 | `vn_crypto_ohlv`(path quy VND) · `yf_commodities`(BTC ref) |
| 3 | `polymarket_event`/`world_prediction_odds`(crypto markets nếu user hỏi xác suất) |

**Verdict**: giá + 24h volume · leverage read (funding, OI, long/short) · fear/greed +
label · path VND (nơi khác biệt của MCP này so với tool crypto thường) · rủi ro chính
sách nếu có tin (cross-ref S8, chỉ khi user hỏi).

**Evidence live**: BTC 83,476 (+0.33%) · funding 2.8e-05 · OI 95.7k · fear/greed 70–74.

**Acceptance**: "crypto sao rồi" → 4 mục verdict, funding/OI không fail batch (per-symbol error cho phép).

## S18. `theo-doi-va-bao-thuc`

```yaml
name: theo-doi-va-bao-thuc
description: >
  Dùng khi user muốn LƯU danh mục theo dõi hoặc đặt cảnh báo giá/RSI ("theo dõi
  FPT + HPG", "báo khi VCB vượt 60"). Đây là skill ghi (READ_WRITE) duy nhất bộ.
tool_budget: 10 / 9 write-calls
```

| Vòng đời | Tools |
|---|---|
| Tạo | `watchlist_create` → `watchlist_add(list_id, symbols)` |
| Đọc | `watchlist_list` · `watchlist_get` → quote bằng `vn_equity_quote_batch`(1 call) |
| Alert | `alert_create(symbol,op,threshold,metric)` → `alert_list` |
| Kiểm tra định kỳ | `alert_check(rules)` (metric: price hoặc rsi14; op gồm cross_up/cross_down) |
| Bảo quản | `alert_pause/resume` · `watchlist_update/remove` · `watchlist_delete` |

**Verdict**: xác nhận state đã lưu (id, rules) + kết quả lần kiểm tra đầu ngay trong run
(`alert_check`) + nêu vòng đời để user dùng lệnh tiếp theo.

**Chống tràn lan**: KHÔNG tạo alert trùng rule cũ (luôn `alert_list` trước `alert_create`);
1 watchlist cho 1 chủ đề; không xóa thay user khi chưa xin.

**Failure modes**: PG fail → file fallback (server tự xử lý, output ghi "stored local");
`alert_check` empty = chưa trigger, ĐÚNG — không phải lỗi; cross-state TTL 3600s: alert
cross_up cần ≥2 lần gọi mới có prev.

**Acceptance**: "theo dõi FPT+HPG, báo khi FPT>70" → state tạo được, `alert_check` chạy
xanh, cleanup demo list sau test.

## S19. `tim-kiem-tin-tuc`

```yaml
name: tim-kiem-tin-tuc
description: >
  Dùng khi TÌM tin theo từ khóa/mã/phạm vi ("tin về FPT", "tin VN hôm nay", "tin thế
  giới về dầu"). Digest tin nóng mặc định → S7/S8.
tool_budget: 10 / 4 song song
inputs: mode (symbol|vn|global), query
```

| Chế độ | Wave | Tools |
|---|---|---|
| **A. Theo mã** | 1 | `news_symbol(symbol, limit=10)` (Fireant-first, GDELT fallback trong tool) |
| | 2 (Fireant mỏng) | `corporate_calendar(symbol)` + `company_events(symbol)` |
| | 3 (đủ 5 tin CHẤT LƯỢNG → DỪNG, không gọi bù) | `news_market`(tên công ty, gdelt) |
| | 4 (nếu hỏi dư luận) | `sentiment_score(symbol)` |
| **B. VN** | 1 | `news_market(limit=10)` + `corporate_calendar(limit=20)` |
| | 2 | `news_symbol` × 2–3 mã nổi bật nhất |
| **C. Toàn cầu** | 1 | `news_market(sources=gdelt, limit=10)` |
| | 2 | `geo_intel(topic)` hoặc `event_stats(query)` |
| | 3 (có key / chọn lọc) | `web_search(query)` → `web_fetch` 1–2 nguồn chính thức |

**Verdict**: bảng tin {tiêu đề · ngày · nguồn · mã/tag liên quan · phân loại catalyst/đồn}
+ nguồn nào đang chết (pre-flight). Tin đồn → ghi nhãn "chưa xác nhận", không diễn giải.

**Chống tràn lan (quy tắc của skill)**: mode A không gọi `news_market` nếu `news_symbol`
đã ≥5 tin đạt chuẩn; GDELT rỗng → THỬ từ khóa English 1 lần rồi kết luận "ít coverage
ngôn ngữ đó"; `web_search` ẩn khi thiếu key → degrade `web_fetch`, không retry.

**Failure modes**: cả 2 nguồn news chết → `snapshot_history(kind=news_feed)` cache, GHI
RÕ "cache <ngày>"; Fireant posts `id/user null` (đặc trưng payload, không phải lỗi).

**Evidence live**: `news_symbol("VCB")` → lãi suất VCB 0.1–6% posts; mode C "dầu" —
GDELT articles live 02-10; corporate_calendar VCB → 487 docs.

**Acceptance**: 3 input mẫu (mã/VN/global) → mỗi output ≥3 tin có provenance, ≤10 calls,
không lần nào vượt 4 song song.

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

## S21. `du-doan-polymarket`

```yaml
name: du-doan-polymarket
description: >
  Dùng khi hỏi/xuất XÁC SUẤT từ Polymarket theo chủ đề ("market nào đang nóng",
  "odds bầu cử Mỹ", "bao giờ Bitcoin chạm 100k", "sự kiện crypto nào có odds").
  Fed chuyên biệt → S9; chính trị rộng → S5 (S5 dùng odds như 1 leg).
tool_budget: 6 / 1 song song
inputs: query hoặc tag (fed|politics|crypto|sports|economy...), optional slug
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `world_prediction_odds`(query hoặc tag, limit=10) | tool đã sort vol24h — tin dùng top |
| 2 | `polymarket_event`(slug — chọn 1 event duy nhất user quan tâm) | drill-down outcomes đầy đủ |
| 3 (chọn lọc ≤2) | `polymarket_event`(slug thứ 2) | tối đa 2 drill-down/run |

**Verdict**: bảng event {title · prob_pct từng outcome · volume24h · liquidity · end-date} +
2 cờ bắt buộc: (1) liquidity thấp (<50k) → "odds kém tin"; (2) end-date đã qua trong dữ liệu
→ loại. Kết luận 1 câu "thị trường đặt cược X với xác suất Y".

**Chống tràn lan**: drill-down tối đa 2 event/run — người dùng chọn, skill không tự
mở cả top-10; query rỗng kết quả → ĐỔI tag 1 lần rồi kết luận "không có market cho chủ đề".

**Failure modes**: jina proxy chậm → tool tự fallback direct (bên trong, warnings cho biết);
Gamma chết cả 2 đường → `unavailable`, nói rõ "không có odds", không bịa xác suất.

**Evidence live**: Fed T10/2026 no-change **74.5%** (vol 2.6M); Brazil presidential detail
`polymarket_event` OK; sort vol24h hoạt động (P14).

**Acceptance**: "polymarket đang nóng gì về kinh tế" → ≥5 event + cờ tin-cậy trên từng dòng.

## S22. `ky-thuat-chuyen-sau`

```yaml
name: ky-thuat-chuyen-sau
description: >
  Dùng khi hỏi THUẦN kỹ thuật một mã: chỉ báo, pattern, hỗ trợ-kháng cự, vị thế 52w,
  tương quan quá khứ, intraday/orderbook ("VCB kỹ thuật sao", "FPT có breakout không",
  "đọc băng HPG"). Cơ bản/định giá → S23/S24; săn toàn thị trường → S12.
tool_budget: 8 / 3 song song
inputs: symbol, optional timeframe (swing|intraday)
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 1 | `signals_technical`(symbol) | 1 call = RSI/MACD/Bands/ADX/patterns/S-R/RS/pos_52w/sma150 |
| 2 (chọn) | `pattern_match`(symbol) · `vn_quote_history`(symbol, days=250) | analogy + tự vẽ đường xu hướng từ nến |
| 3 (intraday) | `dnse_latest_trade` · `dnse_orderbook` · `vn_trades` | ≤3, cùng upstream DNSE |
| 4 (index context) | `vn_index_ohlcv`(VNINDEX) | khi cần so trend index |

**Verdict**: trạng thái trend (đỉnh/đáy/downtrend/đi ngang bằng SMA stack + ADX) · momentum
(RSI/MACD/stoch) · vùng S-R + giá hiện tại trong vùng nào · pattern phát hiện + xác suất
lịch sử (pattern_match corr) · RS vs VNINDEX · kết luận timing (MUA/CHỜ/BÁN + trigger giá).

**Chống tràn lan**: wave 2 CHỈ khi user hỏi "mẫu hình/quá khứ"; wave 3 CHỈ khi intraday;
`interval` khác 1D → tool trả warning — skill tự đổi về 1D, không retry đổi params.
`signals_technical` 1 call đã đủ 80% verdict — đây là skill mẫu mực "1 tool trụ cột".

**Failure modes**: mã mới lên sàn <60 nến → indicators null, báo "thiếu lịch sử"; DNSE
hết giờ → orderbook rỗng là đúng; `pattern_match` corr <0.4 = không có analogy đáng tin.

**Evidence live**: VCB — RSI 39.2, ADX 12.1 (trend yếu), MACD −0.31/−0.13, EMA10 58.09,
support/resistance 20d, pos_52w 0.21, recommend Sell (HPG); HPG pattern best_corr 0.409
(yếu — ghi đúng); orderbook VCB depth live; băng 10:18 giá 58.1.

**Acceptance**: "RSI FPT và vùng hỗ trợ" → trigger 2 mục verdict ≤2 calls; "intraday SSI"
→ thêm leg orderbook, tổng ≤8.

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

## S25. `so-sanh-cung-nganh`

```yaml
name: so-sanh-cung-nganh
description: >
  Dùng khi so sánh 2–6 mã CÙNG NGÀNH hoặc chọn leader ngành ("VCB vs BID vs CTG",
  "steel mạnh nhất là ai", "ngân hàng nào đáng mua nhất"). 1 mã → S1/S23/S24;
  ngành chảy tiền thế nào → S10.
tool_budget: 8 / 4 song song
inputs: symbols (2–6) hoặc sector/industry name
```

| Wave | Tools | Ghi chú |
|---|---|---|
| 0 (nếu nhập ngành) | `vn_reference`(exchange/industry) → chọn ≤6 mã | hoặc `vs_industry_tree`(tra GICS id) 1 call |
| 1 | `compare_equities`(≤4, song song được 2 calls khi 5–6 mã: chia 4+2 qua `peer_compare`) | overview + momentum |
| 2 | `signals_technical` × ≤4 mã (parallel 4) | RS/pos_52w từng ứng viên |
| 3 | `financial_ratios` × ≤3 (song song 3; cap vnstock burst) | PE/ROE/biên |
| 4 (bối cảnh ngành) | `vs_gics_index`(group) · `vn_equity_quote_batch`(toàn bộ ≤6, 1 call) | index ngành + bảng giá 1 shot |

**Verdict**: bảng xếp hạng {mã · PE · ROE · momentum · RS · giá} + **1 dòng luận chọn**
(leader = chất lượng×momentum; định giá tốt = PE thấp trong nhóm ROE cao) + cảnh báo
(correlation_matrix cross-ref khi user hỏi "chia tiền cả nhóm").

**Chống tràn lan**: cap tuyệt đối 6 mã/run — trên 6 → yêu cầu thu hẹp; `signals_technical`
tối đa 4; thiếu dữ liệu 1 tiêu chí → xếp hạng partial + ghi "n/6 mã có đủ", không loại âm thầm.
`stock_screener` (S12) thay thế khi user đưa FILTER chứ không đưa mã.

**Failure modes**: enrich throttle giờ cao điểm (0/20 từng live) → ratios rỗng → verdict
kỹ thuật-only, ghi chú; vn_reference industry không match → thử `vs_industry_tree` 1 lần.

**Evidence live**: compare_equities VCB-vs-HPG 2.8s (rows+momentum) · peer_compare cap 6 ·
vs_gics_index 3 nhóm live · quote_batch 1 request VN30 · HOSE universe 757 mã.

**Acceptance**: "so sánh bank" → bảng ≥4 mã xếp hạng + luận chọn 1 dòng, ≤8 calls.

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

# PHẦN 2 — MA TRẬN BAO PHỦ 135 TOOLS (rev.2)

Mỗi tool có đúng **1 HOME skill**. S5/S9 là skill tổ chức (0 home, chỉ cross-ref —
không cồng cồng giữa 27 skill). Cross-ref giữa skills là design, không phải vi phạm.

| Skill (home) | Số tool | Tools home |
|---|---|---|
| S1 điều phối | 4 | `stock_overview`• `symbol_lookup`• `event_calendar_vn`• `evidence_bundle`• |
| S2 thị trường | 21 | `market_overview`• `market_snapshot`• `market_movers`• `breadth_scan`• `market_candles_batch`• `vs_market_info`• `vs_market_price`• `vs_market_index`• `exchange_calendar`• `dnse_market_status`• `dnse_working_dates`• `vs_selftrading`• `vs_nn_flow`• `money_flow`• `futures_basis`• `block_trades`• `signals_scan`• `brief_build`• `dnse_foreign_flow`• `dnse_ws_snapshot`• `dnse_indices`• |
| S3 macro VN | 9 | `vs_categories`• `vs_indicator_data`• `vs_xnk_detail`• `sbv_rates`• `macro_events_vn`• `economic_calendar`• `snapshot_history`• `vs_currency`• `vn_retail_fx`• |
| S4 macro global | 9 | `fred_series`• `world_macro_country`• `yf_yield_curve`• `yf_regime_assets`• `yf_world_indices`• `yf_global_indices`• `assets_rotation`• `world_fear_greed`• `vn_global_index`• |
| S5 chính trị (0 home — cross-ref S20/S21/S6/S7) | 0 | — (pure cross-ref) |
| S6 xung đột | 1 | `event_stats`• |
| S7+S8 news digest | 3 | `news_market`• `corporate_calendar`• `yf_mega_flows`• |
| S9 du-doan-fed (0 home — cross-ref S21/S4) | 0 | — (pure cross-ref) |
| S10 ngành VN | 5 | `sector_performance`• `vs_industry_heatmap`• `vs_industry_tree`• `vs_gics_index`• `ipo_calendar_vn`• |
| S11 rotation global | 5 | `yf_oracle_markets`• `yf_alloc_history`• `yf_market_pins`• `compare_assets`• `yf_commodities`• |
| S12 sàng lọc | 6 | `stock_screener`• `signals_screener_columns`• `vn_reference`• `vn_listing`• `vn_equity_quote_batch`• `alert_check`• |
| S13 trước BCTC | 1 | `company_events`• |
| S14 risk vị thế | 3 | `vn_quote_history`• `quant_risk`• `scenario_simulate`• |
| S15 backtest | 12 | `quant_backtest`• `quant_factors`• `backtest_strategies`• `param_sweep`• `seasonality`• `correlation_matrix`• `portfolio_optimize`• `dnse_ohlc_history`• `vn_equity_ohlcv`• `vn_futures_ohlcv`• `vn_index_ohlcv`• `dnse_vn30f1m_live`• |
| S16 vàng tỷ giá | 3 | `vn_retail_gold`• `vn_forex_ohlcv`• `vn_msn_fx_gold`• |
| S17 crypto | 3 | `crypto_spot`• `crypto_derivs`• `vn_crypto_ohlv`• |
| S18 theo dõi alert | 12 | `watchlist_create`• `watchlist_list`• `watchlist_get`• `watchlist_add`• `watchlist_update`• `watchlist_remove`• `watchlist_delete`• `alert_create`• `alert_list`• `alert_pause`• `alert_resume`• `alert_delete`• |
| S19 tìm tin | 1 | `web_fetch`• |
| S20 bất ổn quốc gia | 1 | `geo_intel`• |
| S21 dự đoán polymarket | 2 | `world_prediction_odds`• `polymarket_event`• |
| S22 kỹ thuật sâu | 5 | `signals_technical`• `pattern_match`• `dnse_orderbook`• `vn_trades`• `dnse_latest_trade`• |
| S23 cơ bản sâu | 14 | `financial_detail`• `financial_statements`• `financial_ratios`• `planned_targets`• `vs_financeinfo`• `vs_financial_terms`• `vs_financial_norms`• `vs_company_info`• `vn_fundamentals`• `vn_company`• `holders`• `insider_trading`• `dividends_splits`• `stock_forensic`• |
| S24 định giá sâu | 3 | `valuation_run`• `vs_overview_trading`• `vs_trading_info`• |
| S25 so sánh ngành | 2 | `compare_equities`• `peer_compare`• |
| S26 sentiment | 2 | `sentiment_score`• `news_symbol`• |
| S27 cơ hội CTCK | 2 | `analyst_consensus`• `vs_documents`• |
| Contract chung (pre-flight/ops) | 6 | `source_status`• `vs_auth_status`• `doctor`• `oracle_meta`• `runs_list`• `run_get`• |

**Tổng home: 135/135 = 100%, không trùng, không mồ côi**
`web_search` = tool thứ 136 gate theo key, ngoài catalog.

Cross-ref đáng nhớ: `alert_check`•(S12) — S18 bước kiểm tra · `news_market`•(S7) —
S5/S6/S8/S19/S20 · `geo_intel`•(S20) — S5/S6/S8/S19 · `event_stats`•(S6) — S5/S19/S20 ·
`world_prediction_odds`/`polymarket_event`•(S21) — S5/S9/S16/S17 ·
`yf_commodities`•(S11) — S6/S16/S17 · `money_flow`/`futures_basis`/`block_trades`•(S2) —
S10/S13 · `stock_forensic`/`financial_*`/`planned_targets`/`holders`/`insider_trading`•(S23) —
S13 reuse leg · `valuation_run`•(S24) — S13/S14 · `sentiment_score`/`news_symbol`•(S26/S19
home S26) — S7/S13 · `analyst_consensus`•(S27) — S13/S1 · `signals_technical`•(S22) —
S12/S25/S5-ai · `vn_quote_history`•(S14) — S22/S24/S15 · `pattern_match`•(S22) —
S15/S5-ai · `evidence_bundle`•(S1) — mọi verdict cuối · `snapshot_history`•(S3) —
news/macro cache khi upstream chết.

Ghi chú 3 WS tools (`dnse_foreign_flow`•/`dnse_ws_snapshot`•/`dnse_indices`•, home S2):
remote không worker → `unavailable`; mọi skill đã thiết kế đi qua `money_flow` (tự
fallback vs_nn_flow) — harness đừng bắn trực tiếp.

# PHẦN 3 — QUY TRÌNH HARNESS BUILD & ACCEPTANCE

1. **Kết nối trước**: config 0.1, chạy `mcp probe` + `tools/list` = 136 tools.
2. **Scaffold**: 27 thư mục `skills/<slug>/SKILL.md` theo template Phần 1 (frontmatter +
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
