"""Direct URL fetch (mirror opencode webfetch.ts, no API key needed)."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

MAX_RESPONSE_SIZE = 5 * 1024 * 1024
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
HONEST_UA = "opencode"


def accept_header(format: str) -> str:
    if format == "markdown":
        return (
            "text/markdown;q=1.0, text/x-markdown;q=0.9, "
            "text/plain;q=0.8, text/html;q=0.7, */*;q=0.1"
        )
    if format == "text":
        return "text/plain;q=1.0, text/markdown;q=0.9, text/html;q=0.8, */*;q=0.1"
    if format == "html":
        return "text/html;q=1.0, application/xhtml+xml;q=0.9, text/plain;q=0.8, */*;q=0.7"
    return "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def _headers(user_agent: str, format: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": accept_header(format),
        "Accept-Language": "en-US,en;q=0.9",
    }


def extract_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "object", "embed"]):
        tag.decompose()
    return soup.get_text().strip()


def to_markdown(html: str) -> str:
    from markdownify import markdownify

    return markdownify(html, heading_style="atx", bullets="-", code_language="fenced")


def fetch_url(url: str, format: str = "markdown", timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    if not url.startswith("http://") and not url.startswith("https://"):
        raise ProviderBadData("URL must start with http:// or https://")
    capped = min(timeout, MAX_TIMEOUT)
    try:
        response = httpx.get(url, headers=_headers(BROWSER_UA, format), timeout=capped)
        if response.status_code == 403 and response.headers.get("cf-mitigated") == "challenge":
            response = httpx.get(url, headers=_headers(HONEST_UA, format), timeout=capped)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"fetch timed out: {url}") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"fetch failed: {url}: {exc}") from exc
    if len(response.content) > MAX_RESPONSE_SIZE:
        raise ProviderBadData("Response too large (exceeds 5MB limit)")
    content_type = response.headers.get("content-type", "")
    mime = content_type.split(";")[0].strip().lower()
    title = f"{url} ({content_type})"
    if mime.startswith("image/"):
        return {
            "title": title,
            "output": "Image fetched successfully",
            "attachment": f"data:{mime};base64," + base64.b64encode(response.content).decode(),
        }
    text = response.content.decode(response.encoding or "utf-8", errors="replace")
    if format == "markdown" and "text/html" in content_type:
        return {"title": title, "output": to_markdown(text)}
    if format == "text" and "text/html" in content_type:
        return {"title": title, "output": extract_text(text)}
    return {"title": title, "output": text}
