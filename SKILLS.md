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
>
> **Bản 06-10-2026 (fix feedback review, đợt 2)** — bỏ "trong tối đa X calls" khỏi
> descriptions (tool_budget frontmatter đã phủ); `bat-on` 1.2.0 (bỏ tên nước khỏi keywords,
> geo_intel đã lọc chính trị + aggregate); `co-ban` 1.1.1 (bắt buộc giải thích con số
> forensic); `xung-dot` 1.1.1 (+Step 2b máy bay quân sự `geo_intel military=true`, port
> oracle 8010); `truoc-bctc` 1.1.1 (bỏ Step 1 chốt ngày BCTC — không công khai; notes
> planned_targets session-gated + scenario_simulate tuyến tính); `vi-mo-quoc-te/vn`
> 1.1.1/1.2.1; `ky-thuat` 1.2.1; `sentiment` 1.1.1 (top 20 posts + comments);
> `so-sanh` 1.2.1.
>
> **Bản 06-10-2026 (merge upstream harness)** — merge `origin/main` (tool-search, permission,
> todos, compact) vào nhánh `MCP-server` OpenTrading (`baf7a2c` + `da10329`): harness giờ có
> `ask_user`/`todo_write`/`tool_search` + 139 MCP tools deferred sau `tool_search` (model thấy
> tên trong catalog, nạp schema khi cần — vẫn callable); registry 160 (21 local). Turn-guards
> (doom-loop + budget cứng 20) bị upstream thay bằng `PermissionGate` (ask trước tool có side
> effect); `tool_budget` trong skill vẫn là hướng dẫn model đọc. Verify: 238 tests pass · tsc clean.
>
> **Bản 06-10-2026 (chuyển tiếng Anh, tối ưu token)** — toàn bộ 26 skills chuyển body +
> `description` sang English (tiktoken cl100k_base: **36,131 → 27,736 tokens, tiết kiệm 23%**);
> GIỮ NGUYÊN: slug tên skill, `triggers.keywords` tiếng Việt (match input user), câu user
> mẫu tiếng Việt trong description, verdict labels user-visible (ỔN ĐỊNH/CẢNH BÁO/BẤT ỔN/
> NGHIÊM TRỌNG, Tích cực/Tiêu cực/Động lực, kVND, CHƯA XÁC NHẬN...), tool names/budgets/
> live evidence. Mỗi skill thêm dòng: "Verdict labels, units and output formatting stay in
> Vietnamese (user-visible); answer in the user's language (Vietnamese by default)."
> Version bump minor (1.1.x→1.2.0, 1.2.x→1.3.0). Verify: routing TV→English 6/6 câu
> (T01 verdict thật 3897 ch + chart_render); 238 tests pass · tsc clean.

## Đặc tả frontmatter chung

| Field | Bắt buộc | Ý nghĩa |
|---|---|---|
| `name` | ✔ | slug kebab-case không dấu, ≤64 ký tự, trùng tên folder |
| `description` | ✔ | front-load keywords user hay nói; có "Dùng khi…/Không dùng khi…" + tên skill loại trừ (opencode chỉ thấy field này để routing) |
| `when_to_use` | ✔ (harness) | câu hỏi mẫu + loại trừ chi tiết, mirror vào body `Khi nào dùng` |
| `activation` | ✔ | `auto` (model nạp khi khớp) / `manual` (chỉ /skill <tên>, ví dụ kiem-tra-nguon-du-lieu) |
| `requires_tools` | khuyến khích | skill chỉ hiện trong catalog khi MỌI tool này có mặt (gate theo tool hiện có; sau merge upstream 06-10: 139 MCP tools deferred sau `tool_search` — vẫn callable) |
| `tool_budget` | với skill thiết kế | số lần gọi tool tối đa mỗi run; hướng dẫn model đọc trong body [merge upstream 06-10: turn-guard cứng 20/lượt + doom-loop bị thay bằng `PermissionGate` — ask trước tool side-effect] |
| `triggers.keywords` | khuyến khích | pre-routing: khớp keyword → gợi ý skill ở reminder |
| `version` | ✔ | semver (eval-fix → 1.1.1-1.2.2; English conversion 06-10 bump → 1.2.0/1.3.0) |

## Bảng tổng quan

| # | Skill | Kích hoạt | Budget | Version | Tools yêu cầu (đã bỏ prefix mcp__) |
|---|---|---|---|---|---|
| 1 | `bat-on-quoc-gia` | auto | 6 | 1.3.0 | geo_intel |
| 2 | `co-ban-chuyen-sau` | auto | 9 | 1.2.0 | financial_detail |
| 3 | `danh-gia-tinh-hinh-chinh-tri-toan-cau` | auto | 8 | 1.2.0 | — |
| 4 | `danh-gia-tinh-hinh-xung-dot` | auto | 9 | 1.2.0 | event_stats |
| 5 | `danh-gia-truoc-bctc` | auto | 10 | 1.2.0 | company_events |
| 6 | `danh-gia-vi-mo-quoc-te` | auto | 10 | 1.2.0 | fred_series |
| 7 | `danh-gia-vi-mo-viet-nam` | auto | 12 | 1.3.0 | vs_indicator_data |
| 8 | `devil-advocate` | auto | — | 1.3.0 | — |
| 9 | `dinh-gia-chuyen-sau` | auto | 7 | 1.2.0 | valuation_run |
| 10 | `du-doan-fed` | auto | 8 | 1.2.0 | world_prediction_odds |
| 11 | `du-doan-polymarket` | auto | 6 | 1.2.0 | world_prediction_odds |
| 12 | `explain-term` | auto | — | 1.3.0 | — |
| 13 | `kiem-chien-luoc-backtest` | auto | 12 | 1.3.0 | quant_backtest |
| 14 | `kiem-tra-nguon-du-lieu` | manual | 12 | 1.2.0 | doctor |
| 15 | `ky-thuat-chuyen-sau` | auto | 8 | 1.3.0 | signals_technical |
| 16 | `nhip-dap-crypto` | auto | 6 | 1.3.0 | crypto_spot |
| 17 | `phan-tich-chuyen-sau-1-ma` | auto | 8 | 1.3.0 | stock_overview |
| 18 | `phan-tich-sentiment` | auto | 6 | 1.2.0 | sentiment_score |
| 19 | `phan-tich-vang-ty-gia` | auto | 10 | 1.3.0 | vn_retail_gold |
| 20 | `so-sanh-cung-nganh` | auto | 8 | 1.3.0 | compare_equities |
| 21 | `tim-co-hoi-bao-cao-ctck` | auto | 8 | 1.3.0 | analyst_consensus |
| 22 | `tim-kiem-tin-tuc` | auto | 10 | 1.3.0 | news_symbol |
| 23 | `tin-tuc-nong-quoc-te` | auto | 8 | 1.2.0 | news_market |
| 24 | `tin-tuc-nong-viet-nam` | auto | 9 | 1.2.0 | news_market |
| 25 | `ve-bieu-do-ky-thuat` | auto | 8 | 1.3.0 | chart_render (local) |
| 26 | `vn-market-basics` | auto | — | 1.3.0 | — |

---

## 1 · bat-on-quoc-gia
> File thật: `OpenTrading/skills/bat-on-quoc-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: bat-on-quoc-gia
description: Assess the political stability or instability of ONE country (protests, coups, unrest) on a 4-level scale with evidence. Always use this skill when the user asks about a specific country's stability situation — e.g. "Thái Lan đang bất ổn gì", "Trung Quốc có ổn định không", "Bangladesh sau đảo chính ra sao" — even when the user doesn't explicitly say they want an "đánh giá".
activation: auto
requires_tools: [mcp__opentrading__geo_intel]
tool_budget: 6
triggers:
  keywords: [bất ổn, bất ổn quốc gia, biểu tình, đảo chính, ổn định]
version: 1.3.0
```


# Assessing Single-Country Stability

Assess 1 country on the ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG scale, each level backed by evidence with URL. If several countries are asked, loop this skill once per country instead of merging. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user names ONE country + asks about unrest/stability/protests/coup.
- When NOT to use (use another skill instead):
  - Multi-country comparison/map, global elections/policy → `danh-gia-tinh-hinh-chinh-tri-toan-cau`.
  - Armed conflict/combat + market impact → `danh-gia-tinh-hinh-xung-dot`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: measure intensity (GDELT counts + severity)
- [ ] Step 2: verify with news (only if Step 1 is thin)
- [ ] Step 3: 4-level verdict + provenance
```

**Step 1: Measure intensity (mandatory).**

Run 2 calls in parallel against the same upstream GDELT: `geo_intel` (topic = country name in English) + `event_stats` (query = country name in English). `geo_intel` pre-filters political news (drops sports/noise) and returns aggregates (count/by_day/top_sources); `event_stats` returns the base-rate aggregate — use geo_intel for articles, event_stats for count vs baseline. NEVER use web_search/web_fetch before GDELT counts exist — web is only used in Step 2 when Step 1 is thin. Query in English once + at most 1 variant; empty Vietnamese queries are a data characteristic, not an error. On GDELT rate-limit, retry at most 1 time after backoff (server caches 600s); if it still fails, record honestly and base the verdict on older data.

**Step 2: Verify with news (only if Step 1 is thin).**

Run `news_market` (sources=gdelt, filtered by country name) sequentially after Step 1. If Step 1 already has counts + titles, stop — do not run Step 2. Thin coverage is a RESULT ("low-coverage ≠ stable"); never infer ỔN ĐỊNH from it.

**Step 3: Lock the verdict.**

Only add `yf_commodities` or `assets_rotation` (1 call) when the user explicitly asks about "ảnh hưởng thị trường". At most 6 calls/run because every extra call burns quota and dilutes the verdict — stop as soon as evidence is sufficient.

## Template

ALWAYS use this exact verdict structure:

1. **4-level verdict (pick exactly 1):** ỔN ĐỊNH / CẢNH BÁO / BẤT ỔN / NGHIÊM TRỌNG.
2. **Basis (1 line per item + URL):** GDELT event frequency (this run is the baseline) · severity (protest/conflict/coup keywords in titles) · neighbor-country coverage · transmission to prices if a sub-step ran (oil/gold, unit USD/oz or % move).
3. **Provenance:** each item requires 1 line of evidence + source URL.

## Examples

**Example 1:**
Input: Bất ổn Thái Lan
Output:
```
Verdict: CẢNH BÁO
- GDELT event frequency up vs baseline ... + URL
- Severity: protest keyword appears ... + URL
- Neighbor coverage: ...
Provenance: (1 line of evidence + URL per item above)
```

**Example 2 (thin coverage):**
Input: Bất ổn Lào
Output: Verdict with the honest note "low-coverage ≠ stable"; never infer ỔN ĐỊNH.
---

## 2 · co-ban-chuyen-sau
> File thật: `OpenTrading/skills/co-ban-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: co-ban-chuyen-sau
description: Read financial statements and assess the fundamental quality of 1 ticker (M-Score manipulation, F-score, growth, ownership, dividends). Always use this skill when the user asks to read financial statements, earnings quality, M-Score, major shareholders, insider or dividends of a ticker — e.g. "BCTC FPT có gì lạ", "VCB có thao túng không", "cổ đông lớn HPG" — even when the user doesn't explicitly say they want "phân tích cơ bản".
activation: auto
requires_tools: [mcp__opentrading__financial_detail]
tool_budget: 9
triggers:
  keywords: [bctc, báo cáo tài chính, cơ bản, lợi nhuận gộp, nợ phải trả, vốn chủ, m-score, thao túng, cổ đông lớn, cổ tức, kế hoạch kinh doanh]
version: 1.2.0
```


# Analyzing Single-Stock Fundamentals

PURE fundamentals analysis of 1 ticker by aspect: whichever aspect is asked, run only that leg then stop — don't scan the whole statement set "just to be safe". Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks about financial statements (BCTC), earnings quality, M-Score/manipulation, F-score, business plan, major shareholders, insider, dividends of 1 ticker.
- When NOT to use (use another skill instead):
  - Technical questions (RSI, MACD, breakout, support/resistance) → `ky-thuat-chuyen-sau`.
  - Valuation questions (fair value, PER, upside) → `dinh-gia-chuyen-sau`.
  - Comparing 2-6 tickers → `so-sanh-cung-nganh`.
  - Full analysis of 1 ticker → `phan-tich-chuyen-sau-1-ma`.
  - Reading broker reports (not original financial statements) → `tim-co-hoi-bao-cao-ctck`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 0: check whether the JWT is alive
- [ ] Step 1: statement core + quality (aspect chataluong stops here)
- [ ] Step 2-3: only run the aspect the user asked (trend/ratios, ownership/plan)
- [ ] Step 4: lock the 7-item verdict + provenance
```

**Step 0: JWT check (mandatory, call directly first).**

Run `vs_auth_status`. JWT alive → `financial_detail` may be used; JWT dead → switch to the mirror branch `vs_financeinfo` — these two tools never run in parallel because they share the same source of numbers.

**Step 1: Statement core + quality.**

Run 2 calls in parallel: `financial_detail` (statement=KQKD, periods_n=4) + `stock_forensic` (symbol). If the user only asks about quality (`chataluong`), stop right here.

**Step 2: Expand by aspect (each aspect is 1 leg, run only the leg asked).**

