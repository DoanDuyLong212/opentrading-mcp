"""Web: generic fetch + delegated search (mirror opencode webfetch/websearch)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import webfetch as fetch_p
from opentrading_mcp.providers import websearch as search_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY_OPEN,
    cache_lookup,
    cache_store,
    run_blocking,
)


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_web_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY_OPEN)
    async def web_fetch(
        url: str, format: str = "markdown", timeout_seconds: int = 30
    ) -> dict[str, Any]:
        """Đọc một URL và chuyển thành markdown, text, html hoặc text PDF. Dùng khi đọc nội dung
            trang web cụ thể.

        Dùng khi: đọc bài báo/công bố/báo cáo mà user đưa link; đọc chi tiết báo cáo CTCK (url từ
            analyst_consensus).
        Không dùng khi: cần TÌM thông tin mà chưa có link (dùng web_search); trang cần đăng nhập hay
            chỉ render bằng JS (báo không đọc được).

        format: 'markdown' (mặc định), 'text', 'html' hoặc 'pdf' (trích text PDF,
        best-effort thuần stdlib; PDF scan báo thẳng là không trích được). timeout_seconds: thời
            gian chờ
        tối đa (mặc định 30).
        """
        fp = f"{url}|{format}|{timeout_seconds}"
        hit = await cache_lookup("web_fetch", fp)
        if hit is not None:
            return hit
        try:
            data = await _call(
                "web_fetch",
                fetch_p.fetch_url,
                url,
                format,
                min(timeout_seconds, 120),
                secs=120.0,
            )
            return await cache_store(
                "web_fetch", fp, TTL_SECONDS["world"],
                data, source="web",
            )
        except (ProviderBadData, ProviderUnavailable) as exc:
            return _na("web_fetch", str(exc))

    registered = [{"name": "web_fetch"}]

    if search_p.web_search_available():
        # Mirror opencode registry gating: websearch is hidden when no provider key exists.

        @server.tool(annotations=READ_ONLY_OPEN)
        async def web_search(
            query: str,
            num_results: int = 8,
            livecrawl: str = "fallback",
            search_type: str = "auto",
            context_max_chars: int | None = None,
        ) -> dict[str, Any]:
            """Tìm kiếm web qua Exa/Parallel. Dùng khi cần thông tin cập nhật mà chưa có link cụ
                thể.

            Dùng khi: tin tức mới, sự kiện vừa xảy ra, kiểm chứng thông tin ngoài dữ liệu server.
            Không dùng khi: đã có URL (dùng web_fetch đọc thẳng); dữ liệu giá/chỉ số có sẵn (dùng
                tool thị trường tương ứng — chính xác và có nguồn hơn).

            num_results: số kết quả (mặc định 8). livecrawl: 'fallback' ưu tiên
            index cache, 'preferred' crawl live. search_type: 'auto' (mặc định),
            'fast', hoặc 'deep'. context_max_chars: trần ký tự context trả về.
            """
            fp = f"{query}|{num_results}|{livecrawl}|{search_type}|{context_max_chars}"
            hit = None
            # livecrawl='preferred' explicitly requests a fresh crawl: never serve cache.
            if livecrawl != "preferred":
                hit = await cache_lookup("web_search", fp)
            if hit is not None:
                return hit
            try:
                data = await _call(
                    "web_search",
                    search_p.search,
                    query,
                    num_results,
                    livecrawl,
                    search_type,
                    context_max_chars,
                    secs=60.0,
                )
                provider = data.get("provider", "web") if isinstance(data, dict) else "web"
                if livecrawl == "preferred":
                    return make_envelope(
                        data,
                        source="web-search",
                        warnings=[f"provider={provider}"] if provider != "web" else None,
                    )
                return await cache_store(
                    "web_search", fp, TTL_SECONDS["world"],
                    data,
                    source="web-search",
                    warnings=[f"provider={provider}"] if provider != "web" else None,
                )
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                return _na("web_search", str(exc))

        registered.append({"name": "web_search"})
    return registered
