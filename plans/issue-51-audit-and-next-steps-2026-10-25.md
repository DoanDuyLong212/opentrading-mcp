# Kiểm toán issue #51 và kế hoạch tiếp theo — 25/10/2026

## Primary goal

Nhà đầu tư nhận chỉ số có công thức, kỳ, đơn vị và ngày dữ liệu kiểm chứng được; mọi điểm thiếu đầu vào hoặc chưa phù hợp ngành được hiển thị như vậy. Các năng lực mới chỉ xuất hiện sau khi nguồn và phép kiểm ngoài mẫu tương ứng đạt.

## Phạm vi kiểm toán

Đối chiếu `main` tại `8265ed5` với issue #51 và các PR #53–#57 đã merge. Issue có Phase 0–8 cộng Phase 9 kiểm chứng, tức **10 phase**, không phải chín. Bình luận “Phase 0–1 đã mở khóa” nói về adapter annual cho doanh nghiệp thông thường; Phase 1 của issue là mô hình riêng ba ngành tài chính và chưa hoàn thành.

| Phase | Trạng thái được mã chứng minh | Điều kiện còn thiếu |
| --- | --- | --- |
| 0. Registry | Có provenance từng trường BCTC; registry tham chiếu cho năm họ tool đang triển khai ở nhánh này | Mọi field/tool, publication-as-of, scope/revision được xác minh; nhiều nguồn hiện không cung cấp metadata |
| 1. Bank/CK/BH | `not_applicable`/`unsupported` là kết quả đúng hiện tại | Taxonomy, nguồn ngành, công thức, fixture và review nghiệp vụ riêng |
| 2. Ngưỡng VN | Chưa có hiệu chuẩn | Panel point-in-time, nhãn outcome đáng tin, holdout theo thời gian/doanh nghiệp, chi phí và khoảng tin cậy |
| 3. Quarterly/TTM forensic | Chỉ có `derive_quarter_cfo` thuần | Semantics quý/YTD Vietstock, revision và publication, bốn quý không trùng, hai cửa sổ Beneish, ba snapshot Piotroski |
| 4. Imputation | Chưa có | Scenario opt-in riêng, provenance và độ nhạy; không thay strict score hay cờ rủi ro |
| 5. Ichimoku/trough | `classic26` là option có oracle công thức; trough có rule v1 | Export chỉ báo tham chiếu, đặc tả biến thể trough có ngày xác nhận |
| 6. Current-TTM PE/cap | EPS quý có trong detail; giá batch có ClosePrice | Đơn vị EPS riêng, ngày công bố/revision, cùng cơ sở cổ phiếu sau split/bonus, giá có ngày/đơn vị/adjustment, shares outstanding cùng thời điểm |
| 7. vnstock v5 | Runtime khóa 4.0.2 | Frozen parity matrix, môi trường v5 riêng, adapter, rollback và live smoke |
| 8. OpenTrading | Repo truy cập được; consumer skill trên remote main còn hợp đồng M-score cũ | PR riêng cập nhật schema/diễn giải, kiểm e2e với MCP đã deploy |
| 9. Verification | CI các PR cũ xanh, nhưng chưa chứng minh các gate trên | Review tài chính độc lập, oracle số học, fixture báo cáo gốc, test as-of và deployment SHA |

## Kết quả kiểm toán công thức cần ưu tiên

Ba lỗi ở nhánh hiện hành trước sửa:

1. `forensic.py` vẫn có thể dựng PPE từ riêng dòng thuê tài chính khi thiếu TSCĐ hữu hình, làm M-score đổi mà vẫn `complete`.
2. DEPI có thể dùng gross PPE năm hiện tại và net PPE năm trước nhưng chỉ ghi một basis.
3. Dòng 3022 là phải thu khách hàng, hẹp hơn Compustat Receivables Total [2]; dòng 2242 chưa chứng minh tương đương depreciation item của mô hình. Không thể gọi M-score strict đầy đủ chỉ vì hai dòng đều có số.

