# 10 — F13 pricing basis: primary-source research (Wave 4)

Finding F13 [khuyến nghị] concerns the pricing/valuation basis assumptions
flagged in the initial review (GLD/spot, fees, VN30 calendar). This memo
adds the primary-source picture for the **M-score threshold** question that
F06/F13 raise, because it decides what the tool may claim.

## The −1.78 cutoff is US-calibrated and must stay labeled as such

- Beneish (1999) derived −1.78 on US data; the model's use here is a
  screening reference, and the tool already labels it
  (`cutoff: -1.78`, flag text: "further review warranted; not a fraud
  conclusion") — this labeling is correct and must not change to a
  "VN-calibrated" claim without new calibration work.

## Vietnamese calibration literature exists (model FITS, thresholds differ)

| Nguồn | Mẫu | Kết quả liên quan trực tiếp |
|---|---|---|
| Nguyen Huu Anh & Nguyen Ha Linh (2016), VNU J. Economics & Business 1287 | 229 CTCP phi tài chính HOSE 2013–14 | 48.4% có earnings management; quan sát **fit** mô hình Beneish |
| Nguyen Huu Anh, Nguyen Ha Linh & Sung Wook Yoon (2018), Accounting & Taxation 10(1):39–49 (SSRN 3203061) | 468 CTCP phi tài chính HOSE+HNX 2013–14 | 40% EM; mô hình fit; đề xuất làm benchmark VN |
| Le Thi Huong Tram, Nguyen Thuy Vinh, Le Thi Xuan Huong (2023), IJEFM v6i6/57 | 1 doanh nghiệp điển hình, unaudited | M-score có **xác suất nhận diện sai cao** ở VN; khuyến nghị kết hợp công cụ khác |
| Bui Phuong Chi et al., RSU journals (HNX 100 firms) | 100 DN HNX | TATA, GMI, SGI, DSRI là thành phần ảnh hưởng phát hiện |

## Critical counter-evidence (2026)

**Martens, W. (2026), "The IFRS Paradox: Audit Quality, Not Manipulation
Scores, Prices Reporting Risk in Frontier Markets", JRFM 19(5):321 (MDPI)**
— nghiên cứu có hệ thống đầu tiên kiểm tra M-Score/Dechow F-Score nhưreturn
predictors trên dữ liệu VN (system GMM, panel FE, Fama–MacBeth): tín hiệu
không còn ý nghĩa sau fixed effects; **audit quality (Big Four) mới là kênh
governance có premium**. Kết luận cho tool: M-score ở VN là **screening
reference**, không phải pricing signal.

## Decisions for the tool (applied)

1. Giữ cutoff −1.78 với nhãn rõ (đã có trong `forensic_models.py`).
2. KHÔNG đổi ngưỡng theo các nghiên cứu VN (chúng xác nhận model fit, không
   xuất bản ngưỡng thay thế có holdout).
3. TODO [khuyến nghị, wave sau]: phát hành trường `threshold_basis:
   "US-1999 reference; VN calibration pending"` vào payload để consumer
   không thể hiểu nhầm — chờ review nghiệp vụ.
4. Pricing-basis assumptions khác (GLD/spot, phí, VN30 calendar) giữ trạng
   thái [khuyến nghị] như 02 §3 — mỗi mục cần nguồn sàn/nguồn giá trước khi
   thay đổi code.

## Nguồn

- VNU J: https://js.vnu.edu.vn/EAB/article/view/1287
- SSRN 3203061 / Accounting & Taxation 10(1):39–49 (2018)
- IJEFM v6i6/57 (2023)
- Martens (2026) JRFM 19(5):321: https://www.mdpi.com/1911-8074/19/5/321
- Beneish/Lee/Nichols (2013) Exhibit A1 (đã trích trong 02)
