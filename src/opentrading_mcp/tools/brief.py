"""Brief: morning briefs, news, calendars wired to real sources."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vn_public as pub_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_brief_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def brief_build(
        scope: str = "vn", date: str | None = None, calendars: bool = False
    ) -> dict[str, Any]:
        """Soạn bản tin sáng từ tin tức, chốt tâm lý và lịch. Dùng lúc mở đầu phiên hoặc khi user
            xin bản tin tổng hợp.

        Dùng khi: "bản tin sáng", "tóm tắt thị trường hôm nay".
        Không dùng khi: chỉ cần giá hiện tại (dùng market_snapshot/market_overview — nhẹ hơn nhiều);
            chỉ cần tin 1 mã (dùng news_symbol).

        scope: 'vn' hoặc 'world'. date: ngày ISO của bản tin (ghi nguyên văn).
        calendars: kèm thêm mục IPO/vĩ mô/SBV (sbv_rates, macro_events_vn,
        ipo_calendar_vn); tắt mặc định để bản tin nhanh.
        """
        if scope not in ("vn", "world"):
            return make_envelope(
                {"tool": "brief_build"},
                source="local",
                warnings=[f"unknown scope {scope}"],
                availability="empty",
            )
        sections: dict[str, Any] = {}
        try:
            sections["world_pins"] = await _call("p", intel_p.fear_greed, secs=30.0)
        except (ProviderUnavailable, ProviderBadData):
            sections["world_pins"] = None
        try:
            sections["news"] = await _call("n", intel_p.fireant_posts, None, 10, secs=45.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            try:
                sections["news"] = (
                    await _call("g", intel_p.gdelt_events, "vietnam stock market", secs=45.0)
                ).get("articles", [])
            except (ProviderUnavailable, ProviderBadData) as exc:
                sections["news"] = str(exc)
        try:
            cats = await _call("c", vs_p.indicator_categories)
            sections["macro_series_available"] = len(cats) if isinstance(cats, list) else 0
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            sections["macro_series_available"] = 0
            warnings_live = [f"vietstock categories: {exc}"]
        if calendars:
            for key, fn in (
                ("sbv", pub_p.sbv_rates),
                ("macro_releases", pub_p.nso_releases),
                ("ipo", pub_p.hnx_auctions),
            ):
                try:
                    sections[key] = await _call(key, fn, secs=45.0)
                except (ProviderUnavailable, ProviderBadData) as exc:
                    sections[key] = str(exc)
        data: dict[str, Any] = {
            "scope": scope,
            "sections": sections,
            "sources": [
                "vietstock",
                "gdelt",
                "alternative.me",
                "vs_categories",
            ],
        }
        if date is not None:
            data["date"] = date
        live_warnings: list[str] = locals().get("warnings_live", [])
        vs_state = vs_p.auth_status()
        vs_ok = vs_state.get("authenticated", False) if isinstance(vs_state, dict) else False
        if not vs_ok:
            live_warnings.append(f"vietstock: {vs_state}")
        return make_envelope(data, source="composer", warnings=live_warnings or None)
    @server.tool(annotations=READ_ONLY)
    async def news_market(limit: int = 10, sources: str | None = None) -> dict[str, Any]:
        """Tin thị trường: đọc Fireant trước, GDELT dự phòng. Dùng khi kiểm tra chất xúc tác chung
            của thị trường.

        Dùng khi: "có tin gì mới", "vì sao thị trường tăng/giảm".
        Không dùng khi: tin về 1 mã cụ thể (dùng news_symbol); cần đọc bình luận đằng sau bài nóng
            (lấy post_id từ news_symbol rồi dùng fireant_thread); tìm kiếm web tổng quát (dùng
            web_search).

        sources: 'gdelt' đi thẳng GDELT. Mặc định đọc feed đám đông Fireant
        (token từ env), rỗng thì rơi về GDELT khi trống.
        """
        if sources == "gdelt":
            try:
                data = await _call("g", intel_p.gdelt_events, "vietnam market", limit)
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_market", str(exc))
        try:
            posts = await _call("f", intel_p.fireant_posts, None, limit, secs=45.0)
            if posts:
                return make_envelope({"posts": posts}, source="fireant")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            pass
        try:
            data = await _call("g", intel_p.gdelt_events, "vietnam market", 20)
            return make_envelope(data, source="gdelt")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("news_market", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def news_symbol(
        symbol: str, limit: int = 10, sources: str | None = None
    ) -> dict[str, Any]:
        """Tin về 1 mã: bài Fireant gắn mã đó, GDELT dự phòng. Dùng khi xác minh tin đồn về cổ phiếu
            cụ thể.

        Dùng khi: "FPT có tin gì", "tin đồn về mã X có thật không".
        Không dùng khi: tin chung thị trường (dùng news_market); đã có post_id muốn đọc replies
            (dùng fireant_thread).

        sources: 'gdelt' đi thẳng GDELT. Mặc định đọc bài Fireant gắn
        symbol, rỗng thì rơi về GDELT khi trống.
        Ví dụ: {"symbol": "FPT", "limit": 10}.
        """
        sym = symbol.strip().upper()
        if sources == "gdelt":
            try:
                data = await _call("g", intel_p.gdelt_events, sym, limit)
                return make_envelope(data, source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("news_symbol", str(exc))
        try:
            posts = await _call("f", intel_p.fireant_posts, sym, limit, secs=45.0)
            if posts:
                return make_envelope({"symbol": sym, "posts": posts}, source="fireant")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            pass
        try:
            data = await _call("g", intel_p.gdelt_events, f"{sym} stock", 20, secs=45.0)
            return make_envelope(data, source="gdelt")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("news_symbol", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def fireant_thread(post_id: int, limit: int = 20) -> dict[str, Any]:
        """Một bài Fireant kèm replies. Dùng khi đọc luồng bình luận đằng sau bài nóng.

        Dùng khi: "dân Fireant đang bàn gì về FPT", cần tâm lý đám đông chi tiết.
        Không dùng khi: chỉ cần điểm số tâm lý gọn (dùng sentiment_score); chưa có post_id (lấy từ
            news_symbol trước).

        post_id: postID của Fireant (lấy từ bài trong news_symbol). limit: số replies tối đa.
        Tin đồn nằm ở replies; bài gốc có thể mỏng.
        """
        try:
            data = await _call(
                "f", intel_p.fireant_thread, int(post_id), min(int(limit), 50), secs=45.0
            )
            return make_envelope(data, source="fireant")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("fireant_thread", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def economic_calendar(scope: str = "vn", limit: int = 20) -> dict[str, Any]:
        """Danh mục series vĩ mô dùng thay lịch sự kiện. Dùng khi kiểm tra khả năng có dữ liệu (có
            series CPI/GDP nào không).

        Không dùng khi: cần ngày công bố cụ thể (nguồn không có lịch thật); cần ngày giao
            dịch (dùng dnse_working_dates); cần lịch cổ tức/ĐHĐCĐ (dùng event_calendar_vn).

        scope: chỉ 'vn' (scope khác trả rỗng kèm cảnh báo). limit: số series tối đa.
        """
        if scope != "vn":
            return make_envelope(
                {"scope": scope},
                source="local",
                availability="empty",
                warnings=["world calendar: wire FRED releases next"],
            )
        try:
            cats = await _call("c", vs_p.indicator_categories)
            rows = [
                {
                    "category_id": c.get("CategoryID"),
                    "name": c.get("CategoryName"),
                    "has_data": c.get("HasData"),
                }
                for c in (cats if isinstance(cats, list) else [])
            ]
            return make_envelope(
                {"scope": scope, "series": rows[: max(int(limit), 1)]}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("economic_calendar", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def sbv_rates() -> dict[str, Any]:
        """Nguồn lãi suất điều hành và liên ngân hàng SBV, trang tĩnh scrape. Dùng khi xem chế độ
            lãi suất.

        Không dùng khi: cần lịch công bố số liệu (dùng macro_events_vn); cần ngày giao dịch (dùng
            dnse_working_dates).

        Giá trị đổi hiếm; nguồn không có API.
        """
        try:
            return make_envelope(await _call("s", pub_p.sbv_rates), source="sbv-scrape")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("sbv_rates", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def macro_events_vn() -> dict[str, Any]:
        """Danh sách công bố của Tổng cục Thống kê kèm ngày tham chiếu và ngày tới. Dùng khi lập
            lịch dữ liệu vĩ mô.

        Dùng khi: "khi nào công bố CPI", lịch ra số liệu vĩ mô.
        Không dùng khi: cần lãi suất hiện hành (dùng sbv_rates); cần ngày giao dịch chứng khoán
            (dùng dnse_working_dates).

        Gồm lịch CPI và các đợt công bố; lịch cả năm đầy đủ nằm trong PDF của NSO.
        """
        try:
            return make_envelope(
                {"releases": await _call("m", pub_p.nso_releases)}, source="nso-scrape"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("macro_events_vn", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def corporate_calendar(symbol: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Feed công bố thông tin thô dùng như sự kiện doanh nghiệp. Dùng khi quét cổ tức/họp cổ
            đông dạng feed thô.

        Dùng khi: cần feed disclosure nguyên bản.
        Không dùng khi: cần lịch cổ tức/niêm yết/họp đã phân loại theo ngày (dùng event_calendar_vn
            — dạng calendar); cần sự kiện đã phân loại theo loại (dùng company_events).

        symbol: bỏ qua để xem toàn VN (mặc định lấy VCB làm feed mẫu); limit:
        số công bố tối đa. Feed thô; company_events phân loại các công bố
        giống vậy theo loại; event_calendar_vn là dạng xem calendar.
        """
        try:
            docs = await _call("d", vs_p.documents, symbol or "VCB", 60)
            if isinstance(docs, list):
                docs = docs[: max(int(limit), 1)]
            return make_envelope(
                {"symbol": (symbol or "VCB").upper(), "docs": docs}, source="vietstock"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("corporate_calendar", str(exc))

    return [
        {"name": "brief_build"},
        {"name": "news_market"},
        {"name": "news_symbol"},
        {"name": "fireant_thread"},
        {"name": "economic_calendar"},
        {"name": "corporate_calendar"},
        {"name": "sbv_rates"},
        {"name": "macro_events_vn"},
    ]
