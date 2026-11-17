# Changelog

Ghi các thay đổi **hợp đồng công khai** (tool schema, thứ tự/đơn vị dữ liệu) để
client, prompt và skill bên harness kiểm tra lại. Mọi thay đổi ở đây đều bump
fingerprint cache tương ứng, nên entry cache cũ không quay lại.

## 2026-11-17

### Quant tools: không bao giờ tự tạo ngày (#137)

Trước đây một nến thiếu ngày (`t` chỉ chứa số phiên) khiến **toàn chuỗi** bị
đổi nhãn thành walk-back ngày làm việc kết thúc **hôm nay** — month filter,
seasonality, correlation và event study chạy trên lịch bịa. Hợp đồng mới:

- Không tool nào phát minh ngày. Bar không ngày được **bỏ/k-report** rõ ràng.
- `backtest_strategies` / `param_sweep`: `date_basis` giờ là `observed` hoặc
  `missing` (hết `inferred`); bar không ngày **không bao giờ** thoả month/quarter
  filter — đếm trong `undated_bars_blocked`, kèm warning; availability `partial`.
- `correlation_matrix` / `portfolio_optimize`: bar không ngày bị loại khỏi phép
  join (không còn "business-day walkback (approx)" trong `date_note`).
- `seasonality`: bỏ bucket cho window-end không ngày; hết ngày → `unavailable`.
- `event_study`: map chỉ nhận ngày thật; benchmark không ngày → raw returns +
  warning.
- Condition asset (yfinance) không có ngày dùng được → `unavailable`, không còn
  fallback "hôm nay".
- Cache: `backtest_strategies` v3, `param_sweep` v3, `correlation_matrix` v2,
  `seasonality` v2, `portfolio_optimize` v2, `event_study` v2.

### Ngày thị trường theo giờ VN, không theo giờ container (#136)

Thêm `opentrading_mcp.vn_time` (offset cố định +07:00, không cần tzdata).
Mọi nhãn ngày thị trường — cửa sổ request nến/macro, ngày snapshot, độ tươi
cycle, cutoff corp/intel/event, hạn release — lấy từ `vn_today()` thay vì
`date.today()` của container UTC. Timestamp quốc tế (`fetched_at`, HTTP Date)
vẫn là UTC. Layout `date.today()` cũ trả lệch ngày sau 17:00 UTC (00:00 VN).

### financial_ratios / financial_statements / vn_fundamentals / peer_compare — một thứ tự kỳ (#140)

- `periods` giờ luôn **cũ → mới** ở cả bốn tool (trước đây `financial_ratios`,
  `vn_fundamentals` và `peer_compare` trả **mới → cũ**).
- Thêm `latest_period` (và `period_order: "oldest_to_newest"`) cho
  `financial_ratios` và `vn_fundamentals`: đọc kỳ mới nhất bằng field này thay vì
  `periods[0]`.
- `peer_compare` / peers của `financial_ratios`: `period_label` vẫn là **kỳ mới
  nhất có số** của mã đó (không phải kỳ mới nhất rỗng); `equity_fundamentals`
  công bố thêm `latest_period` tách khỏi `period_label`.
- Cache: `financial_ratios` v9→v10, `peer_compare` v9→v10, `vn_fundamentals`
  v4→v5.
- **Việc cần làm ở harness:** rà prompt/skill đang lấy `periods[0]` làm kỳ mới
  nhất. Snapshot benchmark đóng băng trước ngày này vẫn giữ thứ tự cũ — so sánh
  với chúng phải chuẩn hoá thứ tự trước.
