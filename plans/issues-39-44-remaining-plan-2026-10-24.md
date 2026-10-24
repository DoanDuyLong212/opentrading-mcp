# Kế hoạch phần còn lại — issue #39 và #44

## Primary goal

Người dùng nhận điểm tài chính, tín hiệu thị trường và bảng chu kỳ có dữ liệu đủ, đúng thời điểm và giới hạn rõ ràng; trường hợp chưa hỗ trợ không bị hiểu thành một kết luận đã kiểm chứng.

## Phạm vi sau đợt sửa đầu

Đợt đầu trên nhánh `codex/issues-39-44-first-wave` thực hiện phase 1–3 của [review ban đầu](issues-39-44-review-2026-10-24.md): giữ số 0, kiểm số hữu hạn/coverage, chuẩn hóa báo cáo năm theo identity và sửa bộ tính Beneish/Piotroski. Giữ điểm `null` khi thiếu dữ liệu, có số thành phần kiểm được và nguồn/kỳ/scope. Công thức đầy đủ có oracle synthetic riêng; không coi đó là bằng chứng nguồn đã cung cấp đủ đầu vào.

Ba commit triển khai: `b18993e` (zero/filter), `892e66c` (annual inputs), `b552fb5` (mô hình và hợp đồng forensic). Chi tiết kiểm tra cuối đợt nằm trong [báo cáo kiểm chứng](evidence/issues-39-44/first-wave-validation.md); trạng thái PR/CI là bằng chứng riêng, không thay thế kiểm dữ liệu live.

### Những gì đã biết từ nguồn thật

Read-only `financeinfo(period="year")`, ghi nhận ngày 24/10/2026:

- **FPT:** 5 năm 2021–2025 hợp nhất, chỉ có 8 đầu vào canonical: revenue, gross, net income, current assets, assets, liabilities, current liabilities, equity. Không có LCTT, phải thu, PPE, LTD, chi phí bán hàng/quản lý hoặc khấu hao trong mirror này. Công cụ giữ GMI/SGI và các tín hiệu F có thể tính, không dựng điểm đầy đủ.
- **VCB:** loại bank được nguồn xác nhận; annual 2021 có biên kỳ `0/0`, annual 2025 ghi `202501→202612` (24 tháng). Giữ payload và lý do từ chối; không sửa nhãn nguồn bằng phỏng đoán hoặc chọn năm cũ như thể báo cáo mới hợp lệ.
- KQKD/CDKT có `Unit=""`; quy đổi VND dựa hợp đồng request `Unit=1`, không phải response tự ghi đơn vị. Không nâng độ tin cậy đơn vị chỉ từ độ lớn con số.
- Payload và fixture chỉ có dữ liệu doanh nghiệp công khai, không có cookie/token/thông tin đăng nhập. Kiểm live provider không có nghĩa bản MCP đang deploy đã chứa code mới.

## Thứ tự và cách chia PR

Ưu tiên **P1: nguồn annual đầy đủ và công khai giới hạn**, sau đó **P2: kiểm cận bộ lọc và sửa FTD**. Metadata định giá/ratio, capability vốn hóa và cycle có thể làm song song thành PR độc lập. Chế độ PE hiện tại, nguồn market cap mới và mô hình ngành tài chính là năng lực mới, không phải điều kiện để thừa nhận năm lỗi gốc #44 đã được sửa.

## Phase 0 — Documentation Discovery và đóng băng bằng chứng

**How this serves the primary goal:** Mỗi thay đổi tiếp theo dùng đúng phiên bản API và phân biệt dữ liệu quan sát được với giả định nghiệp vụ.

**Đã thực hiện:** đọc code/test các phần còn lại và primary sources từ review; đối chiếu vnstock **4.0.2** với docs hiện hành v5. Khi bắt đầu mỗi PR, cập nhật HEAD và kiểm lại signatures/schema trước khi copy mẫu.

**Allowed APIs và nguồn:**

