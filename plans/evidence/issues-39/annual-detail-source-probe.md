# Annual detail source — LIVE probe kết luận (25/10/2026)

Câu hỏi #51 Phase 0–1: nguồn annual chi tiết (receivables, PPE, LTD, SG&A, depreciation, CFO) có tồn tại qua API có thật không? **CÓ — chuỗi detail hiện hữu chấp nhận `PeriodType: "NAM"`.**

## Recipe đã kiểm chứng live (FPT, read-only, không lưu credential)

1. Norms: `POST /data/GetListReportNormByStockCode {"stockCode": "FPT"}` → 143 dòng CDKT đầy đủ (tên + ReportNormId, kèm `ParentReportNormID`).
2. Periods: `POST /data/CDKT_GetListReportData {**_DETAIL_FILTER, PeriodType: "NAM"}` → **24 kỳ annual (2002–2025, ReportTermID=1)**, có `ReportDataID`, `UnitedName/UnitedId`, `IsShowData_Permission`.
3. Values: `POST /data/GetReportDataDetailValueByReportDataIds {StockCode, Unit: 1e9, TypeCompare: "1", listReportDataIds[i][Index/ReportDataID/YearPeriod/ReportTermID]}` → mỗi norm một row với `Value1..ValueN` theo kỳ batch (kèm `ValuePrev*`).
4. KQKD tương tự: `GetListReportNorm_KQKD_ByStockCode` + `KQKD_GetListReportData` + `GetReportDataDetailValue_KQKD_ByReportDataIds` → **25 dòng** gồm đủ 9. Chi phí bán hàng + 10. Chi phí quản lý doanh nghiệp (SG&A).
5. LCTT annual: đã chứng minh từ #40 (`build_list_params(full=True)`) — CFO + khấu hao expense theo năm.

## Mapping Beneish/Piotroski → dòng nguồn (FPT fixture)

| Input model | Dòng CDKT/KQKD/LCTT annual | NormID (FPT) |
|---|---|---|
| receivables | "III. Các khoản phải thu ngắn hạn" (+ dài hạn) | 3005 |
| gross PPE | "1. TSCĐ hữu hình — Nguyên giá" (+ thuê tài chính, vô hình, BĐS đầu tư) | 3083/3085/3087/3039 |
| accumulated depreciation | "— Giá trị hao mòn lũy kế" | 3084 |
| LTD | "9. Vay và nợ thuê tài chính dài hạn" | 3078 |
| current liabilities | "I. Nợ ngắn hạn" (tổng) | 3014 |
| SG&A | "9. Chi phí bán hàng" + "10. Chi phí quản lý doanh nghiệp" (KQKD) | — |
| depreciation expense | LCTT annual (dòng khấu hao TSCĐ) | — |
| CFO | LCTT annual (dòng tiền thuần HĐKD) | — |
| total assets | "TỔNG CỘNG TÀI SẢN" = 60,283 → 72,000 → 88,142 (2023–2025) ✓ khớp thực tế | 2996 |

Values đã ở **VND tỷ** (Unit=1e9 theo hợp đồng request; response không tự ghi đơn vị — caveat đã ghi ở annual-source-validation.md vẫn đúng).

## Lưu ý cho adapter (Phase 1)

- Map theo **tên chuẩn hóa** (đã bỏ dấu, lowercase) chứ không theo NormID — danh sách norm trả theo từng mã, ID có thể khác giữa các công ty.
- Scope: dùng `_report_scope` như quarterly; basis observed = `UnitedName` (giá trị "***" từ upstream — không tự suy consolidated, giữ trạng thái unknown theo hợp đồng).
- KQKD annual chỉ 25 dòng (bảng rút gọn hơn CDKT) — SG&A đủ, nhưng profit lines cần kiểm trùng "Lợi nhuận sau thuế TNHH" tổng/mẹ như #36/#45.
- Unit per-row vẫn blank từ upstream — quy ước Unit=1e9 giữ nguyên contract hiện hành.

Fixtures: `fpt-{cdkt,kqkd,lctt}-annual-20261025.json` (sanitized, không chứa auth).
