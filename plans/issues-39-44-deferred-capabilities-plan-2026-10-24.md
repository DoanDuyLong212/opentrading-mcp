# Kế hoạch năng lực riêng sau issue #39/#44

## Primary goal

Nhà đầu tư cổ phiếu nhận chỉ số và tín hiệu có công thức phù hợp loại doanh nghiệp, dữ liệu đúng kỳ và đúng thời điểm công bố, cùng giới hạn kiểm định rõ ràng. Mọi tùy chọn mới phải giữ được cách tính cũ có phiên bản để kết quả lịch sử có thể tái lập.

## Phase 0 — Chốt hợp đồng nguồn và lý thuyết

**How this serves the primary goal:** Không thể gọi một điểm là đúng về tài chính khi chưa biết biến đầu vào, kỳ, đơn vị, phạm vi hợp nhất và ngày nó thực sự được công bố.

**What to implement:** Lập registry cho từng trường gồm doanh nghiệp/loại ngành, nguồn, mã dòng, công thức, đơn vị, kỳ bắt đầu/kết thúc, ngày công bố, phiên bản chỉnh sửa, phạm vi hợp nhất và khả năng điều chỉnh cổ phiếu. Định nghĩa trạng thái `supported`, `partial`, `not_applicable`, `unknown`; không coi `unknown` là 0. Đóng băng fixture đầu vào và output mẫu có hash, ghi khác biệt giữa nghiên cứu gốc và quy ước sản phẩm.