- `providers/forensic.py::annual_inputs/normalize_annual/select_annual_window/derive_quarter_cfo`; `providers/vietstock.py::financeinfo`, `financial_detail`, `financial_lctt`, `build_list_params`. `financial_detail` hiện request `PeriodType="QUY"`; không đoán giá trị endpoint năm.
- `providers/vnstock.py::_long_ratio_table/equity_ratios/equity_fundamentals/equity_quote_batch`; dependency 4.0.2 tại `vnstock/ui/domains/fundamental/equity.py`. [Docs v5](https://www.vnstocks.com/docs/vnstock/co-ban-fundamental) dùng để nhận biết khác biệt, không copy API v5 vào v4.
- `tools/market_timing.py::_follow_through`, `providers/technicals.py::compute`, `tools/cycle_stats.py::_major_troughs/_finalize_rest`, schema tại `dbinit.py`, freshness/transaction tại `tools/cycle_db.py`.
- [O’Neil + Co, slide 6](https://quantech2021.siat.org/wp-content/uploads/2021/05/Slide-speech-D_Aboville-William-O_Neil.pdf), [IBD Stock Guide Q1/2024 p18](https://marketsurge-files.investors.com/2024/02/StockGuide-Q1-2024.pdf), [TradingView Ichimoku](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/). Chưa có bằng chứng đầy đủ cho mọi ngoại lệ reversal, anchor Day 1 hoặc parity built-in offset25.

**Verification:** lưu fixture có ngày ghi nhận, nguồn, scope và đơn vị cho field mới; ghi rõ phần nào synthetic. **Anti-pattern guards:** không nâng major thư viện trong cùng PR sửa dữ liệu, không bịa tên method/norm_id/đơn vị.

## Phase 1 — Bổ sung nguồn annual đủ điều kiện chấm điểm

**How this serves the primary goal:** Đổi trạng thái từ “không đủ đầu vào” sang điểm đầy đủ bằng dữ liệu có căn cứ, không bằng cách nới điều kiện mô hình.

**What to implement:**

1. Đối chiếu báo cáo năm gốc của một doanh nghiệp thường với payload nguồn; tìm adapter annual chi tiết có receivables, net tangible/finance-leased PPE, LTD, SG&A, CFO và depreciation expense. Tái dùng API có thật; nếu endpoint năm chưa được chứng minh thì thu thập request/response hợp lệ trước khi viết adapter.
2. Với Piotroski, lấy **current portion of LTD** và tín hiệu phát hành equity tường minh. Không dùng toàn bộ short-term borrowing, biến động số cổ phiếu hay số vốn ròng để suy diễn. Chưa có nguồn thì giữ missing.
3. Mỗi input có report identity, khoảng kỳ, scope, revision status và unit basis. Chỉ ghép CFO qua nguồn khác khi đủ căn cứ cùng báo cáo; không nối thẳng bảng LCTT đang thiếu scope. Dùng helper YTD đã có khi metadata đủ, giữ precision trước khi hiển thị.
4. Điều tra metadata VCB annual lỗi bằng báo cáo gốc hoặc payload endpoint khác; không tự đổi `202612` thành `202512`. Bổ sung lỗi nguồn có cấu trúc để người dùng biết vì sao kỳ bị loại.
5. Nếu hoàn thiện registry placeholder, cần chứng cứ semantics từng provider/schema/item. Các hàng all-zero khác vẫn là số liệu; cờ nghi vấn và ghi chú phải đi xuyên bảng peer và cache.

**Documentation references:** `providers/forensic.py`, `forensic_models.py`, `tests/test_forensic_annual_inputs.py`, `tests/test_forensic_models.py`, hai fixture `financeinfo_*_annual_20261024.json`; định nghĩa công thức và nguồn paper trong review ban đầu.

**Verification checklist:** một annual golden từ báo cáo gốc khớp từng input và index; cùng company/scope/kỳ; DEPI dùng expense thật; không nhầm intangible PPE hoặc accumulated depreciation; thiếu mỗi input vẫn partial; đồng nhất cold/warm cache và tăng fingerprint các consumer bị đổi.

**Anti-pattern guards:** không đặt DEPI=0/1 ngầm, CFO=0, current LTD=0 hoặc “không phát hành” để làm score đầy đủ; không coi synthetic fixture là nguồn live; không suy quy mô VND/VNDbn từ magnitude đơn thuần.

## Phase 2 — Kiểm cận bộ lọc và capability không có dữ liệu

**How this serves the primary goal:** Điều kiện lọc không hợp lệ không biến thành “không giới hạn”, và nguồn không có metric không bị hiểu là thị trường không có mã phù hợp.

**What to implement:**

1. Chuẩn hóa cận range và các shortcut `max_pe/min_roe` trước enrichment/cache: `None` là cách duy nhất bỏ cận; từ chối NaN/±inf, bool và chuỗi không chuyển được thành số hữu hạn. Quy định tường minh `lo>hi` là lỗi. Giữ hai dạng no-op đã sửa.
2. Dùng cùng validator cho `apply_filters` trực tiếp và tool MCP; lỗi có thông báo chỉ rõ field/cận, không gọi nguồn hoặc lưu cache thành công.
3. Với `market_cap` ở long-format chưa có nguồn, trả capability/no-coverage rõ ràng và không tăng `evaluated`. Giữ giới hạn enrichment tối đa 30 mã được thể hiện trong coverage; không nói đã lọc toàn thị trường.

**Documentation references:** `providers/screener.py::_as_number/apply_filters`, `tools/scan.py::stock_screener`, `providers/vnstock.py::equity_fundamentals`, `tests/test_screener_followups.py`, `tests/contract/test_p2_screener.py`.

**Verification checklist:** NaN/inf/bool/string lỗi ở cả cận dưới/trên và shortcut; `lo>hi`; cận 0 và số âm tường minh; no-op/shortcut precedence; input lỗi không fetch/cache; market cap thiếu không tạo kết luận pass/reject giả.

**Anti-pattern guards:** không chỉ kiểm metric mà bỏ cận; không thay missing market cap bằng 0; không đổi quy tắc PE âm đã được công khai trong lúc sửa validator.

## Phase 3 — Sửa FTD và công khai quy ước Ichimoku

**How this serves the primary goal:** Một phiên thủng đáy trong ngày không giữ nhầm rally cũ, và người dùng biết tín hiệu được tính theo quy ước nào.

**What to implement:**

1. Sửa invalidation dùng intraday low. Tách invalidate → cập nhật trough → xét Day 1 → xác nhận; một phiên không vừa là Day 1 mới vừa là FTD. Giữ quy tắc không xác nhận Day 2/3 và loại nến phiên chưa đóng.
2. Trước khi thay anchor hoặc nhận reversal là Day 1, ghi đặc tả bằng ví dụ OHLC có nguồn: up-close/new-low, close-down nhưng hồi mạnh, equality tại đáy, attempt đã confirmed. Chưa đủ bằng chứng thì chỉ ship phần intraday invalidation đã chắc chắn và ghi giới hạn policy.
3. Giữ offset25 hiện tại, bổ sung `offset_bars`, convention và ý nghĩa giá quá khứ dùng đối chiếu chikou. Sửa lời khẳng định TradingView parity nếu chưa có export built-in. Classic26 là option riêng sau khi có reference fixture.

**Documentation references:** `market_timing.py::_follow_through`, `technicals.py::compute`, `scan.py::signals_technical`; `tests/contract/test_timing_rally_attempt.py`, `test_market_timing.py`, `tests/test_technicals_values.py`; primary sources phase 0.

**Verification checklist:** low thủng/close hồi; thay attempt cùng phiên theo policy đã chốt; confirmed attempt bị thủng; equality; Day4; market session đóng/mở; chuỗi không phẳng phân biệt25/26 và không look-ahead; đổi cache/version khi kết quả đổi.

**Anti-pattern guards:** không chỉ thay `elif`; không gọi mọi reversal là Day 1; không đổi default25 chỉ vì tài liệu văn bản nói26.

## Phase 4 — Metadata định giá và ratio theo quý

**How this serves the primary goal:** Người dùng phân biệt được giá hiện tại, EPS kỳ nào và bội số cuối kỳ, kể cả khi nguồn quý có cột lỗi.

**What to implement:** giữ nhãn lịch sử #46; thêm structured `price_as_of`, `eps_period`, unit/source/adjustment basis cho valuation hiện có. Giữ regex loại `2025-Q4_1` nhưng công khai nhãn đã bỏ và frequency/basis đã biết. Không tự annualize ROE quý. Trạng thái field và cờ nghi vấn phải đi xuyên projections/cache.

**Documentation references:** `compute_financial.py::valuation_run/financial_ratios/peer_compare`, `vnstock.py::_long_ratio_table/equity_fundamentals`, `tests/test_period_end_multiples.py`, `tests/test_financial_ratios_table.py`.

**Verification checklist:** historical PE không đổi; metadata EPS/giá khớp fixture; zero/âm EPS không chia; hệ số đơn vị ×1000 bị bắt; cột suffix không lọt vào tính; flag và nhãn còn sau cache hit.

**Anti-pattern guards:** không gọi EPS của annual default là TTM mới nhất năm2026; không thay giá trị lịch sử bằng bội số hôm nay dưới cùng field thiếu basis; không trỏ “PE hiện tại” tới tool chỉ có giao dịch.

## Phase 5 — Cycle có ngày xác nhận, YTD và cửa sổ đầy đủ

**How this serves the primary goal:** Người dùng không biến một đáy chỉ biết sau này thành tín hiệu sớm, hoặc so vài tuần dữ liệu với lợi nhuận ba tháng/năm hoàn chỉnh.

**What to implement:**

1. Giữ drawdown>15%, rebound>=20% và vượt running peak; thêm `rule_version`, thresholds, `confirmation_date`, `requires_future_data`. Không đổi tập event ngầm.
2. Bổ sung actual start/end/observations/completeness theo từng basket. Chốt “3M” là ba tháng lịch hay95 ngày trước khi đổi mẫu; >=20 phiên không tự chứng minh cửa sổ hoàn chỉnh. Quan sát thiếu phải bị tách hoặc gắn nhãn rõ.
3. Giữ năm hiện tại với `is_partial_year/data_through/period_basis`; ngày dựa dữ liệu thực của basket. Không trộn YTD vào thống kê full-year.
4. Migration trong `dbinit.py`, version/freshness và rebuild transaction đi cùng nhau; lỗi rebuild không stamp version. Dữ liệu cũ thiếu confirmation không được điền bằng trough date.

**Documentation references:** `cycle_stats.py::_major_troughs/_finalize_rest/cycle_yearly/cycle_trough_events`, `dbinit.py` schema cycle, `cycle_db.py::check_freshness/transactional`; `tests/test_cycle_asset_stats.py`, `tests/contract/test_cycle_hardening.py`.

**Verification checklist:** 100→80→97 không thuộc rule hiện tại; 100→80→101 có confirmation sau trough; basket thiếu phiên/cuối cửa sổ; năm đang chạy; migration fail không stamp; re-run không nhân đôi event; kiểm trên Postgres16 riêng.

**Anti-pattern guards:** không gọi bảng hindsight là backtest signal biết ngay tại đáy; không gắn nhãn đủ3M chỉ từ số dòng; không đổi rule mà giữ version cũ.

## Phase 6 — Verification và đóng issue theo bằng chứng

**How this serves the primary goal:** Mỗi PR được chấp nhận bằng hành vi thực tế; giới hạn dữ liệu và trạng thái triển khai không bị che bởi số test pass.

**What to implement:** chốt regression theo từng PR, cập nhật output/schema/docstring/hints/fingerprint cùng lúc. Giữ việc merge/deploy là bước riêng theo quyền được cấp; không tự đóng #39 vì mới sửa một nhóm công thức.

**Documentation references:** `.github/workflows/ci.yml`, `pyproject.toml`, tests từng phase; review ban đầu và báo cáo kiểm tra đợt đầu.

**Verification checklist:** Python3.12, `uv sync --frozen --extra dev`, Ruff và pytest đúng CI trên Postgres16 riêng, deselect riêng live matrix. Kiểm cold/warm cache và poisoned old-version cache khi đổi hợp đồng. Sau deploy được ủy quyền, lưu deployed SHA cùng response đã làm sạch cho general/bank/scope mix/zero và capability thiếu.

**Anti-pattern guards:** không dùng CI làm bằng chứng nguồn cung cấp đủ input; không dùng live provider làm bằng chứng deployment đã cập nhật. #44 có thể đóng khi năm sửa gốc đã deploy; #39 cần disposition rõ cho từng mục, phần năng lực mới được theo dõi riêng.

## Hoãn thành năng lực riêng

Forensic riêng ngành tài chính · hiệu chuẩn threshold trên dữ liệu VN · canonical TTM/quarterly forensic · imputation có opt-in · default Ichimoku khác · định nghĩa trough mới · `pe_basis="current_ttm"` sau khi chứng minh EPS mới nhất/cơ sở điều chỉnh · nguồn market cap mới sau fixture timestamp/unit/outstanding shares · nâng vnstock v5 · thay đổi repo OpenTrading ngoài workspace.
