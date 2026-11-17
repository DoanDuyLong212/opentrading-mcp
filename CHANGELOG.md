# Changelog

Ghi các thay đổi **hợp đồng công khai** (tool schema, thứ tự/đơn vị dữ liệu) để
client, prompt và skill bên harness kiểm tra lại. Mọi thay đổi ở đây đều bump
fingerprint cache tương ứng, nên entry cache cũ không quay lại.

## 2026-11-17

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
