# Kế hoạch xử lý review PR #26–#35 để sẵn sàng merge

## Primary goal

Người dùng nhận được số liệu breadth không đánh đồng thiếu dữ liệu với 0, phạm vi screener đúng với số mã được kiểm tra, và bảng ratios giữ nguyên số 0 hợp lệ. Ba phát hiện P2 được sửa ngay trong PR #27, #30, #33; cả chuỗi #26 → #35 có bằng chứng kiểm thử đủ để chuyển sang bước merge.

Trạng thái tài liệu: kế hoạch thực hiện, chưa áp dụng bản sửa hoặc merge PR. Ngày lập: 23/10/2026, giờ Asia/Bangkok.

## Mốc đã xác minh

- Review gốc: [báo cáo chi tiết](/home/doanlong/.codex/visualizations/2026/10/23/01a16740-628a-7d20-b8be-f1cbe6a69691/pr-26-35-review.md).
- Base khi review: `c2442cc8c1d449999031855d91bb226b89d00567`.
- Head #27: `f06c2495bd741daee043bf55c0cc1a0c2d81d64a`.
- Head #30: `f58f73294fb4d7464d08b9c498f5a75030b44cc7`.
- Head #33: `31ddaa0e1d02121c313f3e7325dd9c2f62dcd045`.
- Đọc lại GitHub trong lượt lập kế hoạch: #27, #30, #32, #33, #35 còn mở; head chưa đổi. #32 vẫn dựa trên nhánh #26; #33 vẫn dựa trên nhánh #28; #35 dựa trên main.
- Bản ghép cũ theo thứ tự #26 → #35: không conflict, Ruff pass, 477 test pass với Postgres 16; 1 live matrix bị deselect giống CI.
- Ba test tái hiện độc lập đang fail: [review_regressions.py](/home/doanlong/.codex/visualizations/2026/10/23/01a16740-628a-7d20-b8be-f1cbe6a69691/review_regressions.py).
- Các kết quả trên là baseline trước sửa, không dùng làm bằng chứng CI cho commit sẽ được tạo.

## Phase 0 — Đọc nguồn và chốt hợp đồng hành vi

**How this serves the primary goal:** Chốt nghĩa của null, số mã đã kiểm tra và số 0 trước khi viết mã, tránh sửa một triệu chứng nhưng tạo ra cách hiểu sai mới.

Đã hoàn tất phần khám phá bằng hai tác vụ thu thập nguồn độc lập và đọc đối chiếu. Trước triển khai, đọc lại AGENTS.md áp dụng trong checkout và kiểm tra head/base mới nhất; nếu SHA đổi, đọc phần diff phát sinh trước khi tiếp tục. Dùng checkout/worktree riêng cho các nhánh hiện có, bảo toàn file chưa commit của người dùng.

### Allowed APIs và nguồn đã đọc

