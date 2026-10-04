"""Direct URL fetch (mirror opencode webfetch.ts, no API key needed)."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

MAX_RESPONSE_SIZE = 5 * 1024 * 1024
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
MAX_PDF_CHARS = 20000
MAX_PDF_PAGES = 10


def _extract_pdf(content: bytes, title: str) -> dict[str, Any]:
    """Best-effort text from PDF bytes with stdlib only (no extra deps).

    Decodes FlateDecode streams and reads Tj/TJ text operators. Works for
    text PDFs; scanned-image PDFs and subset-font encodings without ToUnicode
    yield little/garbled text — reported honestly via char counts.
    """
    import re
    import zlib

    texts: list[str] = []
    pages = 0
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.S):
        raw = m.group(1).strip()
        try:
            data = zlib.decompress(raw)
        except Exception:
            continue
        pages += 1
        if pages > MAX_PDF_PAGES:
            break
        # Tj strings: (text) Tj  |  TJ arrays: [(text) 123 (more)] TJ
        for tm in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj", data):
            s = tm.group(0)
            inner = s[1 : s.rindex(b")")]
            texts.append(_pdf_unescape(inner))
        for tm in re.finditer(rb"\[(.*?)\]\s*TJ", data, re.S):
            for sm in re.finditer(rb"\((?:\\.|[^\\()])*\)", tm.group(1)):
                texts.append(_pdf_unescape(sm.group(0)[1:-1]))
    text = "\n".join(t for t in texts if t.strip())
    if len(text.strip()) < 50:
        raise ProviderBadData(
            "pdf has no extractable text (scanned images or custom font encoding?)"
        )
    truncated = len(text) > MAX_PDF_CHARS
    return {
        "title": title,
        "pages_scanned": pages,
        "chars": len(text),
        "truncated": truncated,
        "output": text[:MAX_PDF_CHARS],
    }


def _pdf_unescape(raw: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):  # backslash escapes
            nxt = raw[i + 1]
            mapping = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
            if nxt in mapping:
                out.append(mapping[nxt])
            elif nxt in (0x28, 0x29, 0x5C):
                out.append(nxt)
            elif nxt in b"01234567":
                octal = raw[i + 1 : i + 4]
                try:
                    out.append(int(bytes(o for o in octal if 48 <= o <= 55)) & 0xFF)
                    i += 2
                except ValueError:
                    out.append(nxt)
            else:
                out.append(nxt)
            i += 2
        else:
            out.append(c)
            i += 1
    for enc in ("utf-16-be", "utf-8", "latin-1"):
        try:
            return bytes(out).decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return bytes(out).decode("latin-1", errors="replace")


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
    if format == "pdf" or mime == "application/pdf":
        return _extract_pdf(response.content, title)
    if format == "markdown" and "text/html" in content_type:
        return {"title": title, "output": to_markdown(text)}
    if format == "text" and "text/html" in content_type:
        return {"title": title, "output": extract_text(text)}
    return {"title": title, "output": text}
