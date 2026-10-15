"""Paid web-search providers Exa/Parallel (mirror opencode mcp-websearch.ts)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import httpx

from opentrading_mcp.providers.errors import ProviderAuthMissing, ProviderUnavailable
from opentrading_mcp.providers.pool import shared_client

SEARCH_TIMEOUT = 25


def _exa_url() -> str:
    key = os.environ.get("EXA_API_KEY", "").strip()
    if key:
        from urllib.parse import quote

        return f"https://mcp.exa.ai/mcp?exaApiKey={quote(key)}"
    return "https://mcp.exa.ai/mcp"


PARALLEL_URL = "https://search.parallel.ai/mcp"


def _parallel_headers() -> dict[str, str]:
    headers = {"User-Agent": "opencode"}
    key = os.environ.get("PARALLEL_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def parse_response(body: str) -> str | None:
    def payload(text: str) -> str | None:
        trimmed = text.strip()
        if not trimmed.startswith("{"):
            return None
        try:
            data = json.loads(trimmed)
        except ValueError:
            return None
        try:
            content = data["result"]["content"]
        except (KeyError, TypeError):
            return None
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                return str(item["text"])
        return None

    if body.strip():
        direct = payload(body)
        if direct:
            return direct
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        found = payload(line[6:])
        if found:
            return found
    return None


def select_provider(query: str) -> str:
    override = os.environ.get("WEBSEARCH_PROVIDER", "").strip().lower()
    if override in ("exa", "parallel"):
        return override
    digest = hashlib.sha256(query.encode()).hexdigest()
    return "exa" if int(digest, 16) % 2 == 0 else "parallel"


def web_search_available() -> bool:
    return bool(os.environ.get("EXA_API_KEY", "").strip()) or bool(
        os.environ.get("PARALLEL_API_KEY", "").strip()
    )


def search(
    query: str,
    num_results: int = 8,
    livecrawl: str = "fallback",
    search_type: str = "auto",
    context_max_chars: int | None = None,
) -> dict[str, Any]:
    provider = select_provider(query)
    args: dict[str, Any]
    if provider == "parallel":
        if not os.environ.get("PARALLEL_API_KEY", "").strip():
            raise ProviderAuthMissing("PARALLEL_API_KEY is not set")
        tool, args, headers = (
            "web_search",
            {"objective": query, "search_queries": [query]},
            _parallel_headers(),
        )
    else:
        if not os.environ.get("EXA_API_KEY", "").strip():
            raise ProviderAuthMissing("EXA_API_KEY is not set")
        tool, args, headers = (
            "web_search_exa",
            {
                "query": query,
                "type": search_type,
                "numResults": num_results,
                "livecrawl": livecrawl,
                "contextMaxCharacters": context_max_chars,
            },
            {},
        )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }
    try:
        url = PARALLEL_URL if provider == "parallel" else _exa_url()
        response = shared_client().post(
            url,
            json=payload,
            headers={"Accept": "application/json, text/event-stream", **headers},
            timeout=SEARCH_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"{tool} request timed out") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"{tool} request failed: {exc}") from exc
    output = parse_response(response.text)
    return {
        "output": output or "No search results found. Please try a different query.",
        "provider": provider,
    }