Nhánh sửa #51 giữ số quan sát và provenance nhưng ngăn chúng tự đi vào input chuẩn, yêu cầu thành phần PPE đủ, dùng net PPE [8] nhất quán theo [Beneish/Lee/Nichols 2013, Exhibit A1](https://cpb-us-w2.wpmucdn.com/sites.udel.edu/dist/a/855/files/2020/07/Earnings-Manipulation-and-Expected-Returns.pdf), và tăng cache fingerprint. Bài báo có mô tả prose về gross PP&E khác bảng công thức; model version phải ghi lựa chọn. FPT/HPG có thể chuyển từ M-score `complete` sang `partial` cho tới khi có mapping/fixture tốt hơn; đây là suy giảm độ phủ có chủ đích, cần công bố. [Compustat manual](https://tevgeniou.github.io/EquityRiskFactors/CompustatManualChpt5.pdf) phân biệt Receivables Total [2] và Trade [151]. Ngưỡng −1.78 chỉ là tham chiếu từ nghiên cứu Mỹ, chưa hiệu chuẩn Việt Nam.

## Phase 0 — Chốt registry và sửa M-score strict

**How this serves the primary goal:** Không thể đánh giá một tín hiệu khi metadata đúng và sai bị gộp vào cùng trạng thái `supported`.

**What to implement:** Hoàn tất resource/hàm registry cho các họ tool tài chính hiện có; giữ riêng raw observed, candidate mapping và model input canonical. Bảo toàn `unsupported` khác `not_applicable`; coverage nhiều kỳ nói rõ kỳ nào. Sửa ba lỗi M-score kể trên, chặn cache cũ, cập nhật hướng dẫn OpenTrading; lưu regression về HPG template thiếu dòng lease. Sau khi có fixture HPG thật, chỉ khôi phục PPE khi subtotal/trừ intangible cùng report identity được đối chiếu; không tự điền leased gross bằng 0.

**Documentation references:** `src/opentrading_mcp/providers/forensic.py`, `forensic_models.py`, `financial_contracts.py`, `tools/compute_financial.py`, `plans/evidence/issues-39-44/second-wave-annual-source-validation.md`; nguồn Beneish/Compustat ở trên. **Verification:** 3 reproduction gốc đổi từ complete sai sang partial, Piotroski không đổi, old-cache poison không lọt, registry unknown không thành zero, OpenTrading skill lint. **Anti-pattern:** không gọi `not_reported` là revision đã xác minh; không dùng proxy như biến canonical.

## Phase 1 — Nguồn và mô hình riêng ngành tài chính

**How this serves the primary goal:** Báo cáo ngân hàng, chứng khoán và bảo hiểm có cấu trúc khác, nên cần mô hình rủi ro cùng nghĩa với dữ liệu ngành.

**What to implement:** Tạo taxonomy ngành và danh mục nguồn/định nghĩa/đơn vị/scope; thu thập ít nhất một báo cáo gốc mỗi ngành và xác nhận các chỉ tiêu vốn, dự phòng, chất lượng tài sản, tài sản khách hàng hoặc dự phòng nghiệp vụ với chuyên gia. Viết oracle và kiểm định riêng từng mô hình trước khi bật output. Đến lúc đó giữ Beneish `not_applicable`, Piotroski `unsupported`; bài [Piotroski 2000](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf) không cấm tường minh ngành tài chính nhưng không chứng minh áp dụng cho VN.

**Verification:** fixture ba ngành cùng nguồn và review nghiệp vụ; không tính khoản tiền gửi ngân hàng như nợ vay công nghiệp. **Anti-pattern:** không gắn F-score công nghiệp nhãn “bank forensic”.

## Phase 2 — Nghiên cứu ngưỡng VN theo thời điểm công bố

**How this serves the primary goal:** Cảnh báo VN chỉ có ý nghĩa đầu tư nếu ngưỡng được kiểm định trên dữ liệu biết được lúc ra quyết định.

