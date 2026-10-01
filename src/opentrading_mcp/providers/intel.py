"""Direct HTTP intel providers: FRED, WorldBank, Fireant, Groq, odds, GDELT, fear/greed."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)


def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    try:
        response = httpx.get(url, params=params, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"timeout: {url}") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"unreachable: {url}") from exc
    if response.status_code == 429:
        raise ProviderUnavailable(f"rate limited: {url}")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderBadData(f"bad json: {url}") from exc


def fred_series(series_id: str, limit: int = 60) -> dict[str, Any]:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise ProviderAuthMissing("FRED_API_KEY is not set")
    body = _get_json(
        "https://api.stlouisfed.org/fred/series/observations",
        {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": min(limit, 100),
        },
    )
    obs = body.get("observations", []) if isinstance(body, dict) else []
    points = [{"t": o.get("date"), "v": o.get("value")} for o in obs if o.get("value") != "."]
    return {"series": series_id, "points": points}


def worldbank_country(iso3: str, indicator: str) -> dict[str, Any]:
    body = _get_json(
        f"https://api.worldbank.org/v2/country/{iso3}/indicator/{indicator}",
        {"format": "json", "per_page": 60},
    )
    rows = body[1] if isinstance(body, list) and len(body) > 1 else []
    points = [{"t": r.get("date"), "v": r.get("value")} for r in rows if r.get("value") is not None]
    return {"country": iso3.upper(), "indicator": indicator, "points": points}


def fireant_posts(symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    token = os.environ.get("FIREANT_TOKEN", "").strip()
    if not token:
        raise ProviderAuthMissing("FIREANT_TOKEN is not set")
    base = os.environ.get("FIREANT_API_BASE", "https://restv2.fireant.vn").strip()
    params: dict[str, Any] = {"type": 1, "offset": 0, "limit": min(limit, 50)}
    if symbol:
        params["symbol"] = symbol.upper()
    try:
        response = httpx.get(
            f"{base}/posts",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("fireant unreachable") from exc
    if response.status_code == 401:
        raise ProviderAuthMissing("fireant rejected token")
    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderBadData("fireant bad json") from exc
    items = (
        body
        if isinstance(body, list)
        else (body.get("posts") or body.get("data") or [])
        if isinstance(body, dict)
        else []
    )
    out: list[dict[str, Any]] = []
    for post in items[:limit]:
        if not isinstance(post, dict):
            continue
        user = post.get("user") or {}
        out.append(
            {
                "id": post.get("id") or post.get("postId"),
                "user": user.get("username") if isinstance(user, dict) else None,
                "text": (post.get("description") or "")[:500],
                "symbols": [
                    t.get("symbol")
                    for t in (post.get("taggedSymbols") or [])
                    if isinstance(t, dict)
                ],
                "likes": post.get("likeCount", 0),
            }
        )
    return out


def groq_chat(system_msg: str, user_msg: str, max_tokens: int = 300) -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ProviderAuthMissing("GROQ_API_KEY is not set")
    model = os.environ.get("GROQ_MODEL_SENTIMENT", "llama-3.1-8b-instant")
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("groq unreachable") from exc
    if response.status_code == 401:
        raise ProviderAuthMissing("groq rejected key")
    try:
        body = response.json()
        return str(body["choices"][0]["message"]["content"])
    except (ValueError, KeyError, IndexError) as exc:
        raise ProviderBadData("groq bad response") from exc


def prediction_odds(query: str | None = None) -> dict[str, Any]:
    """Polymarket events: jina reader (text mode -> raw JSON) then direct."""
    attempts: list[tuple[str, str | None]] = [
        ("https://r.jina.ai/https://gamma-api.polymarket.com", "text"),
        ("https://gamma-api.polymarket.com", None),
    ]
    for base, return_format in attempts:
        try:
            headers = {"X-Return-Format": return_format} if return_format else None
            response = httpx.get(
                f"{base}/events?active=true&closed=false&limit=50",
                timeout=30,
                headers=headers,
            )
            if response.status_code == 429:
                raise ProviderUnavailable(f"rate limited: {base}")
            body = json.loads(response.text)
            events = body if isinstance(body, list) else []
            if query:
                query_low = query.lower()
                events = [e for e in events if query_low in str(e.get("title", "")).lower()]
            rows = [
                {
                    "title": e.get("title"),
                    "volume24h": e.get("volume24hr"),
                    "liquidity": e.get("liquidity"),
                    "end": e.get("endDate"),
                }
                for e in events[:20]
            ]
            return {"source": base, "events": rows}
        except (ProviderUnavailable, ProviderBadData, ValueError):
            continue
    raise ProviderUnavailable("polymarket unreachable via jina and direct")


def fear_greed() -> dict[str, Any]:
    body = _get_json("https://api.alternative.me/fng/?limit=7")
    data = body.get("data", []) if isinstance(body, dict) else []
    return {
        "series": [
            {"t": d.get("timestamp"), "v": d.get("value"), "label": d.get("value_classification")}
            for d in data
        ]
    }


def gdelt_events(query: str = "stock market", max_records: int = 20) -> dict[str, Any]:
    body = _get_json(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        {"query": query, "mode": "artlist", "maxrecords": min(max_records, 50), "format": "json"},
    )
    articles = body.get("articles", []) if isinstance(body, dict) else []
    return {
        "query": query,
        "articles": [
            {
                "title": a.get("title"),
                "url": a.get("url"),
                "source": a.get("sourceCommonName"),
                "date": a.get("seendate"),
            }
            for a in articles
        ],
    }
