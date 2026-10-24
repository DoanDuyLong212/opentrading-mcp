# Ichimoku: 25-bar vs 26-bar cloud offset — evidence note (25/10/2026)

Câu hỏi #39: code dùng 25; tài liệu TradingView diễn đạt 26. Vấn đề là **quy ước mapping**, không phải lỗi tính:

## Hai cách đọc cùng một biểu đồ

- **Classic (26)**: senkou A/B tính tại bar N được vẽ `displacement + 26` phía trước (`shift(26)`); chikou = close của N vẽ lùi 26. Cloud thấy tại N được tính từ N−26.
- **Code hiện tại (25)**: cloud tại N = spans tính từ **25 completed bars** trước (`technicals.py:220-223`) — tương đương "displacement − 1": bar chạy đời (forming bar) không được tính là completed.

Hai quy ước lệch nhau đúng **1 bar**; không đổi giá trị trung bình/đỉnh-đáy, chỉ đổi bar neo.

## Nguồn

- TradingView Ichimoku docs: "spans plotted `displacement` periods ahead", displacement = 26.
- IBD/O'Neil không liên quan. Không có export built-in của TradingView để đối chiếu output từng bar (theo plan #39/44: "không gọi compatibility TradingView là đã kiểm chứng nếu chưa có output built-in").

## Kết luận

Giữ mặc định 25 (tương thích kết quả đã phát hành, có `convention`/`offset_bars` trong output từ #48). Chuyển sang 26 chỉ khi: (1) reviewer chốt, và (2) có fixture export từ một chart tham chiếu để đối chiếu từng bar — thuộc Phase 5 backlog #51. Đây là lựa chọn version-hoá, không phải bản sửa lỗi.
