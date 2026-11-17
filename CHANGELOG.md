# Changelog

Ghi các thay đổi **hợp đồng công khai** (tool schema, thứ tự/đơn vị dữ liệu) để
client, prompt và skill bên harness kiểm tra lại. Mọi thay đổi ở đây đều bump
fingerprint cache tương ứng, nên entry cache cũ không quay lại.

## 2026-11-17

### `/readyz` công khai chỉ trả `ok` + status code (#146)

Trước đây `/readyz` không cần token vẫn trả toàn bộ component report
(`detail` có thể chứa hostname/thông báo driver). Giờ client không token chỉ
nhận `{"ok": …, "status": …}` và status code (host readiness không cần gì hơn);
report đầy đủ vẫn lấy được qua `/readyz?full=1` hoặc `/healthz?full=1` với token.

### `quant_risk` — cache key hash, không còn list returns thành Redis key (#145)

Fingerprint của `quant_risk` là `v2|sha256(json([returns, periods_per_year]))`
trước đây là chuỗi hoá toàn bộ list returns — key lớn đổ thẳng vào Redis.
Giá trị cache cũ theo key cũ tự hết hạn; không cần hành động gì phía client.