- Trend/ratios: `financial_statements` · `financial_ratios` · `vn_fundamentals` (at most 3 calls).
- Ownership/plan (`sohuu`/`cophieu`/`kehoach`): `planned_targets` · `holders` · `insider_trading` · `dividends_splits` (+ Step 1 if a base is needed).
- Reference: `vs_financial_norms` / `vs_financial_terms` / `vs_company_info` — only when norm_id/period need explaining.
- Never call `vs_documents` here (that is `tim-co-hoi-bao-cao-ctck`'s tool). Cash-flow (LCTT) / balance-sheet (CDKT) statements are only fetched when the user explicitly asks for cash flow/balance sheet via the `statement` param.

**Step 3: Validate before locking the verdict.**

Any leg that comes back empty → partial verdict + state clearly which source is missing; never fabricate numbers to fill gaps. For each annual forensic model, inspect status and applicability: null/partial means insufficient evidence; Beneish is not applicable to financial firms and Piotroski is unsupported for them. Never turn missing, not_applicable or unsupported into M=0, a clean verdict or a fraud conclusion. If `financial_detail` periods exceed the package → empty rows + warning → degrade to `vs_financeinfo` exactly once, state the fallback clearly. `vn_company` is slow ~30s when throttled so schedule it last; if missing, record as missing.

## Template

ALWAYS use this exact verdict structure, each item with numbers + trend + provenance:

1. Growth quality: Revenue/Profit 4 quarters + QoQ/YoY trend + margins (`provenance: financial_detail`).
2. Key ratios (`provenance: financial_ratios` / `vn_fundamentals`).
3. Annual M-Score + F-score, model status, coverage and review flags (`provenance: stock_forensic`); keep these separate from the quarterly growth trends in item 1.
4. Vs plan: beat/miss % (`provenance: planned_targets`).
5. Ownership structure + insider changes (`provenance: holders` / `insider_trading`).
6. Dividend policy (`provenance: dividends_splits`).
7. 1-sentence conclusion: CƠ BẢN TỐT/TRUNG BÌNH/YẾU + top 3 risks.

**Explaining forensic numbers (mandatory when leg 3 exists):** don't just list numbers — explain what each variable means and why it leads to the conclusion:
- Interpret scores only when that model is complete and applicable, using annual reports with matching company, fiscal periods and report scope. null/partial/not_applicable/unsupported means insufficient evidence for a standard score; show missing inputs and coverage instead of treating missing signals as failures.
- M-Score has eight variables: DSRI (receivables relative to sales), GMI (gross margin), AQI (asset quality using net PPE), SGI (sales growth), DEPI (depreciation rate), SGAI (selling and administration expenses), LVGI (long-term debt plus current liabilities relative to assets), TATA (CFO-based accruals). Only a complete applicable score may be compared with −1.78; exceeding the cutoff warrants further review and does not establish fraud. A lower score does not prove clean accounts.
- F-score has nine signals: positive ROA, positive CFO, rising ROA, CFO above ROA, falling leverage, rising current ratio, no equity issuance, rising gross margin and rising turnover. Explain each evaluated signal using its annual periods and source lines. Report the standard x/9 only for all nine valid inputs; otherwise score=null with passed/evaluated coverage.
- Any forensic interpretation must cite its inputs, periods and model status; never label missing data as clean or fraudulent.

## Examples

**Example 1:**
Input: BCTC FPT có gì lạ
Output (Wave 1 enough, 2 calls): annual M-Score/F-score with model status and missing inputs, plus a separate 4-quarter Revenue/Profit trend and 7-item verdict; don't open Waves 3–4.

**Example 2 (live 02-10-2026, don't fabricate new numbers):**
Input: cơ bản FPT
Output: FPT detail 25 norms × 138 numbers · historical M −2.06/F 2/6 used an obsolete model and must not be interpreted as current standard scores; request annual stock_forensic status/coverage · KH DT 61,850/75,400/58,580 · VCB holders SBV 74.8% · VCB dividend 450đ · insider empty is correct data.
---

## 3 · danh-gia-tinh-hinh-chinh-tri-toan-cau
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-chinh-tri-toan-cau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-tinh-hinh-chinh-tri-toan-cau
description: Map global political risk (elections, policy, international tensions) in 4-6 items, each with odds probability + confirming GDELT news + URL. Always use this skill when the user asks about political/election/policy risk at multi-country scale — even when the user doesn't explicitly say they want a "bản đồ rủi ro".
activation: auto
tool_budget: 8
triggers:
  keywords: [địa chính trị, bầu cử, chính trị, chính sách mỹ, căng thẳng quốc tế, rủi ro chính trị]
version: 1.2.0
```


# Mapping Global Political Risk

This skill organizes cross-referencing (no single home tool — it combines odds + news from multiple sources). Every verdict item must have an event URL + news URL; if either is missing, say so clearly. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks for a global political risk map, elections, policy, international tensions (multiple events, need odds + news combined).
- When NOT to use (use another skill instead):
  - A specific armed conflict → use `danh-gia-tinh-hinh-xung-dot`.
  - Single-country unrest → use `bat-on-quoc-gia`.
  - Just want pure Polymarket odds/board → use `du-doan-polymarket`.
  - Pure Fed cut/hold → use `du-doan-fed`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: odds + intel in parallel
- [ ] Step 2: drill down into relevant events (at most 2 slugs)
- [ ] Step 3: verify with news (1-2 official sources)
- [ ] Step 4: 4-6 item verdict + provenance
```

**Step 1: Odds + intel (parallel, mandatory).**

Run `world_prediction_odds` (tag=fed/politics/elections per the question) + `geo_intel` (topic). Odds come sorted by vol24h so take only the top 5 — pulling all 20 events is sprawl.

**Step 2: Drill-down (parallel, sequential after Step 1).**

Run `polymarket_event` (top 1-2 slugs) + `event_stats` (query). Only drill events actually relevant to the question, at most 2 slugs/run. Do not stack `geo_intel` + `event_stats` + `news_market` with the same query for more than 1 round.

**Step 3: Verify with news (sequential after Step 2).**

Run `news_market` (sources=gdelt) + `web_fetch` 1-2 official source URLs from the news. Stop once 4 items have prob + confirming news.

**Step 4: Validate before locking.**

GDELT rate-limit → backoff 20s, retry at most 1 time → if it still fails, record honestly "missing GDELT news, verdict based on odds only". If Gamma is slow the tool falls back to direct automatically; wait once. Stale odds (end-date passed) → filter `end > today`, drop expired events. If both paths are dead, record "no odds available"; never fabricate probabilities.

## Template

ALWAYS use this exact verdict structure:

1. **Event:** name + 1-line context.
2. **Probability:** prob_pct per outcome (unit %) + end-date.
3. **Odds reliability:** 24h volume + liquidity (unit USD; <50k flags "odds unreliable").
4. **Confirming GDELT news:** 1 line + URL.
5. **Market-impact if any:** transmission channel + URL.
6. **Provenance:** each item requires event URL + news URL.

## Examples

**Example 1 (live 02-10-2026, don't fabricate new numbers):**
Input: Rủi ro chính trị toàn cầu
Output: Fed October 2026 "no change" 74.5% (24h volume ~2.6M USD) · Brazil presidential event OK · every item has prob_pct + provenance event URL.
---

## 4 · danh-gia-tinh-hinh-xung-dot
> File thật: `OpenTrading/skills/danh-gia-tinh-hinh-xung-dot/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-tinh-hinh-xung-dot
description: Assess 1 armed conflict (intensity, whether oil/gold prices have priced it in, transmission channels, escalation probability). Always use this skill when the user asks about a specific conflict/combat and its impact on markets — e.g. "Trung Đông leo thang, dầu lên không", "Biển Đông căng thẳng ảnh hưởng gì" — even when the user doesn't explicitly say they want a "đánh giá xung đột".
activation: auto
requires_tools: [mcp__opentrading__event_stats]
tool_budget: 9
triggers:
  keywords: [xung đột, chiến tranh, biển đông, trung đông, leo thang, dầu hay vàng lên, chiến sự]
version: 1.2.0
```


# Assessing Armed-Conflict Market Impact

Answer 5 fixed items: intensity → whether the price has priced it in → transmission channel → escalation probability → position implication. No direct buy/sell recommendations. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user names 1 specific conflict/combat + asks about intensity, escalation, whether the price has priced it in, transmission channel, position implication.
- When NOT to use (use another skill instead):
  - Broad politics/elections → use `danh-gia-tinh-hinh-chinh-tri-toan-cau`.
  - Single-country unrest (protests/coup, not yet combat) → use `bat-on-quoc-gia`.
  - Just want pure odds → use `du-doan-polymarket`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: measure intensity (GDELT, parallel)
- [ ] Step 2: check whether the price has priced it in (oil/gold, parallel)
- [ ] Step 2b: military aircraft frequency near the conflict zone (geo_intel military=true)
- [ ] Step 3: escalation odds + verification (only if needed)
- [ ] Step 4: 5-item verdict
```

**Step 1: Measure intensity (mandatory, parallel).**

Run `geo_intel` (conflict topic) + `event_stats` (query) at the same time. Try keywords in both Vietnamese and English; GDELT being empty for Vietnamese is a data characteristic (record "VN query empty, used EN query X", retry EN at most 1 time), not an error.

**Step 2: Check whether the price has priced it in (parallel, sequential after Step 1).**

Run `yf_commodities` (oil + gold) + `assets_rotation`. If the latest session is missing, use the most recent session available + state the date clearly; never fabricate current prices. Step 1 counts + Step 2 oil/gold prices are enough for a basic verdict.

**Step 2b: Military aircraft frequency (oracle 8010 reference, 1 call).**

Run `geo_intel` with `military=true` — returns live military aircraft from adsb.lol (count, by_country, by_type), distance to the nearest conflict zone (km) and signal-loss diff (aircraft disappearing near the zone = suspected transponder shutdown, an OSINT signal). Read it as: high count + many tankers/recon near the zone → activity buildup; many "Unknown" operators → official tracking lost. If the tool is dead (adsb.lol 429/geo-block), record honestly; never fabricate aircraft counts.

**Step 3: Escalation odds + verification (only if needed).**

Run `world_prediction_odds` (war keywords) + `web_search`/`web_fetch` (1-2 sources only). If there is no market for the war, record "no odds available"; don't substitute a personal take.

**Step 4: Validate before locking.**

Only 1 topic/call; at most 2 keyword attempts ("biển đông" → "south china sea") then accept "thin coverage". Don't expand to multiple wars within 1 run (if the user asks broadly, suggest splitting per conflict).

## Template

ALWAYS use this exact verdict structure:

1. **Intensity:** GDELT event counts trend (unit counts + up/down trend) + URL.
2. **Priced in yet:** oil/gold move vs baseline (unit USD/barrel, USD/oz, % move) + URL.
3. **Transmission channel:** energy → inflation → rates, 1–2 lines + URL.
4. **Escalation probability:** odds prob_pct (unit %) + end-date + event URL.
5. **Position implication:** cushion/size (references leg 6 of `danh-gia-truoc-bctc`), NO direct buy/sell recommendation.

## Examples

**Example 1 (live 02-10-2026, don't fabricate new numbers):**
Input: Xung đột ảnh hưởng dầu/vàng
Output: `geo_intel("Vietnam")` returns articles · `event_stats("vietnam")` articles >0 · gold 4,195 USD/oz same session → verdict covers all 5 items, with latest-session oil/gold numbers.
---

## 5 · danh-gia-truoc-bctc
> File thật: `OpenTrading/skills/danh-gia-truoc-bctc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-truoc-bctc
description: Grade A/B/C for 1 ticker's setup on the eve of an earnings report from 6 legs (announcement date, trend, manipulation, expectations, positioning, valuation cushion). Always use this skill when the earnings report is not out yet and the user asks whether to buy/hold through it — e.g. "FPT sắp ra báo cáo có nên mua", "setup HPG trước BCTC ra sao" — even when the user doesn't explicitly say they want a "đánh giá setup".
activation: auto
requires_tools: [mcp__opentrading__company_events]
tool_budget: 10
triggers:
  keywords: [trước bctc, sắp ra báo cáo, pre earnings, công bố lợi nhuận, setup bctc]
version: 1.2.0
```


# Grading Pre-Earnings Setup

Grade the pre-earnings setup. No income-statement forecasting — never give forecast revenue/profit numbers. If the earnings report is already out, stop immediately and switch to `co-ban-chuyen-sau`; don't force a grade. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the earnings report is not out yet and the user asks about the pre-earnings setup (`FPT sắp ra báo cáo`, `đánh giá setup HPG trước BCTC`, `pre-earnings`).
- When NOT to use (use another skill instead):
  - Regular ticker analysis (not earnings-linked) → `phan-tich-chuyen-sau-1-ma`.
  - Report already published, need to read numbers/M-Score → `co-ban-chuyen-sau`.
  - One-off technical questions → `ky-thuat-chuyen-sau`.
  - One-off valuation questions → `dinh-gia-chuyen-sau`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: check the announcement date (usually not public — cross-check only, don't lock)
- [ ] Step 2: reuse trend + manipulation from co-ban-chuyen-sau
- [ ] Step 3: expectations + positioning (call directly)
- [ ] Step 4: reuse valuation cushion + grade A/B/C
```

**Step 1: Check the announcement date (cross-check only, do NOT lock a date).**

Earnings announcement dates in VN are usually NOT publicly exact (companies only flag month/quarter; `event_calendar_vn` has no earnings-date type). Run `company_events` + `news_symbol` only to cross-check announcement-schedule news if the user asks; if no clear date is found → treat the date as `unknown`, legs record accordingly and grade is capped at B (this is the default; no need to force a date).

**Step 2: Reuse trend + manipulation (don't call the source tools).**

LOAD `co-ban-chuyen-sau` (call `load_skill` with the skill name ONLY — there is no side file `aspect=...`; aspects are sections inside the body; loading a foreign file will fail). After loading: use the "Growth quality" (trend) + "M-Score + F-score" (manipulation) legs from that skill's body. Reason to reuse instead of calling `financial_detail`/`stock_forensic` directly: avoid stacking calls to the same source of numbers within 1 run. Mark the reuse on each leg.

**Step 3: Expectations + positioning (call directly).**

Run `planned_targets` + `analyst_consensus` + `news_symbol` + `sentiment_score` (anchor = the company plan because VN has no consensus EPS; sentiment is a heuristic and doesn't count as a green leg) and `insider_trading` + `money_flow` + `block_trades`. `planned_targets` returns REAL numbers from Vietstock CTKH (chain verified live) but is session-gated: Render/no session → `unavailable` — record honestly "missing plan anchor"; never fabricate plan numbers.

**Step 4: Reuse valuation cushion + grade.**

LOAD `dinh-gia-chuyen-sau` + run `scenario_simulate` (−5%) to get a suggested size. `scenario_simulate` is an exact LINEAR CALCULATION on the latest close price (shock × price, P/L per 1000 shares) — use it to cushion position size, it is NOT a price forecast. Don't call `valuation_run` directly here. Once 6 legs have evidence (partials included), stop — no second news/money-flow round, no 7th leg.

## Template

ALWAYS use this exact verdict structure:

1. Grade **A/B/C** (rubric: A = ≥5 green legs + complete applicable annual M-Score below −1.78 + clear plan; B = 4–5 legs; C = <4 legs or complete applicable annual M-Score above −1.78). A cutoff is a review signal, not proof of clean accounts or fraud. For null/partial/not_applicable/unsupported forensic status, mark the forensic leg unknown and the grade provisional; do not call it green or red, and do not use a partial F-score as a standard /9 score.
2. 1 evidence line/leg (6 lines, each with numbers + trend + provenance).
3. Suggested size (from `scenario_simulate` −5%).
4. Explicit unknowns (list what is still unknown).
5. 1-sentence conclusion: grade + whether to hold/buy before earnings + biggest risk.

Partial data (missing positioning or expectations) → partial verdict + unknowns. Mildly negative/positive `sentiment_score` → record it as a heuristic; don't promote it to a green/red leg.

## Examples

**Example 1 (live 02-10-2026, FPT, don't fabricate new numbers):**
Input: Đánh giá trước BCTC HPG
Output: M **−2.06** clean · F 2/6 · KH DT 61,850/75,400/**58,580** · bonus shares 10:1 ex 21-09 · sentiment heuristic −0.25 · foreign net selling · pt 0% session → grade B + 6 leg evidence + unknowns, ≤10 calls (reused legs).
---

## 6 · danh-gia-vi-mo-quoc-te
> File thật: `OpenTrading/skills/danh-gia-vi-mo-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-vi-mo-quoc-te
description: Read the US economic cycle and the global risk regime (soft/hard landing, yield curve, RISK-ON/OFF, VN-vs-global comparison). Always use this skill when the user asks about the US/global macro backdrop, employment, countries' GDP, risk regime — e.g. "kinh tế Mỹ soft landing không", "yield curve đảo chưa" — even when the user doesn't explicitly say they want a "đánh giá vĩ mô".
activation: auto
requires_tools: [mcp__opentrading__fred_series]
tool_budget: 10
triggers:
  keywords: [kinh tế mỹ, recession, suy thoái, đường cong lợi suất, yield curve, risk-on, risk-off, fed bối cảnh, kinh tế toàn cầu]
version: 1.2.0
```


# Reading US and Global Macro Regime

Go through 3 waves sequentially (each wave parallel inside): US cycle → risk regime → global confirmation. Call FRED by canonical names; if the key is missing, switch to the non-FRED branch instead of dropping the whole verdict. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks about the US cycle (soft/hard landing), the yield curve, countries' employment/GDP, the global risk regime, VN-vs-global comparison.
- When NOT to use (use another skill instead):
  - Vietnam macro in detail (GDP/CPI/XNK/SBV) → use `danh-gia-vi-mo-viet-nam`.
  - Pure Fed cut/hold/hike odds + FOMC calendar → use `du-doan-fed`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: US cycle (FRED + curve, parallel)
- [ ] Step 2: risk regime (parallel)
- [ ] Step 3: global confirmation (parallel)
- [ ] Step 4: 5-item verdict
```

**Step 1: US cycle (parallel).**

Run `fred_series` (DGS10) + `fred_series` (CPIAUCSL) + `yf_yield_curve`. NEVER use web_search/web_fetch before calling the specialized tools — web only supplements after FRED numbers exist. FRED missing key → returns unavailable → switch to the non-FRED branch (use `yf_yield_curve` + `yf_global_indices`) + note honestly which series are missing. If the curve is flaky, retry at most 1 time after backoff then drop it.

**Step 2: Risk regime (parallel, sequential after Step 1).**

Run `yf_regime_assets` + `assets_rotation` + `world_macro_country` (VN/CHINA per the question). The `yf_*` group is capped at 3 calls/wave; don't stack `yf_yield_curve` + `fred_series` for more than 1 round. If `world_macro_country` comes back empty, swap the country code once then accept "thin coverage".

**Step 3: Global confirmation (parallel, sequential after Step 2).**

Run `yf_global_indices` + `yf_commodities` + `world_fear_greed`. Only proceed past Step 1 if DGS10 + CPI + curve are in; calling ≥3 FRED series at once is a sprawl signal → stop.

## Template

ALWAYS use this exact verdict structure:

1. **US cycle:** soft/hard landing, based on DGS10 + CPI + curve, unit % yield + % CPI + URL.
2. **Curve:** inverted or not, 10Y-2Y spread (unit bps/%) + URL.
3. **Global regime:** RISK-ON/OFF from rotation/regime assets + URL.
4. **VN-vs-global:** mandatory 1-line comparison of VN GDP (unit % WorldBank) vs global + URL.
5. **Variables to watch:** list US CPI, jobs, yields to watch next.

## Examples

**Example 1 (live 02-10-2026, don't fabricate new numbers):**
Input: Kinh tế Mỹ hiện tại
Output: US10Y 5.24% / 2Y 4.61%, not inverted · WorldBank GDP VN 8.02% · fear/greed crypto 70-74 (greedy) → verdict covers all 5 items, curve + ≥2 FRED series have numbers.
---

## 7 · danh-gia-vi-mo-viet-nam
> File thật: `OpenTrading/skills/danh-gia-vi-mo-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: danh-gia-vi-mo-viet-nam
description: Read Vietnam macro (GDP, CPI, trade, USDVND rate, SBV rates, market-driving narrative + event calendar). Always use this skill when the user asks for VN macro numbers, context or release calendar — e.g. "GDP quý này bao nhiêu", "lãi suất SBV bao nhiêu" — even when the user doesn't explicitly say they want a "đánh giá vĩ mô".
activation: auto
requires_tools: [mcp__opentrading__vs_indicator_data]
tool_budget: 12
triggers:
  keywords: [vĩ mô, GDP, CPI, lạm phát, xuất khẩu, nhập khẩu, lãi suất điều hành, sbv, xnk, cán cân, câu chuyện thị trường, dẫn dắt]
version: 1.3.0
```


# Reading Vietnam Macro

Always open with the mandatory 2-call pre-flight (source_status + vs_auth_status) because VN macro depends on JWT and HAR-sessions that die easily. The category/termType pairs must be exactly right (wrong = empty rows): GDP 73/tt3, CPI 15/tt7/sub2, XK 38/tt2. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks for VN numbers (GDP/CPI/XK/NK), SBV rates, USDVND rate in macro context, the NSO release calendar, broker macro reports, the VN market-driving narrative.
- When NOT to use (use another skill instead):
  - US/global macro, Fed context, risk regime → use `danh-gia-vi-mo-quoc-te`.
  - Pure Fed cut/hold odds → use `du-doan-fed`.
  - Detailed gold-FX play → use `phan-tich-vang-ty-gia`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 0: source pre-flight (parallel)
- [ ] Step 1: mandatory VN data (categories first, indicators parallel)
- [ ] Step 2: macro news (parallel)
- [ ] Step 3: broker reports (1 shared-feed call)
- [ ] Step 4: supplementary data + event calendar
- [ ] Step 5: 6-item verdict + narrative
```

**Step 0: Pre-flight (parallel, mandatory).**

Run `source_status` + `vs_auth_status` before every wave.

**Step 1: Mandatory VN data.**

Run `vs_categories` first (look up ids if unsure), then in parallel `vs_indicator_data` GDP + CPI + XK and `vs_xnk_detail` (only 1 direction, xk or nk, per the question). Empty rows → recheck the id pair, retry at most 1 time → if still empty, record "no data for this period".

**Step 2: Macro news (parallel).**

Run `news_market` (filter macro/rates/FX) + `macro_events_vn` + `economic_calendar`.

**Step 3: Broker reports (1 call only).**

Run `analyst_consensus` (report_type=macro, limit=30) as one shared feed; take section pointers + dated reports. Don't fire per keyword.

**Step 4: Supplementary data + calendar (parallel, at most 1 call each).**

Run `snapshot_history` (macro_curated) + `yf_yield_curve` + `sbv_rates` + `vn_retail_fx` + `macro_events_vn` (NSO) + the Fed/US meeting (cross-ref `du-doan-fed`). Missing HAR session → macro returns a permission message: record honestly "macro needs session", fall back to `snapshot_history`; never interpret the permission message as data. Curve/DXY flaky → retry 1 time after backoff then drop.

## Template

ALWAYS use this exact verdict structure:

1. **Growth:** GDP, ≥8 latest points, unit % yoy + URL/provenance.
2. **Inflation:** CPI, ≥8 latest points, unit % yoy + URL.
3. **Trade:** XK/NK/XNK-detail, unit million USD + URL.
4. **Exchange rate:** USDVND (unit VND), SBV rates (refinancing/re-discount, unit %) + URL.
5. **Rates:** SBV policy rate + foreign-capital-flow context (curve/DXY) + URL.
6. **Points Tích cực / Tiêu cực + future outlook.**
7. **Market-driving narrative + event calendar** (per narrative: which event, what date, what impact).

## Examples

**Example 1 (live 02-10-2026, don't fabricate new numbers):**
Input: Vĩ mô VN
Output: GDP 504 rows up to Q2/2026 · CPI 1,839 · XK 2,941 · XNK-country 3,675 · SBV refinancing 4.5% / re-discount 3% · USDVND 25,970 · NSO CPI calendar for August → verdict covers all 6 items + market-driving narrative with event calendar, ≤12 calls.
---

## 8 · devil-advocate
> File thật: `OpenTrading/skills/devil-advocate/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: devil-advocate
description: "Counter investment theses to fight confirmation bias: summarize the thesis, give 3-5 reasons it could be WRONG with tracking signs and falsification conditions. Always use this skill when the user asks about a stock they hold or like, asks for a buy/hold opinion, or requests a counter-argument/bear case — e.g. 'đang giữ HPG có nên giữ không', 'bear case cho VCB là gì' — even when the user doesn't explicitly say they want a 'phản biện' (counter-argument)."
activation: auto
triggers:
  keywords: [phản biện, bear case, có nên giữ, rủi ro gì, đang nắm, đang giữ]
version: 1.3.0
```


# Countering Investment Bias

When users ask about a stock they bought or like, assume confirmation bias — the job is to counter the thesis, not to mock it or conclude on their behalf. Neutral tone, no sarcasm. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user says they hold a stock, asks whether to keep holding, asks what the risks are, asks for a bear case, or requests a counter-argument on a buy/hold thesis.
- When NOT to use (use another skill instead): term definitions (use `explain-term`); charts/candles (use `ve-bieu-do-ky-thuat`); exchange/session/margin mechanics (use `vn-market-basics`).

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 1: summarize the thesis (confirm correct understanding)
- [ ] Step 2: 3-5 reasons it could be WRONG + tracking signs
- [ ] Step 3: falsification conditions
```

**Step 1: Summarize the thesis in 1–2 sentences.**

Confirm correct understanding before countering; never distort the thesis to make it easier to attack.

**Step 2: List the 3–5 strongest reasons the thesis could be WRONG.**

Cover 5 angles: industry, company, valuation, macro, liquidity. Each reason gets 1 concrete sign to track (which indicator/event shows the risk materializing) — a counter-argument without a tracking sign is vague and useless.

**Step 3: State falsification conditions.**

Which event, if it happens, means the thesis should be dropped. Never conclude buy/sell on the user's behalf.

## Template

ALWAYS use this exact output structure: summarized thesis (1–2 sentences) · 3–5 risks + a tracking sign for each · falsification conditions (when to drop the thesis).

## Examples

**Example 1:**
Input: đang giữ HPG, có nên giữ không
Output: 1–2 sentence summary + 3–5 risks each with a tracking sign + falsification conditions, neutral tone, no buy/sell recommendation.

**Anti-pattern (never do this):** only praising along with the user to confirm the bias; concluding "nên bán" on your own.
---

## 9 · dinh-gia-chuyen-sau
> File thật: `OpenTrading/skills/dinh-gia-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: dinh-gia-chuyen-sau
description: "Compute the fair-value range and UPSIDE/DOWNSIDE % for one stock (PER/PB, vs 2-3 year history). Always use this skill when the user asks whether a stock is expensive or cheap, what the fair value is, how much upside is left — e.g. 'FPT đắt chưa', 'VCB fair value' — even when the user doesn't explicitly say they want 'định giá' (valuation)."
activation: auto
requires_tools: [mcp__opentrading__valuation_run]
tool_budget: 7
triggers:
  keywords: [định giá, fair value, dcf, per, đắt hay rẻ, upside, giá mục tiêu tự tính, valuation]
version: 1.2.0
```


# Valuing Single-Stock Fair Value

Return exactly 6 items: price vs fair range → PER/PB vs history → why cheap/expensive → UPSIDE/DOWNSIDE % → broker-target anchor → 1-sentence verdict. Negative EPS (loss-making company) makes per_pb meaningless — say outright that there is no basis for valuation instead of fabricating a fair value. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks for valuation of one stock (`FPT đắt chưa`, `VCB fair value`, `định giá theo PER`, `upside còn bao nhiêu`).
- When NOT to use (use another skill instead):
  - Comparing multiple stocks → `so-sanh-cung-nganh`.
  - Pure fundamentals (financial statements, M-Score, ownership) → `co-ban-chuyen-sau`.
  - Pure technicals → `ky-thuat-chuyen-sau`.
  - Broker target prices (aggregating existing reports) → `tim-co-hoi-bao-cao-ctck` (cross-ref only to anchor expectations; does not replace self-computed valuation).

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 1: core fair value (parallel)
- [ ] Step 2: history anchor (parallel)
- [ ] Step 3: rate context (bank/PB-heavy only)
- [ ] Step 4: verdict, 6 items
```

**Step 1: Core fair value (parallel, call directly).**

Run `valuation_run` (symbol, method defaults to auto — only change method if the user insists) + `vs_overview_trading` (symbol).

**Step 2: History anchor (parallel, call directly).**

Run `financial_ratios` (symbol) + `vn_quote_history` (symbol, days=365), compute the 2–3 year average PER/PB yourself. If price history is missing, drop the history comparison, verdict partial + note the gap.

**Step 3: Rate context (only when needed).**

Run `yf_yield_curve` + `vs_trading_info` for PB-heavy stocks (banks). If you already have fair value + history comparison, stop — do not open Step 3 to pad the answer. One `method` per run; a `method` outside the enum → warning → fall back to auto, no retry with exotic methods.

**Step 4: Validate before finalizing.**

Never rebuild the DCF yourself (already computed in `valuation_run`). Never call `signals_technical` / `financial_detail` / `stock_forensic` here; for fundamentals quality, cross-ref `co-ban-chuyen-sau` without re-calling that skill's tools. For banks prefer per_pb and state the reason.

## Template

ALWAYS use this exact verdict structure, each item with numbers + trend + provenance:

1. Current price vs fair range: which method leads, gap in % (`provenance: valuation_run` + `vs_overview_trading`).
2. Current PER/PB vs self-computed 2–3 year average (`provenance: financial_ratios` + `vn_quote_history`).
3. Why cheap/expensive: growth + quality (cross-ref `co-ban-chuyen-sau`) + rates.
4. UPSIDE/DOWNSIDE % + confidence (high if the 2 methods agree).
5. Expectation anchor line: upside per broker targets (`provenance: tim-co-hoi-bao-cao-ctck` cross-ref, reference only).
6. 1-sentence verdict: ĐẮT/HỢP LÝ/RẺ + UPSIDE/DOWNSIDE %.

## Examples

**Example 1 (live 02-10-2026, no fabricated numbers):**
Input: FPT đắt chưa
Output: VCB per_pb @57,400 (2 methods agree) · FPT per_pb @62,700 · US10Y 5.24% context · overview_trading VCB PE/PB/ROEA complete → UPSIDE % + history comparison, 2 lines, ≤7 calls.
---

## 10 · du-doan-fed
> File thật: `OpenTrading/skills/du-doan-fed/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: du-doan-fed
description: Read next-meeting Fed rate probabilities and scenarios (cut/hold/hike) with the yield curve, FOMC calendar and implications for VN. Always use this skill when the user asks about Fed, FOMC, dot plot or US rate odds — e.g. "Fed tháng tới cắt hay giữ", "dot plot mới nhất" — even when the user doesn't explicitly say they want a "dự đoán Fed" (Fed forecast).
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 8
triggers:
  keywords: [fed, fomc, cắt giảm lãi suất, dot plot, xác suất fed, lãi suất mỹ]
version: 1.2.0
```


# Reading the Next Fed Decision

Return exactly 5 items: probability per scenario → curve → FOMC calendar → variables to watch → VN implications. Drill only the 1 main Fed event (latest slug, already sorted by vol24h) — never fire 5 query variants. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks about the next Fed decision (cut/hold/hike), FOMC, dot plot, or odds probabilities + curve + VN implications.
- When NOT to use (use another skill instead):
  - General US macro context (cycle, jobs, risk regime) without odds → use `danh-gia-vi-mo-quoc-te`.
  - Odds on non-Fed topics (elections, BTC...) → use `du-doan-polymarket`.
  - Broad political-risk map → use `danh-gia-tinh-hinh-chinh-tri-toan-cau`.

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 1: Fed odds (1 call, take the top event)
- [ ] Step 2: drill-down + macro (parallel)
- [ ] Step 3: curve + verify official source
- [ ] Step 4: verdict, 5 items
```

**Step 1: Fed odds (mandatory).**

Run `world_prediction_odds` (query=fed). Probabilities for ≥2 scenarios + meeting dates are enough for a verdict; Step 3 afterwards is only for verification.

**Step 2: Drill-down + macro (parallel, after Step 1).**

Run `polymarket_event` (slug fed-decision-*) + `fred_series` (DGS10, add EFFR/DFII if needed). Never drill more than 1 Fed slug per run.

**Step 3: Curve + verification (parallel, after Step 2).**

Run `yf_yield_curve` + `web_fetch` (only the statement/official fed.gov source cited in the odds).

**Step 4: Validate before finalizing.**

Stale odds (end-date passed) → filter `end > today`, drop expired events, retry once with a fresh fed query. If Gamma is down on both proxy + direct, state clearly "không có odds" (no odds available) — never substitute your own opinion. Flaky curve → retry at most once after backoff, then drop with a note that the curve is missing. `fred_series`: at most 3 series beyond the Fed ones, then stop.

## Template

ALWAYS use this exact verdict structure:

1. **Probability per scenario:** cut/hold/hike, each with prob_pct (unit %) + volume (USD) + end-date + event URL.
2. **Implied curve:** US10Y/2Y (unit %) + whether inverted or not + URL.
3. **Next FOMC date:** meeting day (unit day/month) + fed.gov source URL.
4. **Variables to watch:** US CPI, jobs, unit %/K jobs + URL.
5. **Implications for VN:** FX/rates, 1–2 lines + URL.

## Examples

**Example 1 (live 02-10-2026, no fabricated numbers):**
Input: Fed tháng tới
Output: "Fed Decision in October 2026": Yes(no change) 74.5% / No 25.5%, volume24h 2.6M · curve US10Y 5.24% not inverted → probabilities for ≥2 scenarios + meeting dates + 1 line of VN implications.
---

## 11 · du-doan-polymarket
> File thật: `OpenTrading/skills/du-doan-polymarket/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: du-doan-polymarket
description: Read Polymarket odds by topic (event table + prob_pct + volume + liquidity/end-date trust flags). Always use this skill when the user asks about odds/probabilities, which markets are hot, or "bao giờ X" (when will X happen) — e.g. "odds bầu cử Mỹ", "BTC bao giờ chạm 100k" — even when the user doesn't explicitly say they want "xem Polymarket" (Polymarket odds). Do not use for Fed specifically (use du-doan-fed).
activation: auto
requires_tools: [mcp__opentrading__world_prediction_odds]
tool_budget: 6
triggers:
  keywords: [polymarket, odds, xác suất, prediction market, bao giờ bitcoin, cá cược sự kiện]
version: 1.2.0
```


# Reading Polymarket Odds

Return an event table with prob_pct + volume + liquidity + end-date, every row carrying both trust flags. At most 2 events drilled per run — the user picks, never open the whole top-10 yourself. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks for Polymarket odds/probabilities by topic (economy, elections, crypto...), "market nào đang nóng" (which markets are hot), or drill-down of 1–2 events.
- When NOT to use (use another skill instead):
  - Fed specifically (needs curve + FOMC + VN implications) → use `du-doan-fed`.
  - Broad political map combining odds + GDELT news → use `danh-gia-tinh-hinh-chinh-tri-toan-cau`.

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 1: scan odds (1 call, take the top sorted by vol24h)
- [ ] Step 2: drill down into the events the user cares about (max 2)
- [ ] Step 3: table + flags + 1-sentence conclusion
```

**Step 1: Scan odds (mandatory).**

Run `world_prediction_odds` (query or tag, limit=10). Empty query → switch to tag at most once, then conclude "không có market cho chủ đề" (no market for this topic). If the user only asked "đang nóng gì" (what's hot) and Wave 1 already has ≥5 events, stop — no drill-down.

**Step 2: Drill-down (after Step 1, max 2).**

Run `polymarket_event` for the slug the user cares about (drill full outcomes); a second event only if the user asks explicitly. Never run Step 2 + 3 in parallel.

**Step 3: Validate before finalizing.**

Wrong/nonexistent slug → switch to the next top slug once, then note "không drill được event X" (could not drill event X). Slow Jina proxy → the tool falls back to direct by itself (see warnings), wait once, no rapid-fire retries. Gamma down on both paths → state clearly "không có odds" (no odds available), never fabricate probabilities.

## Template

ALWAYS use this exact verdict structure:

1. **Event table:** each row {title · prob_pct per outcome (unit %) · volume24h (USD) · liquidity (USD) · end-date (day) · event URL}.
2. **Mandatory trust flags on every row:** (1) low liquidity (<50k USD) → "odds kém tin" (low-trust odds); (2) end-date passed → LOẠI from the table.
3. **Conclusion:** 1 sentence "thị trường đặt cược X với xác suất Y" (unit %).
4. **Provenance:** every row requires the event URL.

## Examples

**Example 1 (live 02-10-2026, no fabricated numbers):**
Input: Polymarket đang nóng gì về kinh tế
Output: Fed T10/2026 no-change 74.5% (vol 2.6M) · Brazil presidential detail OK · sort vol24h active → ≥5 events + trust flags on every row.
---

## 12 · explain-term
> File thật: `OpenTrading/skills/explain-term/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: explain-term
description: "Explain securities terms (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2) in simple Vietnamese: 1-sentence definition + formula in words + hypothetical example + common pitfalls. Always use this skill when the user asks what an indicator or concept is — even when the question is only 2-3 words like 'P/E là gì'."
activation: auto
triggers:
  keywords: [là gì, nghĩa là gì, giải thích, khái niệm, thuật ngữ]
version: 1.3.0
```


# Explaining Securities Terms Simply

Answer in exactly 5 steps, keep it lean, never drift into stock analysis or recommendations. All illustrative numbers are rounded hypotheticals — always label them "ví dụ giả định" (hypothetical example), never let the user mistake them for real figures. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks what a term, indicator or concept is (P/E, EPS, ROE, margin, ATO/ATC, room ngoại, T+2...).
- When NOT to use (use another skill instead): countering buy/hold theses (use `devil-advocate`); analyzing a specific stock (use `phan-tich-chuyen-sau-1-ma`); drawing charts (use `ve-bieu-do-ky-thuat`).

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 1: 1-sentence definition, simple Vietnamese
- [ ] Step 2: formula in words (if any)
- [ ] Step 3: hypothetical example (clearly labeled)
- [ ] Step 4: how it works in VN + 1 common pitfall
- [ ] Step 5: 1 open-ended question
```

**Step 1–2: Definition + formula.**

Definition in one sentence, no other unexplained jargon. Formula written in words, never swap in real numbers.

**Step 3: Illustrative example.**

Rounded hypothetical numbers, always labeled "ví dụ giả định".

**Step 4: Real-world usage in VN + 1 common pitfall.**

Examples: deceptively low P/E from one-off profits, margin call, locked foreign room.

**Step 5: End with 1 open-ended question.**

Helps the user dig deeper (e.g. "bạn muốn xem P/E này so với ngành không?"). Explain only 1 term per turn.

## Template

ALWAYS use this exact output structure: 1-sentence definition · formula in words · hypothetical example (clearly labeled as such) · VN usage + common pitfall · 1 open-ended question.

## Examples

**Example 1:**
Input: P/E là gì
Output: 1-sentence definition + formula in words + clearly-labeled hypothetical example + VN pitfall + 1 open-ended question.

**Anti-pattern (never do this):** defining with harder jargon; forgetting the "ví dụ giả định" label so the user mistakes numbers for real ones; answering like a textbook chapter.
---

## 13 · kiem-chien-luoc-backtest
> File thật: `OpenTrading/skills/kiem-chien-luoc-backtest/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: kiem-chien-luoc-backtest
description: Verify trading strategies with backtest code (SMA cross, RSI oversold, momentum, param sweep with best AND worst, monthly seasonality, post-Tết/dividend, oil/gold price rules). Always use this skill when the user asks whether a strategy works or which month/quarter tends to rise — e.g. "SMA20/50 FPT có ăn không", "mua RSI<30 có thắng không" — even when the user doesn't explicitly say they want a "backtest".
activation: auto
requires_tools: [mcp__opentrading__quant_backtest]
tool_budget: 12
triggers:
  keywords: [backtest, kiểm chứng, chiến lược, sma cross, rsi dưới, quá bán, momentum chiến lược, param sweep, mùa vụ tháng, sau tết, sau chia cổ tức, theo giá dầu, theo giá vàng]
version: 1.3.0
```


# Backtesting Trading Strategies Honestly

Standard pipeline per run: baseline → strategy → sweep → seasonality/event → conclusion. Best must always come with worst (anti-overfit); missing worst or missing engine caveat means not done. Engine is numpy-only, default cost, VN T+2 not modeled — every conclusion carries this caveat. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: verifying technical conditions (SMA/momentum/RSI), time conditions (month/quarter), post-event conditions (Tết/dividend/AGM), commodity-price conditions (oil/gold).
- When NOT to use (use another skill instead): specific position sizing → the Đệm (cushion) leg in `danh-gia-truoc-bctc`; valuation → `dinh-gia-chuyen-sau`; news/sentiment → `tim-kiem-tin-tuc` / `phan-tich-sentiment`.

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 1: data + benchmark (1 symbol at a time)
- [ ] Step 2: technical conditions
- [ ] Step 3: time conditions
- [ ] Step 4: post-event conditions
- [ ] Step 5: commodity-price conditions
- [ ] Step 6: sweep + best/worst synthesis
```

**Step 1: Data (first, sequential).**

Run `vn_quote_history` (stock) or `dnse_ohlc_history` (futures/index) + `vn_index_ohlcv` (benchmark). Only 1 symbol per sweep. For VN stocks use equity candles — NEVER use `vn_crypto_ohlcv`.

**Step 2: Technical conditions.**

Run `backtest_strategies` (strategy=sma_cross/momentum/**rsi_meanrev** + rsi_low/rsi_high). rsi_meanrev: buy RSI<30, exit RSI>70. `quant_backtest` is deprecated for strategies (baseline buy-hold only) — all timing-rule comparisons go through `backtest_strategies`; never call `quant_backtest` in this step.

**Step 3: Time conditions.**

Run `backtest_strategies` + `months`/`quarters` + `seasonality` (describes month/quarter). Entries only in the selected periods, exits always open. Months=[1] on a March candle → 0 trades + warning is valid, no retry with a different timeframe.

**Step 4: Post-event conditions.**

Run `event_study` (symbol, dates, window ±N) — CAR around Tết/dividend/AGM, dates from `event_calendar_vn`, nearest-day 3 sessions, with hit-rate/best-worst.

**Step 5: Commodity-price conditions.**

Run `backtest_strategies` + `condition_symbol` (BZ=F/GC=F...) + `condition_rule` above_sma/rising. If `condition_symbol` is down the whole call is unavailable — say so clearly, never substitute another symbol. The vnstock→yfinance fallback is inside the tool; never switch sources manually.

**Step 6: Synthesis.**

Run `param_sweep` (max 30 available combos, never widen it yourself; passthrough months/quarters) + `correlation_matrix` + `portfolio_optimize` (multiple stocks). Never sweep more than 3 symbols per run.

## Template

ALWAYS use this exact verdict structure: baseline buy-hold → each condition (trades/net/win) → best param + worst param → seasonality/event bias → verdict "đáng tin / đáng nghi" (trustworthy / questionable) + reason + engine caveat (numpy-only, default cost, T+2 not modeled) + provenance (candle source, benchmark, event dates).

## Examples

**Example 1 (live 02-10-2026, no fabricated numbers):**
Input: Backtest mua RSI<30 FPT + backtest sau Tết
Output: VCB buy-hold −4.9% gross · sma_cross 7 trades −10.4% · sweep best **+3.7%** · seasonality January mean +4.67% · rsi_meanrev VCB 1 trade · months=[1] on a March candle → 0 trades + warning · event_study VCB 2026-09-21: CAR +0.25% → table of each condition (trades/net/win) + best/worst + verdict, with T+2/cost caveat.
---

## 14 · kiem-tra-nguon-du-lieu
> File thật: `OpenTrading/skills/kiem-tra-nguon-du-lieu/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: kiem-tra-nguon-du-lieu
description: Sweep the health of all upstreams in one pass (status table per source + recommendation of which skills can run). Always use this skill when the user asks whether sources are alive, wants a pre-session check, or when other skills report mass unavailability — e.g. "Vietstock chết chưa", "sáng nay data có đủ không" — even when the user doesn't explicitly say they want a "check nguồn" (source check).
activation: manual
requires_tools: [mcp__opentrading__doctor]
tool_budget: 12
triggers:
  keywords: [check nguồn, kiểm tra nguồn, server sống không, vietstock chết, data có đủ không, health check, nguồn dữ liệu]
version: 1.2.0
```


# Checking Data-Source Health

Return a status table for 9 sources + 1 recommendation line on which skills can run. Smoke here means ping (smallest limit/days), not real data pulls. This skill does no market analysis. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks whether the server is alive, whether Vietstock is down, whether there is enough data this morning, wants a pre-session source check, or when other skills report mass unavailability.
- When NOT to use (use another skill instead): stock/market analysis (use `phan-tich-chuyen-sau-1-ma`, `ky-thuat-chuyen-sau`).

## Workflow

Copy the checklist and tick off as you progress:

```
Task Progress:
- [ ] Step 0: doctor local
- [ ] Step 1: upstream overview + JWT (parallel)
- [ ] Step 2: smoke each upstream (smallest limit/days)
- [ ] Step 3: verdict table + recommendation
```

**Step 0: Doctor.**

Run `doctor` (env keys + local versions).

**Step 1: Overview (parallel).**

Run `source_status` + `vs_auth_status`: upstream overview + JWT expiry.

**Step 2: Smoke each upstream (parallel, smallest limit/days).**

`vn_quote_history` (VCB, days=5) · `vs_market_index` · `dnse_latest_trade` (VN30F1M) · `yf_market_pins` · `crypto_spot` (BTCUSDT), then `news_market` (limit=1) · `fred_series` (DGS10, limit=1) · `world_prediction_odds` (limit=1) · `sbv_rates`. Retry at most once per upstream. For Vietstock accounts logged in via Google, the password fallback is rejected ("đăng nhập bằng Google!") — must re-login via Google + export a fresh HAR/cookie.

**Step 3: Validate before finalizing.**

This skill itself can be partial (1–2 sources down) — still produce the full table, mark dead sources in red.

## Template

ALWAYS use this exact verdict structure — table {Nguồn · Trạng thái · Độ trễ · Skills ảnh hưởng nếu chết} covering all 9 sources: vnstock (ok/throttle/down) · Vietstock JWT (còn hạn tới.../HẾT) · Vietstock HAR-session (sống/chết) · DNSE (ok/lạnh) · yfinance/Binance/GDELT/Fireant/Gamma/FRED/SBV + 1 recommendation line ("sáng nay đủ data chạy ..." or "chỉ chạy legs không-Vietstock").

## Examples

**Example 1 (live 02-10-2026, no fabricated numbers):**
Input: check nguồn trước phiên
Output: JWT expiry incident at 19:15 caught in Step 1 (`vs_auth_status` false) before other skills fail en masse; HAR-session alive independently (macro still available while JWT is dead) → full 9-source table + recommendation, ≤12 calls, ≤3 minutes.
---

## 15 · ky-thuat-chuyen-sau
> File thật: `OpenTrading/skills/ky-thuat-chuyen-sau/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: ky-thuat-chuyen-sau
description: Pure single-stock multi-timeframe technical read 1D/1W/1M (RSI/MACD/BB/Ichimoku/ADX, Elliott/Wyckoff, support-resistance, higher-high or lower-low). Always use this skill when the user asks about technicals, breakouts, reading the price band, Elliott waves or HH/LL of a stock — e.g. "VCB kỹ thuật sao", "FPT có breakout không" — even when the user doesn't say explicitly they want "phân tích kỹ thuật".
activation: auto
requires_tools: [mcp__opentrading__signals_technical]
tool_budget: 8
triggers:
  keywords: [kỹ thuật, rsi, macd, bb, bollinger, ichimoku, elliott, wyckoff, hỗ trợ, kháng cự, breakout, pattern, orderbook, băng giá, chỉ báo, adx, ema, sma, higher high, lower low, đa khung]
version: 1.3.0
```


# Reading Single-Stock Technicals

Default 2 timeframes (1D+1W); 1M only when the user asks long-term. One `signals_technical` call already covers 80% of the verdict — this is the model "1 pillar tool" skill, don't add more tools just for extra numbers. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks about 1 stock's technicals (`VCB kỹ thuật đa khung sao`, `FPT có breakout không`, `đọc băng HPG`, `higher-high hay lower-low`, `sóng Elliott`).
- When NOT to use (use a different skill instead):
  - Financial statements/fundamentals/M-Score → `co-ban-chuyen-sau`.
  - Valuation/fair value/PER/upside → `dinh-gia-chuyen-sau`.
  - Full single-stock analysis → `phan-tich-chuyen-sau-1-ma` (that skill dispatches this one).
  - Comparing multiple stocks → `so-sanh-cung-nganh`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: multi-timeframe candles (1 call per timeframe)
- [ ] Step 2: read wave structure from Step 1 output (no new tool calls)
- [ ] Step 3: confirm per the question (max 3 calls)
- [ ] Step 4: per-timeframe verdict + synthesis
```

**Step 1: Multi-timeframe candles.**

Run `signals_technical` (symbol, interval=1D) + (interval=1W) [+ (interval=1M) if long-term]. One call per timeframe: RSI/MACD/BB/Ichimoku/S-R/patterns. Interval only accepts 1D/1W/1M (1W needs ≥30 bars, 1M ≥24 bars); unknown interval → `unavailable`, no retry.

**Step 2: Read wave structure (no new tool calls).**

From the Step 1 output read swings + swing_trend + fib + elliott + wyckoff; label yourself HH/HL/LH/LL + 7 Fibonacci levels + Elliott (impulse/corrective/developing + invalidation) + Wyckoff phase.

**Step 3: Confirm per the question (max 3 calls).**

Only call when the user asks about: `pattern_match` (historical analogy) · `dnse_latest_trade` / `dnse_orderbook` / `vn_trades` (intraday) · `vn_index_ohlcv` (index trend). Do NOT call `financial_detail` / `valuation_run` / `stock_forensic` here.

**Step 4: Validate before finalizing.**

New stock <60 candles → indicators null → report "thiếu lịch sử", never fabricate RSI/MACD. DNSE session ended → empty orderbook is correct data, state the closed session. `pattern_match` corr <0.4 = no reliable analogy → report it honestly. Prices come as kVND (`signals_technical.last 57.3` = 57,300đ) → conversion mandatory + state the unit. Any missing timeframe → partial verdict for the remaining timeframes + note which are missing. Elliott/Wyckoff are heuristics → confidence + invalidation mandatory.

## Template

ALWAYS use this exact verdict structure, for EACH timeframe (1D/1W[/1M]), every item with numbers + trend + provenance:

1. Trend: SMA stack + ADX. 2. Momentum: RSI/MACD/stoch/CCI per indicator. 3. S-R of that timeframe. 4. Structure: HH/HL/LH/LL + Fibo + Elliott pattern/invalidation + Wyckoff phase + confidence. 5. Timeframe conclusion: higher-high or lower-low. 6. Synthesis: multi-timeframe consensus or divergence + price trigger → timing MUA/CHỜ/BÁN. 7. One-sentence conclusion for the whole stock.

## Examples

**Example 1 (live 02-10-2026, no new fabricated numbers):**
Input: FPT kỹ thuật 1D+1W
Output: VCB — RSI 39.2, ADX 12.1 (trend yếu), MACD −0.31/−0.13, EMA10 58.09, pos_52w 0.21 · HPG pattern best_corr 0.409 (yếu — state honestly) · VCB 1W bearish/lower-low/fib-down consistent → 2-timeframe verdict + HH/LL + Ichimoku signal, ≤8 calls.
---

## 16 · nhip-dap-crypto
> File thật: `OpenTrading/skills/nhip-dap-crypto/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: nhip-dap-crypto
description: "Crypto pulse in plain language for non-experts: price trend, whether leverage funding/OI is heating up, fear/greed, VND-converted price. Always use this skill when the user asks how BTC/ETH/SOL is doing, whether crypto is up or down, funding rate, whether they should care about crypto — even when the user doesn't say explicitly they want 'phân tích crypto'."
activation: auto
requires_tools: [mcp__opentrading__crypto_spot]
tool_budget: 6
triggers:
  keywords: [btc, bitcoin, eth, ethereum, crypto, tiền số, tiền ảo, funding]
version: 1.3.0
```


# Reading Crypto Pulse in Plain Language

Written for people who aren't crypto experts: every term must be explained in 1 line alongside its number. Answer in exactly 3 sentences. Crypto runs 24/7 so "today" numbers differ from VN stock sessions — don't compare across mismatched sessions. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks how BTC/ETH/SOL is doing, whether crypto is up or down, what funding/OI says, crypto price converted to VND, how crypto links to VN stocks.
- When NOT to use (use a different skill instead): global macro regime context (only `danh-gia-vi-mo-quoc-te`); crypto event probability odds (only `du-doan-polymarket`); gold/FX analysis (only `phan-tich-vang-ty-gia`).

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: spot prices (max 3 coins)
- [ ] Step 2: derivatives leverage
- [ ] Step 3: sentiment + VND price
- [ ] Step 4: 3-sentence verdict
```

**Step 1: Spot prices.**

Run `crypto_spot` (BTC ETH SOL — max 3 coins/wave 1). Price + % 24h = "tăng/giảm bao nhiêu hôm nay". NEVER use `vn_crypto_ohlcv` as a substitute (VND-converted price ≠ real USD price) — that tool is only for Step 3 when the user asks the VND price.

**Step 2: Derivatives leverage.**

Run `crypto_derivs` (BTC ETH). Explain alongside the numbers: funding rate = "phe mua đang trả tiền cho phe bán (dương = đám đông cược lên)"; OI = "tổng tiền đang cược"; long/short = "bên nào đông hơn"; high funding + high OI = hot leverage, prone to reversal. Funding/OI empty because Binance geo-blocks the Singapore worker → write "không lấy được do giới hạn vùng", don't conclude the market is dead.

**Step 3: Sentiment + VND price.**

Run `world_fear_greed` + `vn_crypto_ohlcv` (VND-conversion path). Only drill into Polymarket crypto when the user asks probabilities; don't drift into odds/event-study on your own.

## Template

ALWAYS use this exact verdict structure (exactly 3 sentences):

1. What the trend is (up/down/sideways + %). 2. Whether leverage is hot (high funding + high OI = prone to reversal). 3. What it links to for VN (VND price + rest for stocks — if none, write "độc lập").

## Examples

**Example 1 (live 02-10-2026, no new fabricated numbers):**
Input: BTC sao rồi
Output: BTC 83,476 (+0.33%) · funding 2.8e-05 (trung tính) · OI 95.7k · fear/greed 70-74 → 3-sentence answer + 0 unexplained jargon, ≤6 calls.
---

## 17 · phan-tich-chuyen-sau-1-ma
> File thật: `OpenTrading/skills/phan-tich-chuyen-sau-1-ma/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-chuyen-sau-1-ma
description: "Coordinator for full single-stock analysis in 8 steps: self-identify the stock/sector/news/events, call the specialist skills (technicals, valuation), then merge the verdict into a Tích cực/Tiêu cực/Động lực table. Always use this skill when the user asks for full analysis of one stock — e.g. 'phân tích FPT', 'VCB thế nào', 'mã này sao' — even when the user doesn't say explicitly they want 'phân tích toàn diện'."
activation: auto
requires_tools: [mcp__opentrading__stock_overview]
tool_budget: 8
triggers:
  keywords: [phân tích, phân tích cổ phiếu, phân tích mã, toàn diện, chi tiết mã, mã này sao]
version: 1.3.0
```


# Coordinating Full Single-Stock Analysis

8-step coordinator skill: do the stock + sector + news + event identification yourself, dispatch technicals/valuation to sub-skills, then merge the verdict. Budget 8 only counts this skill's own tools; sub-skill tools live in the sub-skill's budget — they don't stack. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks for full analysis of one stock (`phân tích FPT`, `VCB thế nào`, `mã này sao`).
- When NOT to use (use a different skill instead):
  - Only technicals (RSI, breakout, multi-timeframe, higher-high/lower-low) → `ky-thuat-chuyen-sau`.
  - Only financial statements/fundamentals (M-Score, shareholders, dividends) → `co-ban-chuyen-sau`.
  - Only valuation (fair value, PER, upside) → `dinh-gia-chuyen-sau`.
  - Comparing 2-6 same-sector stocks → `so-sanh-cung-nganh`.
  - Assessing the setup before earnings → `danh-gia-truoc-bctc`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: resolve the stock (disambiguate the given name)
- [ ] Step 2: sector + where the money comes from (direct calls)
- [ ] Step 2b: price chart (reuse existing candles → chart_render local, attach to verdict)
- [ ] Step 3-4: dispatch technicals + valuation to sub-skills
- [ ] Step 5-7: quarterly earnings + news + events (direct calls)
- [ ] Step 8: synthesis + lock the verdict
```

**Step 1: Resolve the stock (direct calls).**

Run `symbol_lookup` (company name) · `symbol_resolve` (multi-type symbols, ranked fallback). Ambiguous names (gold/BTC/USD) require `symbol_resolve` first. `symbol_resolve` returns multiple candidates → pick the highest rank + state clearly which name resolved to which symbol; no symbol → stop and ask, never guess. After you have the symbol: VN equities → candles/tools `vn_*`/`vs_*`; crypto → `crypto_spot` (USD, never use `vn_crypto_ohlcv` unless the VND price is asked).

**Step 2: Sector + where the money comes from (direct calls).**

Run `vn_company` · `vs_company_info` · `vs_industry_tree`. Get the GICS sector, business model, main revenue source. New stock not yet sector-classified (`vs_industry_tree` no match) → note "chưa phân loại", still run the remaining steps.

**Step 2b: Price chart (local tool, no remote budget).**

Reuse candles already in context (from Step 1 `vn_quote_history` or the technicals sub-skill) → call `chart_render` (local, kind=`candlestick` ≥5 candles) and attach the image to the final verdict. Never re-fetch candles just to draw; no candles → skip the chart, don't add data calls. Kind/color details: see `ve-bieu-do-ky-thuat`.

**Step 3-4: Dispatch technicals + valuation (never call the underlying tools).**

Dispatch `ky-thuat-chuyen-sau` (technical state) and `dinh-gia-chuyen-sau` (valuation). NEVER call `signals_technical` / `valuation_run` / `stock_forensic` directly here as a substitute — anything needing technicals/valuation goes through the sub-skill.

**Step 5-7: Quarterly earnings + news + events (direct calls).**

Run `financial_detail` (only quick earnings numbers for 4 quarters + QoQ/YoY/margin comparison — no deep financial-statement/M-Score/F-score digging, that's `co-ban-chuyen-sau`'s job), `news_symbol` + `company_events` (news + disclosures), `event_calendar_vn` (30–90 day calendar: earnings reports/AGMs/dividends).

**Step 8: Synthesis + validate.**

Run `evidence_bundle` to lock the verdict into a Tích cực / Tiêu cực / Động lực tương lai table. If a sub-skill loses a leg, still produce a verdict with the surviving leg + state the missing leg clearly, never backfill numbers. If the user asks a single dimension (`RSI FPT`) you must answer via the corresponding sub-skill, don't run all 8 steps. After 8 steps or once data is enough for the 3-column table, stop — never run a second news/events round.

## Template

ALWAYS use this exact verdict structure, every item with numbers + trend + provenance (which tool/sub-skill produced that number):

1. One-sentence assessment (recommendation/main tone).
2. Sector + how it makes money (2 lines, from Step 2).
3. Technicals (`provenance: ky-thuat-chuyen-sau`, include 1D/1W timeframes).
4. Valuation (`provenance: dinh-gia-chuyen-sau`, include UPSIDE/DOWNSIDE % if any).
5. Quarterly earnings (DT/LN numbers for 4 quarters + QoQ/YoY trend + margins, from `financial_detail` Step 5).
6. News + upcoming events (from `news_symbol` / `company_events` / `event_calendar_vn`).
7. Tích cực / Tiêu cực / Động lực tương lai table (3 columns, locked via `evidence_bundle`).
8. Candlestick chart attached (from Step 2b, if any).
9. One-sentence conclusion for the whole stock.

## Examples

**Example 1:**
Input: Phân tích FPT
Output: all 8 steps done, 3-column tích cực/tiêu cực/động lực table, ≤8 own calls (sub-skill calls not counted). Live numbers live in the sub-skills `ky-thuat-chuyen-sau` and `dinh-gia-chuyen-sau` — never fabricate numbers in this skill.
---

## 18 · phan-tich-sentiment
> File thật: `OpenTrading/skills/phan-tich-sentiment/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-sentiment
description: Measure the crowd on 1 stock via Fireant (sentiment score + quotes + FOMO warning). Always use this skill when the user asks what the street/crowd says about a stock, sentiment or FOMO — e.g. "Phố nói gì về FPT", "crowd có FOMO HPG không" — even when the user doesn't say explicitly they want "đo sentiment".
activation: auto
requires_tools: [mcp__opentrading__sentiment_score]
tool_budget: 6
triggers:
  keywords: [sentiment, dư luận, phố nói gì, crowd, fomo, tâm lý nhà đầu tư, comment]
version: 1.2.0
```


# Measuring Single-Stock Crowd Sentiment

Measure the *crowd*, not the *business* — the crowd can be wrong, sentiment is never the only leg of a decision. One symbol/run; limit 20 covers 90% of cases, never widen the limit. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: asked about the crowd/sentiment/FOMO/comments on 1 specific stock on Fireant.
- When NOT to use (use a different skill instead): official news/rumors → `tim-kiem-tin-tuc`; general fear/greed → `danh-gia-vi-mo-quoc-te` / `nhip-dap-crypto`; broker ratings → `tim-co-hoi-bao-cao-ctck`.

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: top 20 posts + score + comments of the hottest post (parallel)
- [ ] Step 2: cross-check disclosures (only on contradiction)
- [ ] Step 3: verdict (score + quotes + comments + FOMO + warning)
```

**Step 1: Top 20 posts + score + comments (parallel).**

Run `sentiment_score` (symbol, limit=20) — score + posts from Fireant. Run `news_symbol`/Fireant posts (limit=20) to read titles/summaries of the top 20. Pick the hottest post (highest interactions/comments) → run `fireant_thread` (post_id) to get the actual comments (replies) — read the comments' mood, not just the score. Stop when you have the score + ≥3 quotes + ≥3 comments + source label.

**Step 2: Cross-check disclosures (only on contradiction, sequential).**

Run `company_events` (symbol) when comments contradict disclosures. Never use sentiment to "settle the case" — only confirm/deny.

**Step 3: Validate before finalizing.**

No Groq → `score_heuristic` + warning "groq unavailable" → mandatory `heuristic` label in the verdict (different scale, never cross-normalize the two Groq/heuristic modes). Empty posts = low-discussion stock (empty is valid), never fabricate quotes, state clearly "ít bàn luận". Fireant down → single fallback: GDELT titles via `tim-kiem-tin-tuc` (1 call), state the replacement source clearly. Never interpret the heuristic as "should buy/sell" advice.

## Template

ALWAYS use this exact verdict structure:

- **Sentiment score** (Groq or heuristic — mandatory source label).
- **3–5 representative comment quotes** (positive / negative / repeat-poster) + Fireant provenance.
- **FOMO/panic detection** (symbol tag frequency + likes); heuristic thresholds: <−0.3 panic · >+0.3 FOMO · in between = neutral.
- **Mandatory loop warning:** the crowd can be wrong — sentiment must never be the only leg of a decision.

## Examples

**Example 1 (live 02-10-2026, no new fabricated numbers):**
Input: Phố nói gì về FPT
Output: FPT — 20 posts, heuristic **−0.25**, while M −2.06 is clean (classic crowd≠fundamentals) · VCB posts on rates 0.1-6% → score + ≥3 quotes + source label, ≤4 calls. Missing the source label or the loop warning = not done.
---

## 19 · phan-tich-vang-ty-gia
> File thật: `OpenTrading/skills/phan-tich-vang-ty-gia/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: phan-tich-vang-ty-gia
description: "Analyze SJC gold, the SJC-vs-world premium, the USDVND rate and rates at both ends SBV-Fed (max 10 calls). Always use this skill when the user asks how much more expensive SJC gold is than the world, whether the FX rate is under pressure, or a VN gold frame forecast — even when the user doesn't say explicitly they want 'phân tích vàng'."
activation: auto
requires_tools: [mcp__opentrading__vn_retail_gold]
tool_budget: 10
triggers:
  keywords: [vàng sjc, vàng miếng, giá vàng, usdvnd, tỷ giá, premium vàng, vàng thế giới, xauusd, dự đoán vàng]
version: 1.3.0
```


# Analyzing Gold Premium and USDVND Pressure

Returns: world price + 3-line TA · premium % + VN gold frame forecast (with the world / against the world when the premium widens) · rates at both ends + FX implications · odds scenarios. No point forecast of a specific price ("vàng sẽ lên X triệu") — only premium + drivers + odds scenarios. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks SJC gold/gold bar prices, the VN–world gap (premium), world gold price + gold TA, USDVND FX pressure, a VN gold frame forecast, SBV–Fed rates at both ends and FX implications.
- When NOT to use (use a different skill instead): general VN policy rates (only `danh-gia-vi-mo-viet-nam`); crypto pulse (only `nhip-dap-crypto`); VN stock TA (only `ky-thuat-chuyen-sau`).

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 1: international gold price + gold TA
- [ ] Step 2: geopolitical risk (cross-ref, no re-calls)
- [ ] Step 3: VN–world gap → premium
- [ ] Step 4: rates at both ends
- [ ] Step 5: odds scenarios + verdict
```

**Step 1: International gold price + gold TA.**

Run `yf_commodities` (GC — 1 call already includes GC+DXY, don't split into separate ticks) + `vn_msn_fx_gold`. Read trend/momentum on daily candles (price vs SMA20/50 + RSI estimated from the series). `signals_technical` only supports VN stocks — never force it for GC=F, read TA from the series you already have.

**Step 2: Geopolitical risk (cross-ref, no re-calls).**

Reference `danh-gia-tinh-hinh-xung-dot` / `bat-on-quoc-gia` if just run in a previous skill (escalation = gold up); don't re-call and waste budget.

**Step 3: VN–world gap → premium.**

Run `vn_retail_gold` (SJC mua/bán). Premium = (SJC mua vào − converted world price) / world price — mandatory to state the unit-conversion assumption (SJC VND/lượng vs XAUUSD USD/oz). Widening premium = VN gold resists following the world price down.

**Step 4: Rates at both ends.**

Run `sbv_rates` + `fred_series` (DGS10) + `yf_yield_curve`: SBV (refinancing/discount) vs US (DGS10/curve) — the spread pulls capital, implies FX pressure.

**Step 5: Odds scenarios + validate.**

Reference `world_prediction_odds` (cross-ref `du-doan-fed`) + `macro_events_vn` for context. Only state premium + drivers + odds scenarios, no point forecasts.

## Template

ALWAYS use this exact verdict structure: world price + 3-line TA · premium % + VN gold frame forecast (with the world / against the world when the premium widens) · rates at both ends + FX implications · odds scenarios · NO point price forecast.

## Examples

**Example 1 (live 02-10-2026, no new fabricated numbers):**
Input: Vàng SJC hôm nay đắt hơn thế giới bao nhiêu
Output: VÀNG MIẾNG SJC 999.9 (BTMC live) · XAUUSD 4,195 · USDVND 25,970 (MSN) · SBV 4.5% tái cấp vốn · Fed giữ 74.5% → premium % number + assumption + 2 drivers, ≤10 calls.
---

## 20 · so-sanh-cung-nganh
> File thật: `OpenTrading/skills/so-sanh-cung-nganh/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: so-sanh-cung-nganh
description: "Rank 2-6 same-sector stocks and pick the leader (quality × momentum). Always use this skill when the user asks to compare same-sector stocks, which is strongest/most worth buying — e.g. 'VCB vs BID vs CTG', 'steel mạnh nhất là ai' — even when the user doesn't say explicitly they want 'so sánh cùng ngành'."
activation: auto
requires_tools: [mcp__opentrading__compare_equities]
tool_budget: 8
triggers:
  keywords: [so sánh, vs, so với, cùng ngành, mạnh nhất, leader, hơn kém, xếp hạng mã]
version: 1.3.0
```


# Ranking Same-Sector Stocks

Second coordinator skill (same family as `phan-tich-chuyen-sau-1-ma`): resolve same-sector stocks, call 1 sub-skill per stock, merge into a ranking. Each stock gets only 1 sub-skill based on the question (momentum → technicals; quality → fundamentals; cheap/expensive → valuation) — never run all 3 dimensions per stock, never run a second sub-skill round. Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks to compare/rank 2–6 same-sector stocks (`VCB vs BID vs CTG`, `steel mạnh nhất là ai`, `ngân hàng nào đáng mua nhất`).
- When NOT to use (use a different skill instead):
  - Only 1 stock → `phan-tich-chuyen-sau-1-ma`.
  - Single dimension for 1 stock (RSI → `ky-thuat-chuyen-sau`; financial statements → `co-ban-chuyen-sau`; fair value → `dinh-gia-chuyen-sau`).

## Workflow

Copy the checklist and tick as you go:

```
Task Progress:
- [ ] Step 0: resolve same-sector stocks (max 6)
- [ ] Step 1: quick table (overview + momentum + prices in 1 shot)
- [ ] Step 2: 1 sub-skill/stock, max 4 parallel
- [ ] Step 3: sector backdrop + ranking verdict
```

**Step 0: Resolve same-sector stocks (direct calls).**

Run `vn_reference` (industry) or `vs_industry_tree` (GICS lookup) → pick max 6 stocks; given only a sector name use `stock_screener` (sector filter, narrow pool). More than 6 → ask the user to narrow, never expand on your own. `vn_reference` industry no match → try `vs_industry_tree` once, still nothing → ask for the sector again, never guess symbols.

**Step 1: Quick table (direct calls).**

Run `compare_equities` (≤4 stocks/call; 5–6 stocks → split 4+2 with `peer_compare`) + `vn_equity_quote_batch` (≤6 stocks, 1 call): overview + momentum + price table in 1 shot.

**Step 2: Call a sub-skill per stock (dispatch, max 4 parallel).**

Dispatch `ky-thuat-chuyen-sau` OR `co-ban-chuyen-sau` OR `dinh-gia-chuyen-sau` for each stock based on the question. NEVER call `signals_technical` / `financial_detail` / `valuation_run` directly here.

**Step 3: Sector backdrop + validate.**

Run `vs_gics_index` (group) as the sector index backdrop (1 call). Peak-hour enrich throttle → empty ratios → technical-only verdict + note the gap, never fabricate PE/ROE. Missing data on 1 criterion → partial ranking + note "n/6 mã có đủ", never silently drop stocks.

## Template

ALWAYS use this exact verdict structure, every item with numbers + provenance:

1. Ranking table {symbol · PE · ROE · momentum · RS · price} (`provenance: compare_equities` / `peer_compare` / `vn_equity_quote_batch` + Step 2 sub-skill).
2. One-line rationale: leader = quality × momentum; good valuation = low PE within a high-ROE group.
3. Group-correlation warning when allocating across the whole group (cross-ref `correlation_matrix`, reference only).
4. One-sentence conclusion: which stock + why.

## Examples

**Example 1 (live 02-10-2026, no new fabricated numbers):**
Input: So sánh bank
Output: compare_equities VCB-vs-HPG 2.8s · peer_compare cap 6 · vs_gics_index 3 groups live · quote_batch 1 request VN30 · HOSE universe 757 stocks → peer list ≤6 + capped sub-skill calls + ranking table, ≤8 own calls.
---

## 21 · tim-co-hoi-bao-cao-ctck
> File thật: `OpenTrading/skills/tim-co-hoi-bao-cao-ctck/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tim-co-hoi-bao-cao-ctck
description: "Hunt opportunities from broker analyst reports (CTCK): rating + target price + upside % verified against the current price. Always use this skill when the user asks what brokers (CTCK) recommend buying, which tickers got new targets, or what a broker report says — e.g. 'CTCK gần đây khuyên mua gì', 'có target mới cho MSN không' — even when the user doesn't explicitly say they want to 'tìm báo cáo CTCK'."
activation: auto
requires_tools: [mcp__opentrading__analyst_consensus]
tool_budget: 8
triggers:
  keywords: [ctck, khuyên mua, giá mục tiêu, target, báo cáo phân tích, khuyến nghị, rating]
version: 1.3.0
```


# Hunting Broker-Report Opportunities

Broker recommendations are INPUT, not gospel — always verify upside against the current price and include the disclaimer. Never turn a recommendation into "nên mua"; never fabricate target prices when the feed has none.

Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: asking about broker rating/target/reports from the shared feed or a specific ticker, or an upside % table is needed.
- When NOT to use (use another skill instead): rumor/crowd → `phan-tich-sentiment` / `tim-kiem-tin-tuc`; own valuation → `dinh-gia-chuyen-sau`; backtest → `kiem-chien-luoc-backtest`.

## Workflow

Copy the checklist and tick as you progress:

```
Task Progress:
- [ ] Step 1: shared feed (1 call only)
- [ ] Step 2: specific ticker + source docs + read PDF
- [ ] Step 3: verify upside top 1-2 tickers
- [ ] Step 4: table + disclaimer
```

**Step 1: Shared feed (1 call only).**

Run `analyst_consensus` (limit=30) — shared feed without symbol, parse rating + target price from titles. For macro reports add `analyst_consensus` (report_type=macro): filter CTCK macro reports (entry section/report); if there are no dated reports, use the source figures. If the feed is genuinely empty (weekend) → empty is valid, widen `days` once only, then conclude.

**Step 2: Specific ticker + source docs (sequential, after Step 1).**

Run `analyst_consensus` (symbol, limit=15) + `vs_documents` (symbol, only the single most worthwhile ticker) + `web_fetch` (format=pdf, report URL — read the PDF stdlib-only, scan it honestly, cap 10 pages/20k chars). If the user names a ticker and `analyst_consensus` (symbol) is empty → read the shared feed and filter titles containing the ticker (title-scrape filtering may miss some); do not retry with a different limit.

**Step 3: Verify upside (sequential, 1–2 standout tickers).**

Run `stock_overview` (1–2 calls) to compare current price vs target → upside %. Verify only the top picks, not everything.

## Template

ALWAYS use this exact verdict structure:

- Table {mã · CTCK · rating · giá mục tiêu · ngày · upside % so giá hiện tại}, filtered within `days` (default 7).
- Top 3 opportunities (large upside + MUA rating + still valid).
- The **"đã kiểm chứng"** column is mandatory = Step 3 ran for the 1–2 standout tickers (with `stock_overview`); unverified tickers must be marked "chưa kiểm chứng giá hiện tại".
- Mandatory disclaimer: broker recommendations are INPUT, not gospel — do not turn them into "nên mua".
- Provenance: dates come from URL/title; if `source/date null` (typical when parsing titles) → infer the date from URL/title + state the date source as "không chắc chắn". Once the table has ≥5 rows + 2 top tickers verified, stop; do not dig into tickers outside the top.

## Examples

**Example 1 (live 02-10-2026, do not fabricate new numbers):**
Input: CTCK khuyên mua gì tuần này
Output: Shared feed **7 reports** — MBB MUA 28,200 · **MSN MUA 89,200 (30/09)** · VPB KHẢ QUAN 30,500 · MSB GIẢM TỶ TRỌNG 13,200 · FRT THEO DÕI 157,000 · filter symbol=VCB/FPT each empty as expected → table ≥5 rows with upside %, verify 2 top tickers, ≤8 calls. Missing the "đã kiểm chứng" column or the disclaimer → not done; fabricating a target when the feed is empty → not done.
---

## 22 · tim-kiem-tin-tuc
> File thật: `OpenTrading/skills/tim-kiem-tin-tuc/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tim-kiem-tin-tuc
description: Hunt news by keyword/ticker/scope from VN to global, including rumors (web + comments hunt, cross-check announcements, 4-column verdict + CHƯA XÁC NHẬN label). Always use this skill when the user names a specific ticker/keyword or wants to verify a rumor — e.g. "tin về FPT", "nghe đồn HPG, có thật không" — even when the user doesn't explicitly say they want to "tìm tin".
activation: auto
requires_tools: [mcp__opentrading__news_symbol]
tool_budget: 10
triggers:
  keywords: [tin về, tìm tin, tin tức về, news về, tin trên, dư luận về, nghe đồn, tin đồn, có thật không]
version: 1.3.0
```


# Hunting News Including Rumors

Rumors precede official news — hunt both but always classify clearly official vs CHƯA XÁC NHẬN. Never pass a rumor off as fact; never drop the confidence label.

Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user names a specific ticker/keyword/scope, wants news + rumor + crowd hunting, wants to verify a rumor, or wants a deep dive on one item.
- When NOT to use (use another skill instead): default digest without keywords → `tin-tuc-nong-viet-nam` / `tin-tuc-nong-quoc-te`; crowd/FOMO only → `phan-tich-sentiment`; broker rating/target only → `tim-co-hoi-bao-cao-ctck`; strategy backtest only → `kiem-chien-luoc-backtest`.

## Workflow

Copy the checklist and tick as you progress (pick EXACTLY 1 mode):

```
Task Progress:
- [ ] Mode A (by ticker): news_symbol → web + comments hunt → cross-check → sentiment
- [ ] Mode B (VN): news_market + corporate → 2-3 standout tickers
- [ ] Mode C (global): news_market gdelt → geo/event + web EN
- [ ] 4-column verdict + confirmation label
```

**Mode A — By ticker (+ rumors).**

1. Run `news_symbol` (symbol, limit=20) first. NEVER run web_search before `news_symbol` returns — the web is only for cross-verification afterwards.
2. Hunt web + comments in parallel: `web_search` ("ticker name" + "đồn"/"tin đồn"/rumor, max 2 queries) → `web_fetch` the 1–2 most suspicious URLs + `fireant_thread` (post_id from step 1 — rumors live in the replies; Fireant posts have real ids now, never fabricate a post_id).
3. Cross-check sequentially: `corporate_calendar` (symbol) + `company_events` (symbol) — does the news match an announcement?
4. Crowd: `sentiment_score` (symbol). Stop once ≥5 items meet the bar.

**Mode B — VN.**

1. Run in parallel `news_market` (limit=15) + `corporate_calendar` (limit=20).
2. Sequentially: `news_symbol` × 2–3 standout tickers + `web_search` the hottest item for cross-verification. Do not dig beyond the 2–3 tickers.

**Mode C — Global.**

1. Run in parallel `news_market` (sources=gdelt, limit=10).
2. In parallel: `geo_intel` (topic) / `event_stats` (query) + `web_search` (English keywords). GDELT empty → try English once, then conclude "ít coverage ngôn ngữ đó".

**Shared validation.**

`web_search` hidden when the key is missing → use Fireant+GDELT only + state "chưa quét web" clearly. If both news sources are dead → read `snapshot_history` (kind=news_feed), must state "cache <ngày>" clearly.

## Template

ALWAYS use this exact verdict structure:

| Tiêu đề | Tuổi tin | Độ tin cậy + provenance | Triển vọng |
- **Tiêu đề** full title, with related tickers. **Tuổi tin** (hours/days ago — news >3 days old on a bluechip counts as already priced in). **Độ tin cậy** (official / broker / Fireant-crowd / anonymous-open-source) + provenance (`news_symbol`/`news_market`/Fireant/GDELT/web). **Triển vọng** (impact on the business: revenue/profit/price — or just noise). Rumors must carry the `CHƯA XÁC NHẬN` label + confirmation conditions (which announcement to await, on which date).
- Deep dive on the most important item: who said it → said what → attached evidence → is the impact quantifiable (e.g. dividend per share, deal size in billions) → scenario if true/false.

## Examples

**Example 1 (live 02-10-2026, do not fabricate new numbers):**
Input: Nghe đồn HPG ... thật không
Output: `news_symbol("VCB")` → VCB interest-rate 0.1-6% posts · GDELT "dầu" live · corporate VCB 487 docs · `fireant_thread` (post PNJ 42088453) → root + 2 real replies → 4-column verdict + detailed analysis + confirmation label, ≤10 calls. Any 1 of the 4 verdict columns missing → not done; missing the `CHƯA XÁC NHẬN` label for a rumor → not done.
---

## 23 · tin-tuc-nong-quoc-te
> File thật: `OpenTrading/skills/tin-tuc-nong-quoc-te/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tin-tuc-nong-quoc-te
description: Digest world news that moves markets (5 headlines + market reaction verified with numbers). Always use this skill when the user asks about international/US/China news today — even when the user doesn't explicitly say they want a 'digest tin nóng'.
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 8
triggers:
  keywords: [tin quốc tế, tin thế giới, thị trường mỹ, fed tin, wall street, nasdaq]
version: 1.2.0
```


# Digesting Global Hot News With Market Reaction

World news + market reaction verified with NUMBERS — no bare headlines. News without a reaction yet must state "thị trường chưa phản ánh"; never fabricate a reaction. International rumors must carry the `CHƯA XÁC NHẬN` label.

Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: international/US/China news, Fed, Wall Street, need headlines + market figures confirming the reaction.
- When NOT to use (use another skill instead): VN news → `tin-tuc-nong-viet-nam`; specific keywords/rumors → `tim-kiem-tin-tuc` mode C; deep macro (curve, flows, separate fear/greed) → `danh-gia-vi-mo-quoc-te`; crypto → `nhip-dap-crypto`.

## Workflow

Copy the checklist and tick as you progress:

```
Task Progress:
- [ ] Step 1: global news (parallel)
- [ ] Step 2: reaction with numbers (parallel, after Step 1)
- [ ] Step 3: verify the 1 standout item
- [ ] Step 4: 5-headline verdict + reaction
```

**Step 1: Global news (parallel).**

Run `news_market` (sources=gdelt) + `geo_intel` (no topic = global coverage). Do not add a narrow topic yourself when the user asks broadly. GDELT empty → try English keywords once, then conclude "ít coverage".

**Step 2: Reaction with numbers (parallel, sequential after Step 1 to pick the right items).**

Run `yf_mega_flows` + `world_fear_greed`.

**Step 3: Verify the 1 standout item (sequential).**

Run `event_stats` for exactly the 1 standout keyword, not every headline. Both news sources dead → read `snapshot_history` (kind=news_feed), must state "cache <ngày>" clearly. Empty feed on a weekend → empty is valid, state the market holiday.

## Template

ALWAYS use this exact verdict structure: 5 headlines, each item with **tiêu đề + tuổi tin + provenance** (GDELT/`geo_intel`) + **market reaction with NUMBERS** (mega-cap flows, fear/greed, curve if rates involved).

## Examples

**Example 1 (live 02-10-2026, do not fabricate new numbers):**
Input: Tin thế giới
Output: mega_flows AAPL/MSFT/NVDA OK · fear/greed 70-74 Greed 7 days → ≥5 headlines + ≥2 quantified reaction items, ≤8 calls. Missing reaction numbers without stating "thị trường chưa phản ánh" → not done.
---

## 24 · tin-tuc-nong-viet-nam
> File thật: `OpenTrading/skills/tin-tuc-nong-viet-nam/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: tin-tuc-nong-viet-nam
description: Digest today's hot VN news (5-7 headlines + classification + sentiment + provenance). Always use this skill when the user asks broadly about VN stock/market/business news today — e.g. "tin nóng hôm nay", "có tin gì về VN30" — even when the user doesn't explicitly say they want a "digest tin nóng".
activation: auto
requires_tools: [mcp__opentrading__news_market]
tool_budget: 9
triggers:
  keywords: [tin nóng, tin chứng khoán, tin hôm nay, tin vn, tin doanh nghiệp, headline]
version: 1.2.0
```


# Digesting Daily Vietnam News

Fast digest of today's VN news — headlines + classification + sentiment, with clear provenance. Never turn heuristic sentiment into buy/sell recommendations.

Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: today's hot VN news, VN30, VN market/business, a quick 5–7 headline digest is needed.
- When NOT to use (use another skill instead): specific ticker/keyword or rumor → `tim-kiem-tin-tuc`; US/China/global news → `tin-tuc-nong-quoc-te`; deep crowd/FOMO dive on 1 ticker → `phan-tich-sentiment`; broker rating/target → `tim-co-hoi-bao-cao-ctck`.

## Workflow

Copy the checklist and tick as you progress:

```
Task Progress:
- [ ] Step 1: general news + announcement calendar (parallel)
- [ ] Step 2: dig into the 2-3 most frequent tickers
- [ ] Step 3: sentiment + cross-check the hottest ticker
- [ ] Step 4: 5-7 headline verdict
```

**Step 1: General news + announcement calendar (parallel).**

Run `news_market` (limit=15) + `corporate_calendar` (limit=20).

**Step 2: Dig into standout tickers (sequential, after Step 1).**

Run `news_symbol` × 2–3 tickers appearing most in the news — pick by appearance frequency, not gut feeling, max 3 tickers.

**Step 3: Sentiment + cross-check (parallel).**

Run `sentiment_score` (hottest ticker) + `company_events` (that ticker, cross-check only, do not dig the full history). Missing Groq → use heuristic + warning, the verdict must carry the `heuristic` label.

**Step 4: Validate before finalizing.**

Fireant dead → the tool falls back to GDELT itself, no infinite Fireant retries. Both dead → read `snapshot_history` (kind=news_feed) 1-day cache, must state clearly that it is a cache + the cache date. Empty feed on weekends/holidays → empty is valid, state "phiên nghỉ, ít tin mới". Stop once 5 headlines have provenance; stop once the Step 3 verdict exists for the hottest ticker. Do not re-call `sentiment_score` with a larger limit.

## Template

ALWAYS use this exact verdict structure, each headline with: **tiêu đề + mã liên quan + phân loại** (catalyst / đồn đoán / tin vĩ mô) + **sentiment** if there is enough data + **provenance** (Fireant/GDELT) + **tuổi tin**. Rumors must carry the `CHƯA XÁC NHẬN` label.

## Examples

**Example 1 (live 02-10-2026, do not fabricate new numbers):**
Input: Tin nóng hôm nay
Output: Fireant posts 02-10 (fuel stabilization fund back to KBNN; HN land market shifts sentiment; tax-id cleanup campaign) · `news_symbol("VCB")` → interest-rate 0.1-6% posts → ≥5 headlines with provenance, ≤9 calls. Missing provenance or classification → not done; sentiment without a source label → not done.
---

## 25 · ve-bieu-do-ky-thuat
> File thật: `OpenTrading/skills/ve-bieu-do-ky-thuat/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: ve-bieu-do-ky-thuat
description: "Draw charts right in the TUI (candlestick, price line, sparkline, bar, gauge, heatmap, donut, histogram, multi-ticker compare, depth orderbook) with ANSI color. Always use this skill when the user says vẽ, chart, nến, candlestick or asks to see price bias visually — e.g. 'vẽ nến VCB', 'so chart VCB vs HPG' — even when the user doesn't explicitly say they want 'vẽ biểu đồ'."
activation: auto
requires_tools: [chart_render]
triggers:
  keywords: [vẽ, chart, nến, candlestick, đường giá, sparkline, biểu đồ, đồ thị, so sánh, bar, gauge, heatmap, donut, histogram, fear, greed, tương quan, tỷ trọng]
tool_budget: 8
version: 1.3.0
```


# Drawing Charts Inside the TUI

Pure display skill: data comes from data tools on every call, there are no fixed live numbers — never pass illustrative numbers off as real ones. Reuse data already in context; do not re-fetch.

Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user says vẽ, chart, nến, candlestick, price line, sparkline, compare 2–5 tickers, sector/top gainers-losers bar, fear/greed gauge, correlation heatmap, allocation donut, distribution histogram, depth orderbook.
- When NOT to use (use another skill instead): text-only analysis (use `ky-thuat-chuyen-sau` only); detailed valuation (use `dinh-gia-chuyen-sau` only).

## Lookup: Data Tool to Chart Kind

| Data (tool) | `chart_render` kind |
|---|---|
| OHLC candles: `vn_equity_ohlcv`, `market_candles_batch`, `dnse_ohlc_history` | `candlestick` (bars ≥5) |
| Price/macro series: `vn_quote_history`, `fred_series`, `vs_indicator_data`, `yf_alloc_history` | `line` / `sparkline` / `area` |
| Compare 2–5 tickers/assets: `compare_assets`, `compare_equities`, `vn_equity_quote_batch` | `chart_compare` (dedicated tool, legend + % from first point) |
| Top gainers/losers, sector, per/pb, odds, annual targets: `market_movers`, `sector_performance`, `valuation_run`, `world_prediction_odds`, `planned_targets` | `bar` (series + labels; green when ≥0, red when <0) |
| Distributions: `event_study` CARs, `pattern_match` corrs | `histogram` |
| Matrices: `correlation_matrix`, `compare_assets`, `vs_industry_heatmap` | `heatmap` (matrix + labels rows+cols) |
| Single number: `world_fear_greed`, `sentiment_score`, `quant_risk` | `gauge` (value+max) |
| Allocation weights: `portfolio_optimize`, `holders`, `breadth_scan` | `donut` (value+max) |
| Win/loss: `money_flow`, `vs_nn_flow` sign | `winloss` |
| Orderbook: `dnse_orderbook` | `chart_depth` |

## Workflow

Copy the checklist and tick as you progress:

```
Task Progress:
- [ ] Step 1: get data (reuse from context if available)
- [ ] Step 2: draw (correct kind + color)
- [ ] Step 3: 2-3 sentence verdict
```

**Step 1: Get data.**

Pick the data tool from the lookup table above. Choose the right source before drawing: VN ticker → `vn_equity_ohlcv`/`vn_quote_history` (NEVER use `vn_crypto_ohlcv` for stocks); USD crypto → `crypto_spot`. If data is missing, say so honestly; never draw without data. Minimum thresholds: candlestick ≥5 candles; line/sparkline/area/winloss ≥2 points; histogram ≥5 points; heatmap non-empty matrix; gauge/donut need value+max. Below threshold → do not draw, report missing data.

**Step 2: Draw.**

Run `chart_render` (+symbol) or `chart_compare`. ANSI color follows direction automatically (up green/down red); `color=never` when the user copies plain text. Default width 64 chars (never exceed 100 to avoid breaking TUI wrap); candle height 14, line 10, compact 1–8.

**Step 3: Verdict.**

Read from the picture + numbers: trend, HH/LL, price position vs range. 2–3 sentences, state units in kVND (57.3 = 57,300đ). Long charts auto-collapse after 3 lines (ctrl+o to expand) — do not summarize the picture in long prose. Outside DNSE hours an empty orderbook is expected; `chart_depth` reports empty, no retry.

## Template

ALWAYS use this output structure: the chart picture (keep ANSI chars intact) + 2–3 sentence verdict (trend, HH/LL, price position vs range, kVND units).

## Examples

**Example 1:**
Input: vẽ nến VCB 30 phiên
Output: 1 data call + 1 `chart_render` call + colored candle picture + verdict ≤3 sentences, ≤8 calls.
---

## 26 · vn-market-basics
> File thật: `OpenTrading/skills/vn-market-basics/SKILL.md` — sửa file này ở repo OpenTrading, đừng sửa bản gộp.

```yaml
name: vn-market-basics
description: "Explain Vietnam stock trading mechanics (HOSE/HNX/UPCoM exchanges, ATO/continuous/ATC sessions, price bands, tick size, lots, T+2 settlement cycle, LO/MP order types). Always use this skill when the user asks about trading rules/mechanics — e.g. 'biên độ HOSE bao nhiêu', 'lô chẵn lô lẻ là sao' — even when the user doesn't explicitly say they want to 'hỏi cơ chế'."
activation: auto
triggers:
  keywords: [biên độ, bước giá, lô chẵn, lô lẻ, ATO, ATC, loại lệnh, thanh toán T, phiên giao dịch]
version: 1.3.0
```


# Explaining Vietnam Market Mechanics

Answer concisely per exchange (where they differ) + a note that KRX/CCP/upgrade info may be outdated + 1 line advising to check official sources. Never give current price or market-index numbers in this skill.

Verdict labels, units and output formatting stay in Vietnamese (user-visible); answer in the user's language (Vietnamese by default).

## When to Use

- Use when: the user asks about HOSE/HNX/UPCoM, ATO/continuous/ATC sessions, price bands, tick size, even/odd lots, settlement cycle, order types (LO, MP, ATO, ATC...).
- When NOT to use (use another skill instead): asking what P/E, EPS, ROE, margin mean (use `explain-term` only); asking whether to keep a held ticker (use `devil-advocate` only); asking for current prices/indices (use an analysis skill instead).

## Workflow

Copy the checklist and tick as you progress:

```
Task Progress:
- [ ] Step 1: identify the relevant exchange (split HOSE/HNX/UPCoM)
- [ ] Step 2: answer per current KRX rules + note possibly outdated
- [ ] Step 3: advise checking official sources
```

**Step 1: Identify the relevant exchange.**

Distinguish HOSE/HNX/UPCoM clearly where rules differ; do not collapse price bands/tick sizes/lot sizes of all 3 exchanges into one number.

**Step 2: Answer per current KRX rules.**

Rules change over time (KRX system, CCP roadmap, FTSE upgrade) — must state clearly that the info reflects the model's knowledge and may be outdated. Claiming certainty about new rules without this note is wrong.

**Step 3: Advise checking official sources.**

Always advise the user to cross-check exchange or broker announcements. Do not include current prices — mechanics only, no market numbers.

## Template

ALWAYS use this exact output structure: concise answer per exchange (where they differ) · note that KRX/CCP/upgrade info may be outdated · 1 line advising to check official sources.

## Examples

**Example 1:**
Input: Biên độ HOSE bao nhiêu
Output: number per exchange + note KRX may be outdated + line advising to check the exchange/broker, no market prices.
---
