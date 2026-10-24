"""MCP prompts: tool-composition guides (UW/EODHD/Tiingo pattern).

Prompts do not fetch data; they tell the agent which tools to call in
which order for recurring workflows. ai_detect is a heuristic proxy of
the 8010 Breakout/SEPA model (reference-only: no pickle, no ML probability).

Prompt text is Vietnamese: users read it (it is sent as their message) and
answer in Vietnamese. Tool and field names stay as they are.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(server: FastMCP) -> list[str]:
    @server.prompt(description="Bản tin đầu phiên. Dùng lúc mở cửa thị trường.")
    def morning_briefing(scope: str = "vn") -> str:
        return (
            f"Soạn bản tin đầu phiên cho phạm vi '{scope}'.\n"
            "1. Gọi brief_build để lấy bản tin tổng hợp.\n"
            "2. Gọi market_overview để xem giá, mã tăng/giảm mạnh, độ rộng và phiên.\n"
            "3. Gọi breadth_scan để đánh giá sức khoẻ đợt tăng.\n"
            "4. Gọi money_flow để xem hướng dòng tiền khối ngoại.\n"
            "5. Gọi futures_basis để xem chênh lệch VN30F1M so với cơ sở.\n"
            "6. Gọi world_prediction_odds khi xác suất vĩ mô có ảnh hưởng.\n"
            "Tổng hợp thành 5 gạch đầu dòng, mỗi dòng ghi rõ nguồn."
        )

    @server.prompt(description="Phân tích sâu một mã. Dùng trước khi khuyến nghị một cổ phiếu.")
    def ticker_analysis(symbol: str) -> str:
        sym = symbol.strip().upper()
        return (
            f"Phân tích {sym}.\n"
            "1. Gọi symbol_lookup khi chưa chắc mã chính xác.\n"
            "2. Gọi stock_overview để lấy hồ sơ.\n"
            "3. Gọi signals_technical để chọn thời điểm (sức mạnh tương đối, vị trí 52 tuần, "
            "mẫu hình).\n"
            "4. Gọi valuation_run để có vùng giá trị hợp lý.\n"
            "5. Gọi stock_forensic; chỉ diễn giải điểm annual khi model complete và áp dụng được, "
            "cùng pháp nhân/phạm vi báo cáo; null/partial ghi input thiếu hoặc chưa rõ; "
            "not_applicable/unsupported ghi mô hình không áp dụng/chưa hỗ trợ.\n"
            "6. Gọi insider_trading và analyst_consensus để xem giao dịch nội bộ và khuyến nghị "
            "của các CTCK.\n"
            "7. Gọi company_events và news_symbol để tìm chất xúc tác.\n"
            "Kết thúc bằng kịch bản tích cực/tiêu cực và điều gì sẽ khiến bạn đổi ý."
        )

    @server.prompt(description="Chấm độ tin cậy trước BCTC. Dùng khi sắp công bố kết quả.")
    def pre_earnings(symbol: str) -> str:
        sym = symbol.strip().upper()
        return (
            f"Chấm điểm thiết lập trước BCTC của {sym} (KHÔNG dự báo kết quả).\n"
            "1. Độ chắc của ngày: company_events + event_calendar_vn — có ngày cụ thể hay chỉ "
            "là tin đồn?\n"
            "2. Chất lượng xu hướng: financial_statements 4 quý gần nhất.\n"
            "3. stock_forensic M-Score/Piotroski annual: kiểm tra model status và cùng phạm vi; "
            "chỉ diễn giải complete/applicable; null/partial ghi input thiếu hoặc chưa rõ; "
            "not_applicable/unsupported ghi mô hình không áp dụng/chưa hỗ trợ.\n"
            "4. Mốc kỳ vọng: planned_targets (kế hoạch công ty) + độ phân tán analyst_consensus "
            "+ độ nóng news_symbol + rủi ro thổi phồng theo sentiment_score.\n"
            "5. Vị thế: insider_trading + money_flow + giao dịch thoả thuận bất thường "
            "block_trades.\n"
            "6. Biên an toàn: valuation_run, so bội số với lịch sử.\n"
            "Kết quả: grade A/B/C, mỗi tiêu chí một dòng bằng chứng, quy mô gợi ý qua "
            "scenario_simulate, và danh sách điều chưa biết (VN không có đồng thuận EPS nên "
            "không bao giờ đặt mức bất ngờ bằng số)."
        )

    @server.prompt(description="Xoay vòng ngành. Dùng khi đọc phân bổ vốn giữa các ngành.")
    def sector_rotation() -> str:
        return (
            "Đọc xu hướng xoay vòng ngành.\n"
            "1. Gọi sector_performance để xem bản đồ nhiệt ngành.\n"
            "2. Gọi money_flow để xem khối ngoại đang ở đâu.\n"
            "3. Gọi futures_basis để xem vị thế phái sinh.\n"
            "4. Gọi ipo_calendar_vn để xem áp lực nguồn cung sắp tới.\n"
            "5. Gọi compare_equities cho 2 mã dẫn đầu của mỗi ngành nóng.\n"
            "Gọi tên dòng xoay vòng (ví dụ ngân hàng -> thép) kèm số liệu chứng minh."
        )

    @server.prompt(
        description="Dò breakout (heuristic kiểu SEPA). Dùng để tìm hoặc kiểm chứng điểm bứt phá."
    )
    def ai_detect(symbol: str | None = None) -> str:
        target = (symbol or "").strip().upper()
        header = (
            f"Kiểm chứng thiết lập breakout của {target}.\n"
            if target
            else "Tìm breakout: chạy signals_scan trước, rồi kiểm chứng từng mã tìm được theo "
            "các tiêu chí dưới đây.\n"
        )
        return (
            header + "Đây là heuristic mô phỏng mô hình 8010 Breakout/SEPA (chỉ tham khảo: không "
            "có xác suất ML, không có ngưỡng 0.85 — chấm từng tiêu chí).\n"
            "Tiêu chí 1, xu hướng: signals_technical — giá trên sma50/sma150/sma200, "
            "adx14 >= 20, rs_vs_bench > 0, pos_52w > 0.75.\n"
            "Tiêu chí 2, co hẹp: bandwidth Bollinger thu hẹp + atr14 thấp + khối lượng cạn.\n"
            "Tiêu chí 3, xác nhận bứt phá: giá trên kháng cự 20 phiên; đối chiếu signals_scan; "
            "pattern_match để tìm mẫu tương tự trong lịch sử.\n"
            "Tiêu chí 4, cơ bản: tăng trưởng EPS từ vn_fundamentals + valuation_run (tránh đuổi "
            "theo bội số đã quá cao).\n"
            "Tiêu chí 5, dòng tiền: money_flow + xác nhận từ block_trades.\n"
            "Kết luận: STRONG (>=4 tiêu chí) / WATCH (3) / REJECT; điểm vào và điểm sai từ "
            "hỗ trợ/kháng cự; nêu rõ tiêu chí nào không đạt."
        )

    @server.prompt(
        description="Checklist rủi ro trước khi vào lệnh. Dùng trước khi chọn quy mô vị thế."
    )
    def risk_check(symbols: str, side: str = "buy", size_vnd: str = "100000000") -> str:
        names = ", ".join(s.strip().upper() for s in symbols.split(",") if s.strip())
        return (
            f"Checklist trước lệnh: {side.upper()} {names}, quy mô {size_vnd} VND.\n"
            "1. quant_risk trên lợi suất gần đây (Sharpe, sụt giảm tối đa, tỷ lệ thắng).\n"
            "2. scenario_simulate cú sốc -5%, quy theo quy mô ở trên.\n"
            "3. correlation_matrix với danh mục đang nắm.\n"
            "4. stock_forensic cho từng mã: chỉ dùng ngưỡng khi annual model complete/applicable "
            "và cùng phạm vi; vượt ngưỡng cần kiểm tra thêm, cân nhắc giảm quy mô. "
            "null/partial ghi input thiếu hoặc chưa rõ; not_applicable/unsupported ghi mô hình "
            "không áp dụng/chưa hỗ trợ; không kết luận sạch hay gian lận.\n"
            "5. company_events + event_calendar_vn kiểm tra giai đoạn nhạy cảm (BCTC/ĐHCĐ trong "
            "10 ngày tới thì giảm nửa quy mô).\n"
            "6. valuation_run kiểm tra biên an toàn.\n"
            "Kết quả: GO / HALF (nửa quy mô) / NO-GO, kèm quy mô tối đa bằng VND, giá sai "
            "(invalidation) "
            "và 3 điều chưa biết."
        )

    return [
        "ai_detect",
        "morning_briefing",
        "pre_earnings",
        "risk_check",
        "sector_rotation",
        "ticker_analysis",
    ]