**Allowed APIs/patterns:** `providers/forensic.py::normalize_annual`, `annual_inputs`, `derive_quarter_cfo`, `select_annual_window`; `forensic_models.py::calculate_forensic`; nguồn công bố chính thức [HNX](https://cbisprod.hnx.vn/vi-vn/huong-dan/chi-tiet-thu-tuc-22-39.html). Bài [Beneish 2013](https://cpb-us-w2.wpmucdn.com/sites.udel.edu/dist/a/855/files/2020/07/Earnings-Manipulation-and-Expected-Returns.pdf) nêu rõ mô hình không áp dụng cho doanh nghiệp tài chính. [Piotroski 2000](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf) kiểm nghiệm trên mẫu cổ phiếu giá trị Mỹ; không ghi quy tắc loại toàn bộ doanh nghiệp tài chính. Xác minh văn bản pháp lý Việt Nam hiện hành trước khi đưa hạn công bố vào mã.

**Verification:** Oracle độc lập cho từng công thức và fixture đối chiếu báo cáo gốc; test cùng mã/kỳ/scope/đơn vị/publication-as-of; kiểm ba trạng thái thiếu dữ liệu. **Anti-pattern:** không dùng dữ liệu sửa lại sau ngày quyết định để mô phỏng một tín hiệu quá khứ.

## Phase 1 — Forensic riêng cho ngân hàng, chứng khoán và bảo hiểm

**How this serves the primary goal:** Người dùng không nhận điểm công nghiệp từ cấu trúc báo cáo tài chính ngành có ý nghĩa kế toán khác.

**What to implement:** Thiết kế taxonomy và adapter theo ba ngành, mỗi ngành có bảng dữ liệu, giả thuyết rủi ro, công thức, đơn vị, kết quả giải thích được và điều kiện áp dụng riêng. Với ngân hàng, khảo sát chất lượng tài sản/dự phòng, vốn và thanh khoản từ báo cáo gốc và quy định Việt Nam; với công ty chứng khoán, tách tài sản khách hàng và tự doanh; với bảo hiểm, tách dự phòng nghiệp vụ, bồi thường và khả năng thanh toán. Chỉ phát hành chỉ số sau khi có nguồn và kiểm định thực nghiệm cho đúng ngành. Giữ Beneish `not_applicable`; Piotroski `unsupported` cho tới khi một mô hình ngành được nghiên cứu, không tuyên bố bài gốc cấm dùng cho ngành tài chính.

**References:** `forensic_models.py` applicability branch; [Basel Framework](https://www.bis.org/baselframework/BaselFramework.pdf) chỉ là nền tảng khái niệm ngân hàng, không thay quy định Việt Nam; báo cáo và chuẩn công bố HNX/HOSE/SBV phải được kiểm riêng. **Verification:** ba fixture báo cáo ngành có phạm vi solo/hợp nhất, năm liên tiếp và ngày công bố; review bởi người am hiểu ngành; không ghép chỉ tiêu khác nghĩa. **Anti-pattern:** không coi tiền gửi khách hàng là nợ vay công nghiệp hoặc thu nhập lãi là doanh thu bán hàng.

## Phase 2 — Hiệu chuẩn ngưỡng trên dữ liệu Việt Nam

**How this serves the primary goal:** Một ngưỡng cảnh báo tại Việt Nam chỉ được hiển thị khi có bằng chứng ngoài mẫu, thay vì đổi nhãn của ngưỡng nghiên cứu nước ngoài.

**What to implement:** Xây panel có ngày công bố thực và lịch sử hủy niêm yết, định nghĩa trước outcome (gian lận/sai sót/khả năng sinh lời là ba nhãn khác nhau), horizon, chi phí giao dịch và metric. Chia theo thời gian và doanh nghiệp; walk-forward, bootstrap khoảng tin cậy, so với ngưỡng gốc và baseline đơn giản. Công bố số mẫu, tỷ lệ thiếu, selection bias, sensitivity và phiên bản threshold; nếu thiếu nhãn đáng tin, chỉ công bố nghiên cứu không triển khai cutoff.

**References:** [Piotroski 2000](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf) dời thời điểm bắt đầu lợi nhuận tới tháng thứ năm sau năm tài chính để giảm nhìn trước; [CFA Backtesting & Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation) hướng dẫn kiểm định theo thời gian và cảnh báo look-ahead/survivorship. **Verification:** pipeline point-in-time tái lập, holdout khóa trước, kết quả kèm CI và chi phí; kiểm không lộ issuer giữa train/test khi cần. **Anti-pattern:** không gọi −1.78 là ngưỡng đã hiệu chuẩn cho VN.

## Phase 3 — Canonical quarterly và TTM forensic

**How this serves the primary goal:** Điểm 12 tháng gần nhất phản ánh đúng bốn quý không trùng nhau và các số dư tại đúng ngày báo cáo.

**What to implement:** Lập adapter lưu riêng dòng YTD, dòng quý đơn và balance snapshot; suy quý bằng chênh lệch YTD khi cùng doanh nghiệp, phạm vi, nguồn, phiên bản và niên độ. Ghép bốn quý không chồng lấn, kiểm năm tài chính lệch lịch, restatement và ngày công bố; balance không cộng bốn quý. Đặt `period_basis`, `as_of`, `source_revision`, `coverage`, `model_version` trong output. TTM chỉ thành `complete` khi từng biến mô hình đủ.

**References:** `forensic.py::derive_quarter_cfo` là pattern kiểm identity; [IAS 34](https://www.ifrs.org/issued-standards/list-of-standards/ias-34-interim-financial-reporting/) phân biệt số liệu kỳ giữa niên độ và lũy kế; phải xác minh semantics báo cáo Việt Nam riêng. **Verification:** fixture quý đơn/YTD và restatement; fiscal year lệch, thiếu Q2, thay scope, YTD âm, số 0, duplicate; oracle độc lập. **Anti-pattern:** không `annual / 4`, cộng balance, hoặc dùng dữ liệu công bố sau ngày as-of.

## Phase 4 — Imputation chỉ khi người dùng bật

**How this serves the primary goal:** Người dùng có thể khảo sát độ nhạy mà không nhầm số ước lượng với báo cáo đã xác thực.

**What to implement:** Thiết kế `imputation_mode` mặc định `off`; mỗi thay thế có phương pháp, nguồn so sánh, kỳ, phạm vi, giá trị gốc, uncertainty và số thành phần bị ảnh hưởng. Output phải tách observed score với scenario estimate; điểm strict canonical tiếp tục `null` khi thiếu trường bắt buộc. Không dùng imputation cho quyết định đầu tư tự động nếu chưa có hiệu chuẩn và disclosure.

**References:** `forensic_models.py` missing/coverage contract; [Beneish gốc](https://www.researchgate.net/publication/252059255_The_Detection_of_Earnings_Manipulation) dùng quy tắc thay thế cụ thể cho một số biến trong tập nghiên cứu, không phải giấy phép thay mọi dữ liệu thiếu. **Verification:** off không đổi output; từng phương pháp có sensitivity/bounds và provenance; không cache lẫn chế độ. **Anti-pattern:** không điền CFO=0, DEPI=1 hay equity issuance=false để dựng điểm đầy đủ.

## Phase 5 — Quy ước Ichimoku và trough mới có phiên bản

**How this serves the primary goal:** Người dùng thử quy ước biểu đồ hay định nghĩa đáy khác mà vẫn tái lập được kết quả cũ.

**What to implement:** Dùng fixture export từ chỉ báo tham chiếu để quyết định mapping `displacement=26` với index shift; thêm lựa chọn có tên và `rule_version`, giữ mặc định cũ tới khi so sánh và migration rõ. Với cycle, định nghĩa ngưỡng drawdown/rebound/new-peak và ngày `confirmation_date` cho từng biến thể, kiểm sự khác biệt event set và hậu quả thống kê. Công khai rằng trough chỉ xác nhận khi có dữ liệu tương lai.

**References:** `technicals.py::compute` shift25; `cycle_stats.py::_major_troughs`; [TradingView Ichimoku](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/) mô tả displacement 26; [CFA model validation](https://rpc.cfainstitute.org/-/media/documents/article/rf-brief/investment-model-validation.pdf) về look-ahead. **Verification:** chuỗi OHLC không phẳng, export đối chiếu, nhiều đáy/đỉnh, equality, vùng dữ liệu chưa đủ; cache/schema version. **Anti-pattern:** không đổi 25 thành 26 chỉ vì mô tả văn bản, không gắn tín hiệu biết được tại ngày trough.

## Phase 6 — PE theo TTM hiện tại và nguồn vốn hóa mới

**How this serves the primary goal:** Bội số và vốn hóa phản ánh giá, lợi nhuận và số cổ phiếu trên cùng cơ sở điều chỉnh và thời điểm.

**What to implement:** `pe_basis="current_ttm"` là output mới có giá/giờ, EPS bốn quý và kỳ công bố, đơn vị/currency, xử lý cổ tức cổ phiếu, split và hồi tố; không ghi đè historical PE. Nguồn market cap mới phải có giá cùng thời điểm với shares outstanding, loại shares (outstanding/free float/treasury), đơn vị và corporate actions; báo `unavailable` nếu không xác minh được. Kiểm API nguồn v4 thực tế trước khi thêm adapter.

**References:** `compute_financial.py::valuation_run`, `vnstock.py::equity_fundamentals/equity_quote_batch`; [IAS 33 EPS](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ias-33-earnings-per-share.pdf?bypass=on) về bình quân gia quyền và điều chỉnh cổ phiếu; [SEC market-cap glossary](https://www.sec.gov/resources-small-businesses/glossary) định nghĩa giá × cổ phiếu đang lưu hành. **Verification:** split/bonus/dividend, EPS âm/0, shares stale, giá sau giờ giao dịch, ×1000 units và as-of; historical PE giữ nguyên. **Anti-pattern:** không gắn EPS năm cũ nhãn TTM hiện tại hoặc giá hiện tại với số cổ phiếu đã lỗi thời.

## Phase 7 — Nâng vnstock v5 cách ly

**How this serves the primary goal:** Nâng nguồn dữ liệu mà không âm thầm đổi ký hiệu kỳ, đơn vị hoặc kết quả tài chính.

**What to implement:** Đóng băng matrix v4 hiện hành, đọc migration chính thức, dựng adapter v5 riêng, map schema và exception theo fixture cùng symbol/kỳ/scope; kiểm candle times, báo cáo VAS IDs, financial statement shapes; chỉ chuyển dependency sau parity và fallback/rollback. Không gộp thay đổi công thức với nâng major.

**References:** `pyproject.toml` đang khai `vnstock>=3.0`; [vnstock 4→5 migration](https://www.vnstocks.com/docs/vnstock/chuyen-doi/tu-vnstock-4x), [docs v5](https://www.vnstocks.com/docs/vnstock/gioi-thieu); `vnstock.py` adapters. **Verification:** frozen lock, unit tests, recorded parity fixtures, live smoke read-only và cache fingerprint; report mọi sai khác. **Anti-pattern:** không gọi method/parameter v5 trong runtime v4.

## Phase 8 — Hợp đồng với repo OpenTrading ngoài workspace

**How this serves the primary goal:** Ứng dụng gọi MCP hiểu đúng trạng thái dữ liệu, mô hình và thay đổi schema trước khi đưa lời khuyên đầu tư.

**What to implement:** Sau khi các output mới ổn định, lập bảng contract field/status/version và tình huống thiếu/không áp dụng; khảo sát quyền truy cập, version repo, code consumers và test e2e. Thực hiện PR riêng trong repo đó khi có workspace/quyền phù hợp. Không suy ra logic bên ngoài từ tên repo.

**References:** `SKILLS.md`, `prompts.py`, MCP tool schemas tại repo hiện hành; cần discovery repo OpenTrading thực tế trước triển khai. **Verification:** schema compatibility, lời nhắc không suy điểm `null` là an toàn, e2e cùng deployed SHA. **Anti-pattern:** không sửa repo khác khi chưa kiểm code và quyền hiện hành.

## Phase 9 — Verification và quyết định triển khai

**How this serves the primary goal:** Mỗi năng lực chỉ mở khi công thức, dữ liệu nguồn và tác động đầu tư được kiểm độc lập.

**What to implement:** Review tài chính độc lập, oracle số học, kiểm nguồn công bố, test as-of, cache cold/warm và migration, CI PostgreSQL/Python, pilot read-only và báo cáo sai lệch. Giữ từng capability sau feature flag cho đến khi cổng dữ liệu và validation tương ứng đạt.

**Verification:** tài liệu acceptance công khai nguồn, sample, khoảng tin cậy, phiên bản, known gaps; không dùng một CI xanh để suy ra tính đúng của nguồn live. **Anti-pattern:** không gọi score có thiếu đầu vào là lời khuyên mua/bán.

## Thứ tự và ranh giới

Phase 0→3 là nền dữ liệu; phase 1 và 2 cần nghiên cứu ngành và panel riêng; phase 4/5/6 là tùy chọn sản phẩm có phiên bản; phase 7 là migration kỹ thuật độc lập; phase 8 chỉ sau khi contract ổn định; phase 9 áp dụng ở cuối mỗi phase. Không đặt trước ngày hoàn thành hay ngưỡng VN khi chưa có dataset.