| API/pattern có thật | Nguồn |
|---|---|
| `_board_breadth(exchange: str, raw: Any) -> dict[str, Any] \| None`; `_breadth_totals(boards: list[dict[str, Any]]) -> dict[str, Any]` | [PR27 market.py:287–310](https://github.com/DoanDuyLong212/opentrading-mcp/blob/f06c2495bd741daee043bf55c0cc1a0c2d81d64a/src/opentrading_mcp/tools/market.py#L287-L310) |
| Cả live và snapshot breadth dùng chung helper tổng | [PR27 market.py:804–890](https://github.com/DoanDuyLong212/opentrading-mcp/blob/f06c2495bd741daee043bf55c0cc1a0c2d81d64a/src/opentrading_mcp/tools/market.py#L804-L890) |
| `stock_screener(filters=None, max_pe=None, min_roe=None, limit=20, technical=None)` và giới hạn gọi provider | [PR30 scan.py:51–211](https://github.com/DoanDuyLong212/opentrading-mcp/blob/f58f73294fb4d7464d08b9c498f5a75030b44cc7/src/opentrading_mcp/tools/scan.py#L51-L211) |
| `apply_filters(rows, filters) -> list[dict[str, Any]]`: lọc local; missing numeric bị loại | `src/opentrading_mcp/providers/screener.py:84` trong checkout PR30 |
| `technicals.compute(candles, benchmark=None) -> dict[str, Any]`; indicator có thể None sau #29 | [PR29 technicals.py:66](https://github.com/DoanDuyLong212/opentrading-mcp/blob/903e478c883dc047f6869e005cbcdc2d001713e6/src/opentrading_mcp/providers/technicals.py#L66) |
| `_long_ratio_table(frame) -> tuple[list[str], list[dict[str, Any]]] \| None`; `equity_ratios(symbol, period="year")` | [PR33 vnstock.py:637–698](https://github.com/DoanDuyLong212/opentrading-mcp/blob/31ddaa0e1d02121c313f3e7325dd9c2f62dcd045/src/opentrading_mcp/providers/vnstock.py#L637-L698) |
| Provider call hiện có: `Fundamental().equity(symbol.upper()).ratio(period=period)` | [PR33 vnstock.py:691](https://github.com/DoanDuyLong212/opentrading-mcp/blob/31ddaa0e1d02121c313f3e7325dd9c2f62dcd045/src/opentrading_mcp/providers/vnstock.py#L691) |
| `cache_lookup`, `cache_store`, `run_blocking`, `blocking_slots` | `src/opentrading_mcp/tools/shared.py`; giữ cách gọi đang có trong các tool |
| Mẫu mock/fixture/envelope và CI | Các test dẫn ở từng phase; [CI:19–43](https://github.com/DoanDuyLong212/opentrading-mcp/blob/42430003dc8bc071ec393b9a7694bd2d17d23c61/.github/workflows/ci.yml#L19-L43) |

Không cần thư viện, endpoint, tham số SDK hoặc public tool mới. Helper nội bộ mới, nếu cần, phải được định nghĩa rõ trong thay đổi.

### Quyết định chốt

1. Tổng breadth chỉ biết khi các sàn được đưa vào tổng có số liệu cho trường đó.
2. `screened` đếm số mã đã thử đánh giá tại bước lọc cuối đang hoạt động; bổ sung metadata phân biệt thử đánh giá và đánh giá được.
3. Mọi số 0 hữu hạn trong bảng ratios được bảo toàn. Fixture all-zero không đủ chứng minh đó là placeholder.
4. Cập nhật ngay ba PR hiện có; không tạo một PR sửa chồng lên cả chuỗi.

**Verification checklist:** xác nhận SHA/base; đọc các nguồn trên; ghi rõ hợp đồng và cache version trong mô tả sửa; đưa ba repro vào bộ test của đúng PR.

**Anti-pattern guards:** không coi metadata mergeable hoặc CI cũ là bằng chứng bản sửa đúng; không viết lại fixture để che lỗi; không mặc định tmp snapshot còn mới.

## Phase 1 — Sửa breadth trong PR #27

**How this serves the primary goal:** Người đọc phân biệt được số mã thực sự bằng 0 với trường nguồn chưa cung cấp, và không nhận tỷ lệ tăng giá tính từ mẫu số thiếu.

### What to implement

- Sao chép mẫu `_fake_boards` và `_tool_fn` từ `tests/contract/test_market_breadth.py:27–51`; mở rộng test missing-field ở :143–149 trước khi sửa.
- Giữ chữ ký `_breadth_totals`. Cộng từng trường khi danh sách không rỗng và mọi board có giá trị khác None cho trường đó; nếu không, trả None.
- Chỉ tính `advancers_pct` khi ba tổng advancers/decliners/unchanged đều biết và mẫu số lớn hơn 0. Ba tổng đều 0 vẫn giữ 0; tỷ lệ khi mẫu số 0 là None.
- Cảnh báo cụ thể sàn/trường thiếu. Kết quả live có trường thiếu mang availability=partial; snapshot vẫn availability=stale và thêm cảnh báo.
- Giữ hành vi một sàn lỗi: tổng của các sàn thực sự trả về, có danh sách exchanges và cảnh báo/partial hiện hữu. Không ngầm đưa sàn vắng vào tổng với giá trị 0.
- Dùng cùng quy tắc cho live và snapshot.
- Nâng fingerprint breadth_scan từ `v2|` lên `v3|`, cùng giá trị cho lookup/store, để cache cũ không che bản sửa.

### Documentation references

- Hàm và hai đường gọi: market.py:287–310, 804–890 ở nguồn Phase 0.
- Test fallback: `tests/contract/test_market_breadth.py:102–121`.
- Test partial exchange: cùng file :91–101.

### Verification checklist

- Thiếu upc/dnf: cả board và top-level ceiling/floor là None.
- Thiếu st: unchanged và advancers_pct là None.
- Nhiều sàn, một sàn thiếu một trường: chỉ tổng trường đó là None, các tổng đủ dữ liệu vẫn đúng.
- Số 0 thật, trường None và chuỗi không parse được đều được phân biệt.
- Snapshot thiếu trường tuân cùng hợp đồng và giữ trạng thái stale.
- Case đủ dữ liệu và case một sàn lỗi hiện có vẫn pass.
- Cache cũ không được dùng; cache mới bảo toàn null và warnings.
- Chạy focused test: `uv run pytest tests/contract/test_market_breadth.py -q`.

**Anti-pattern guards:** không dùng `value or 0` để cộng dữ liệu thiếu; không tính tỷ lệ trên mẫu số biết một phần; không đổi timeout/concurrency/provider trong phase này.

## Phase 2 — Sửa phạm vi screener trong PR #30

**How this serves the primary goal:** Người dùng biết rõ bao nhiêu mã đã được đưa vào bước lọc cuối, bao nhiêu mã đủ dữ liệu để đánh giá, và các kết quả bị giới hạn ở đâu.

### What to implement

- Sao chép pattern mock listing/fundamentals từ `tests/contract/test_alert_check_rules.py:111–127`; chuyển repro 40 mã/limit=5 thành regression test trong repo.
- Giữ nguyên giới hạn enrichment, semaphore, 250 nến RSI và thứ tự lọc hiện có. Không đổi sang quét toàn thị trường hoặc đưa prefilter lên trước enrichment trong bản sửa này.
- Chuẩn hóa `technical={}` thành không có bước lọc kỹ thuật; không fetch history chỉ vì dict rỗng.
- Giữ `universe=len(listing)`.
- Chốt `screened` là số mã attempted tại bước cuối có hoạt động:
  - Có technical không rỗng: số mã trong technical shortlist đã thử kiểm tra.
  - Không technical, có valuation filter: số mã được đưa vào bước kiểm tra fundamentals cần cho filter.
  - Không hai bước trên: số dòng được kiểm tra bằng filter local.
- Bổ sung object `coverage` chỉ mô tả bước cuối:
  - `stage`: local, fundamentals hoặc technical.
  - `eligible`: số mã có thể đi vào bước này trước khi áp giới hạn.
  - `attempted`: số mã đã thử kiểm tra; bằng screened.
  - `evaluated`: số mã đủ input để có kết luận pass/reject.
- Với technical, eligible lấy từ candidates sau các filter trước đó, không lấy universe. Các cảnh báo giới hạn fundamentals hiện có tiếp tục thể hiện phạm vi của bước trước.
- Phân biệt kết quả nội bộ pass/reject/unavailable. Một mã không đạt RSI/SMA là reject hợp lệ; history lỗi, compute lỗi hoặc indicator bắt buộc None là unavailable.
- Thêm warning khi attempted < eligible, nêu đúng số và bước lọc. Giới hạn chủ ý chỉ thêm warning; dữ liệu lỗi/thiếu thật mới đánh dấu partial, giữ hợp đồng test hiện hữu.
- Với lỗi đánh giá, warning nêu mã và lý do; evaluated không tăng; không coi đó là một kết quả filter=false bình thường.
- Nâng stock_screener fingerprint hiện chưa có version thành `v2|`; tính fp một lần rồi dùng lại cho lookup và store.
- Bổ sung docstring cho screened/coverage và cập nhật mô tả PR.

Ví dụ hợp đồng:

```json
{
  "universe": 40,
  "screened": 5,
  "coverage": {
    "stage": "technical",
    "eligible": 40,
    "attempted": 5,
    "evaluated": 4
  }
}
```

Ví dụ trên có một mã không đánh giá được nên availability=partial; warning đồng thời nêu giới hạn 5/40 và lỗi của mã đó. Nếu cả 5 đánh giá được nhưng đều không đạt filter, evaluated=5 và không coi là lỗi dữ liệu.

### Documentation references

- `scan.py:99–141`: enrichment và warning hiện có.
- `scan.py:143–210`: candidates, shortlist, xử lý technical và output.
- `tests/contract/test_p6_u1.py:19–55`: technical và invalid rule.
- `tests/contract/test_alert_check_rules.py:127`: giới hạn 20/40 không tự mang partial.

### Verification checklist

| Case | Kết quả bắt buộc |
|---|---|
| 40 mã, technical, limit=5 | 5 history calls; screened=attempted=evaluated=5; eligible=40; warning giới hạn |
| Valuation + technical | Giới hạn fundamentals giữ nguyên; screened theo technical; warning từng bước đúng mẫu số |
| Prefilter còn 3 candidates | Technical eligible=3; không báo kiểm tra kỹ thuật cả 40 mã |
| technical=None và {} | Cùng hành vi; không gọi history |
| 5 mã đều không đạt filter | evaluated=5; không warning lỗi dữ liệu |
| 1/5 history lỗi, compute lỗi hoặc indicator thiếu | attempted=5, evaluated=4; warning theo mã; partial |
| Không có candidates | Các count technical là 0; không gọi history |
| Valuation-only 20/40, input đầy đủ | screened=20; warning giới hạn; không partial chỉ vì giới hạn |
| Cache hit | Giữ đúng coverage, warnings và availability |

Chạy focused: `uv run pytest tests/contract/test_alert_check_rules.py tests/contract/test_p2_screener.py tests/contract/test_p6_u1.py -q`.

**Anti-pattern guards:** không đếm len(rows) cho bước technical; không gộp lỗi dữ liệu vào reject; không sửa alert/cross-rule semantics; không thay candidate pool/thứ tự enrichment ngoài phần dict rỗng đã chốt.

## Phase 3 — Giữ số 0 hợp lệ trong PR #33

**How this serves the primary goal:** financial_ratios và peer_compare giữ được giá trị do nguồn trả về, không biến một tỷ suất bằng 0 thành một ô dữ liệu thiếu theo suy đoán.

### What to implement

- Sao chép test parser/table và mock tool từ `tests/test_financial_ratios_table.py:29–49`; thêm regression parser trước khi sửa.
- Bỏ phép đổi toàn bộ hàng all-zero thành None tại `providers/vnstock.py:669–670`.
- Giữ logic chuyển từng ô unparseable, NaN và ±Infinity thành None ở :662–668. Giữ mọi số hữu hạn, gồm 0 và "0".
- Cập nhật docstring parser và tool; không suy diễn ý nghĩa thiếu dữ liệu chỉ từ numeric zero.
- Sửa assertion ở `tests/test_financial_ratios_table.py:61–62`: annual roe_trailling trong fixture được giữ dưới dạng 0 đúng quan sát nguồn.
- Không sửa fixture gốc. Fixture annual all-zero và quarterly nonzero chứng minh cần giữ kỳ; không chứng minh quy tắc placeholder.
- Nâng fingerprint financial_ratios và peer_compare từ `v2|` lên `v3|`; lookup/store dùng chung fp để cache null cũ không tồn tại dưới nghĩa mới.
- Giữ chữ ký, period order, metric aliases và output shape.

### Documentation references

- Parser và provider: vnstock.py:637–698 ở Phase 0.
- Fingerprint: [compute_financial.py:493](https://github.com/DoanDuyLong212/opentrading-mcp/blob/31ddaa0e1d02121c313f3e7325dd9c2f62dcd045/src/opentrading_mcp/tools/compute_financial.py#L493) và [:559](https://github.com/DoanDuyLong212/opentrading-mcp/blob/31ddaa0e1d02121c313f3e7325dd9c2f62dcd045/src/opentrading_mcp/tools/compute_financial.py#L559).
- Fixture: `tests/fixtures/vnstock_ratio_fpt_20261023.json:52–58,110–116`.
- Tool tests: `tests/test_financial_ratios_table.py:52–89`.

### Verification checklist

- Toàn 0, một kỳ 0, zero xen None/NaN và chuỗi "0": zero vẫn là 0.
- Dòng thiếu toàn bộ hoặc có giá trị không hữu hạn: các ô tương ứng là None.
- Annual và quarterly có cùng item_id không ảnh hưởng nhau.
- financial_ratios và peer_compare đều trả 0 đúng, gồm cache hit.
- Order kỳ, bỏ cột hậu tố _1, aliases và cảnh báo metric thiếu không đổi.
- Chạy: `uv run pytest tests/test_financial_ratios_table.py tests/test_vnstock_fundamentals_candles.py tests/contract/test_p5_compute_params.py -q`.

**Anti-pattern guards:** không thêm allowlist item_id khi chưa có chứng cứ nguồn; không dùng truthiness để phân biệt 0/None; không mở rộng sang cách equity_fundamentals của #28 xử lý zero trong phase này.

## Phase 4 — Kiểm chứng tích hợp và chốt sẵn sàng merge

**How this serves the primary goal:** Chứng minh ba bản sửa đúng khi đi cùng toàn bộ chuỗi PR và không phá các chức năng đã review, trước khi chuyển sang thao tác merge thật.

### What to implement

- Mỗi lỗi có commit và regression tests trong đúng PR gốc #27/#30/#33; cập nhật mô tả PR với hành vi mới, cache version và lệnh kiểm chứng.
- Kiểm tra lại diff từng PR: không lẫn thay đổi của PR khác hoặc file người dùng chưa commit.
- Dựng bản ghép mới từ main hiện tại, không tái sử dụng kết quả 477 test cũ làm bằng chứng cho code mới.
- Ghép thử theo thứ tự #26 → #35, giữ quan hệ #26 → #32 và #28 → #33.
- Chạy ba regression đã đưa vào repo trước; sau đó chạy toàn suite với Python 3.12 và Postgres 16 tạm theo CI.
- Lưu SHA của main, head từng PR và bản ghép, kết quả lint/test và danh sách test deselect/skip kèm lý do.
- Khi triển khai được yêu cầu và bản sửa đã push: kiểm tra GitHub CI trên head SHA mới, trạng thái review/conversation và conflict mới trước khi kết luận READY.

### Documentation references

CI chính thức: `.github/workflows/ci.yml:19–43` ở Phase 0. Các file giao nhau phải kiểm tra tích hợp: compute_financial.py (#26/#28/#32/#33), scan.py (#29/#30), vn.py và quant_backtest.py (#28/#34).

```bash
uv sync --frozen --extra dev
uv run ruff check src tests
uv run pytest -q -p no:cacheprovider --deselect tests/contract/test_verify_matrix.py::test_full_matrix_stdio
```

Thiết lập TEST_DATABASE_URL vào DB tạm, VNSTOCK_TELEMETRY=off, MPLBACKEND=Agg như CI. Không dùng DB thật. Live matrix chỉ được deselect đúng test đã nêu; các test finalize cần DB phải thực sự chạy.

### Verification checklist / Definition of ready

- Ba regression cũ chuyển từ fail sang pass; các case mở rộng của từng phase pass.
- Ruff sạch; toàn bộ test đang có và test mới pass, không skip test DB vì thiếu môi trường.
- Bản ghép #26–#35 không conflict và không bỏ bản sửa khi hợp nhất file chung.
- CI mới xanh đúng head đã kiểm tra của từng PR cần cập nhật.
- Không có review thread hoặc CI failure cần hành động còn chưa xử lý.
- Ba lỗi được đánh dấu đã giải quyết bằng test và vị trí commit, không chỉ bằng lời mô tả.
- Kết quả bàn giao có bảng PR/commit/CI/test/dependency và trạng thái READY hoặc việc cụ thể còn lại.

### Trình tự merge khi chuyển sang bước merge

1. Merge theo số #26, #27, #28, #29, #30, #31, #32, #33, #34, #35 sau khi từng PR đạt gate ở trên.
2. Sau #26: đưa #32 về main và kiểm tra diff chỉ còn thay đổi forensic. Sau #28: làm tương tự với #33, diff chỉ còn ratios và bản sửa zero.
3. Nếu parent được squash/rebase khi merge, xử lý lịch sử stacked branch có chủ ý để không đưa lại commit parent. Đối chiếu patch và chạy lại test liên quan; không mặc định đổi base là đủ.
4. Sau mỗi parent merge hoặc cập nhật main ảnh hưởng file chung: kiểm tra CI trên merge candidate mới. Nếu có xung đột, resolve rồi xác minh lại phần bị ảnh hưởng.
5. Báo cáo READY trong kế hoạch này không tự thực hiện merge hay deploy.

**Anti-pattern guards:** không dựa vào CI của SHA cũ; không bỏ Postgres tests; không dùng kết quả merge thử cũ sau khi head/base đã đổi; không force-push mù hoặc đưa commit parent trùng vào PR con.

## Ngoài phạm vi đợt xử lý này

- Quét fundamentals toàn thị trường, tăng quota hoặc đổi thứ tự prefilter/enrichment.
- Đổi phương pháp Beneish/Piotroski, công thức chỉ báo hoặc nội dung những PR chưa có phát hiện.
- Tự quy định zero-placeholder của upstream khi chưa có bằng chứng.
- Refresh/finalize dữ liệu production, deploy hoặc merge thật trong lượt chỉ lập kế hoạch.