**What to implement:** Định nghĩa outcome trước khi thu thập (gian lận/kết quả cổ phiếu/khả năng mất khả năng thanh toán là ba mục tiêu khác nhau), lập panel gồm publication/revision, delisted firms và corporate actions, khóa train/holdout theo thời gian và issuer, walk-forward cùng chi phí/CI. Báo cáo phân bố thiếu dữ liệu và selection bias; nếu chưa có nhãn/panel, chỉ xuất nghiên cứu, không threshold production.

**References:** [Piotroski 2000](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf) dời ngày hình thành danh mục để tránh nhìn trước; [CFA Backtesting & Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation). **Verification:** pipeline as-of tái lập và holdout chưa từng dùng để chọn cutoff. **Anti-pattern:** không gọi −1.78 là VN-calibrated.

## Phase 3 — Xác minh nguồn quý rồi mới ghép TTM

**How this serves the primary goal:** TTM chỉ đúng khi bốn dòng flow là bốn quý riêng và balance là snapshot cuối kỳ.

**What to implement:** Trước tiên lưu fixture quý/YTD raw với `ReportTermID`, fiscal start/end, scope, publication, revision, Unit và định nghĩa dòng EPS/CFO. Nếu nguồn thiếu metadata, giữ adapter `partial/unavailable` và ghi gap; không dùng vị trí danh sách làm thứ tự sửa đổi. Khi nguồn đạt gate, suy quý từ YTD cùng report identity, ghép bốn quý liên tiếp; Beneish so hai cửa sổ TTM cách 12 tháng, Piotroski TTM là biến thể version mới có ba snapshot assets. Cấm reuse threshold/hiệu năng của paper annual cho biến thể chưa kiểm định.

**References:** `derive_quarter_cfo` hiện có; [IAS 34](https://www.ifrs.org/issued-standards/list-of-standards/ias-34-interim-financial-reporting/) là chuẩn khái niệm, không chứng minh cách Vietstock mã hóa kỳ. **Verification:** Q4/YTD double count, năm tài chính khác lịch, restatement, scope change, công bố sau as-of, EPS/corporate action. **Anti-pattern:** không annual/4, cộng balance, hoặc ghép revision không biết.

## Phase 4 — Scenario imputation opt-in

**How this serves the primary goal:** Người dùng thấy độ nhạy của ước lượng mà không nhầm nó là điểm báo cáo chính thức.

**What to implement:** `imputation_mode=off` mặc định; khi bật, chỉ trả `scenario` riêng với phương pháp, giả định, khoảng giá trị và trường bị thay. Strict observed score giữ nguyên `null`; không sinh flags/cutoff tự động từ scenario. Chọn phương pháp sau khi có nguồn/validation của từng biến, không dùng các giá trị trung tính mặc định.

**Verification:** mode off byte-compatible; scenario không thay strict score, cache tách mode, provenance đầy đủ. **Anti-pattern:** không gán CFO=0, DEPI=1 hay “không phát hành” từ chỗ thiếu.

## Phase 5 — Parity Ichimoku và trough variant

**How this serves the primary goal:** Tín hiệu biểu đồ/tín hiệu đáy có thể đối chiếu và tái lập theo rule_version.

**What to implement:** Giữ `offset25` mặc định và `classic26` option; ghi fixture xuất từ chỉ báo tham chiếu để chứng minh từng index trước khi đổi default. Với trough variant, chủ sở hữu cần chốt điều kiện drawdown/recovery/new peak và mốc xác nhận; triển khai dưới tên mới và so event set, không ghi đè v1.

**References:** [TradingView Ichimoku](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/) nói 26 kỳ nhưng không xác định index zero-based của code; `technicals.py`, `cycle_stats.py`. **Verification:** chuỗi OHLC không phẳng, bar đầu/cuối, no-look-ahead, cache version, giao dịch chỉ sau confirmation_date. **Anti-pattern:** không coi trough date là tín hiệu biết ngay ngày đó.

## Phase 6 — PE TTM hiện tại và market cap có chứng cứ

**How this serves the primary goal:** PE/vốn hóa không dùng giá hôm nay với lợi nhuận hoặc số cổ phiếu khác kỳ/cơ sở điều chỉnh.

**What to implement:** Adapter read-only giữ raw EPS theo bốn quý, unit VND/share riêng, publication/revision/weighted-average shares/adjustment; giá phải có timestamp, unit/currency và adjustment basis. Chỉ bật `pe_basis=current_ttm` khi bốn quý không trùng, EPS cùng basis sau bonus/split theo [IAS 33](https://www.ifrs.org/issued-standards/list-of-standards/ias-33-earnings-per-share/), giá cùng as-of. Nếu thiếu, trả `unavailable` + lý do; historical PE và `valuation_run.per` hiện hữu giữ nhãn riêng. Market cap cần số cổ phiếu **đang lưu hành** cùng ngày giá theo [SEC glossary](https://www.sec.gov/resources-small-businesses/glossary); charter capital/free float không thay thế được.

**Verification:** EPS thiếu quý/âm/0, duplicate/restatement, bonus/split, đơn vị ×1e9, giá không timestamp, shares stale, cache cold/warm. **Anti-pattern:** không cộng bốn EPS quý khác weighted-share basis và gọi TTM chuẩn.

## Phase 7 — vnstock v5 trong môi trường cách ly

**How this serves the primary goal:** Nâng thư viện mà không đổi âm thầm nến, thời gian hay báo cáo nguồn.

**What to implement:** Đóng băng parity matrix v4 từ fixture đã có, xây môi trường v5 theo [hướng dẫn 4→5 chính thức](https://www.vnstocks.com/docs/vnstock/chuyen-doi/tu-vnstock-4x), adapter riêng và so kết quả/tool errors trên cùng mã/kỳ. Chỉ đổi dependency/lock khi matrix và rollback đạt. Hướng dẫn chính thức dùng kho gói riêng và cảnh báo breaking behavior, nên không xem là rủi ro thấp.

**Verification:** candle dates/adjustment, source/period IDs, numerical units, missing/error behavior, cold/warm cache, live smoke đọc dữ liệu. **Anti-pattern:** không gộp migration với sửa công thức hay chạy v5 method trong v4.

## Phase 8 — Hợp đồng OpenTrading

**How this serves the primary goal:** Agent đầu tư không diễn giải `null` là an toàn hoặc điểm proxy là kết luận gian lận.

**What to implement:** PR riêng trên repo `FinDaHuman/OpenTrading` từ remote main cập nhật skill M-score 8 biến, Piotroski 9 tín hiệu, status/version/coverage và nguồn. Giữ checkout cũ ngoài tác động. Sau MCP deploy, kiểm một response general partial, một bank N/A, cache/schema và prompt e2e tại deployed SHA.

**Verification:** skill lint, schema keys thực tế, lời nhắc không gọi −1.78 là ngưỡng VN; không merge trước khi consumer compatibility review. **Anti-pattern:** không sửa checkout local cũ hơn remote hay gắn mẫu lịch sử như chuẩn hiện hành.

## Phase 9 — Cổng nghiệm thu từng năng lực

**How this serves the primary goal:** “Xong” nghĩa là có bằng chứng nguồn, công thức và hành vi thực, không chỉ CI xanh.

**What to implement:** Với mỗi PR, lưu nguồn/fixture/hash, oracle số học độc lập, test unit/integration/cache, review tài chính và CI trên exact head. Sau quyền triển khai, ghi deployed SHA và response sạch. Chỉ đóng checklist #51 cho phase có acceptance; các phase thiếu dữ liệu giữ open với blocker cụ thể.

**Verification:** Python/Ruff/pytest CI, kiểm as-of/restatement/scope/unit, consumer contract, không có credential trong fixture. **Anti-pattern:** không suy nguồn live đã đầy đủ chỉ từ synthetic unit test.
