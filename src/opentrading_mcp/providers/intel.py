"""Direct HTTP intel providers: FRED, WorldBank, Fireant, Groq, odds, GDELT, fear/greed."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)

_CLIENT: httpx.Client | None = None


def _client() -> httpx.Client:
    """Shared connection-pooled HTTP client (keep-alive across calls).

    Successive one-shot httpx.get() calls re-pay TCP+TLS handshake every time
    (~11s TLS to some hosts from certain networks); a pooled client pays it
    once per process. Thread-safe: calls run on run_blocking worker threads
    and httpx connection pools are thread-safe. Lazily built so importing this
    module never opens sockets (tests without network stay fast).
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.Client(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
            timeout=httpx.Timeout(20.0),
        )
    return _CLIENT


def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    try:
        response = _client().get(url, params=params, timeout=timeout)
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


@guarded("fred")
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


@guarded("worldbank")
def worldbank_country(iso3: str, indicator: str) -> dict[str, Any]:
    body = _get_json(
        f"https://api.worldbank.org/v2/country/{iso3}/indicator/{indicator}",
        {"format": "json", "per_page": 60},
    )
    rows = body[1] if isinstance(body, list) and len(body) > 1 else []
    points = [{"t": r.get("date"), "v": r.get("value")} for r in rows if r.get("value") is not None]
    return {"country": iso3.upper(), "indicator": indicator, "points": points}


@guarded("fireant")
def fireant_posts(symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    token = os.environ.get("FIREANT_TOKEN", "").strip()
    if not token:
        raise ProviderAuthMissing("FIREANT_TOKEN is not set")
    base = os.environ.get("FIREANT_API_BASE", "https://restv2.fireant.vn").strip()
    params: dict[str, Any] = {"type": 1, "offset": 0, "limit": min(limit, 50)}
    if symbol:
        params["symbol"] = symbol.upper()
    try:
        response = _client().get(
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
        out.append(_fireant_post_row(post))
    return out


def _fireant_post_row(post: dict[str, Any]) -> dict[str, Any]:
    """Normalize one Fireant post (list posts use postID/totalLikes)."""
    user = post.get("user") or {}
    uname = (
        post.get("userName")
        or (user.get("name") if isinstance(user, dict) else None)
        or (user.get("username") if isinstance(user, dict) else None)
    )
    likes = post.get("totalLikes")
    if likes is None:
        likes = post.get("likeCount", post.get("likes", 0))
    return {
        "id": post.get("postID") or post.get("id") or post.get("postId") or post.get("post_id"),
        "user": uname,
        "text": (post.get("description") or post.get("content") or "")[:500],
        "symbols": [
            t.get("symbol") for t in (post.get("taggedSymbols") or []) if isinstance(t, dict)
        ],
        "likes": likes,
        "replies": post.get("totalReplies", 0),
        "date": post.get("date"),
    }


@guarded("fireant")
def fireant_thread(post_id: int | str, limit: int = 20) -> dict[str, Any]:
    """One post + its replies (rumor threads live in replies)."""
    token = os.environ.get("FIREANT_TOKEN", "").strip()
    if not token:
        raise ProviderAuthMissing("FIREANT_TOKEN is not set")
    base = os.environ.get("FIREANT_API_BASE", "https://restv2.fireant.vn").strip()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        root_resp = _client().get(f"{base}/posts/{post_id}", headers=headers, timeout=30)
        root_body = root_resp.json() if root_resp.status_code == 200 else None
        rep_resp = _client().get(
            f"{base}/posts/{post_id}/replies",
            params={"limit": min(limit, 50)},
            headers=headers,
            timeout=30,
        )
        rep_body = rep_resp.json()
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("fireant unreachable") from exc
    except ValueError as exc:
        raise ProviderBadData("fireant bad json") from exc
    root = root_body if isinstance(root_body, dict) else None
    items = (
        rep_body
        if isinstance(rep_body, list)
        else (rep_body.get("posts") or rep_body.get("data") or [])
        if isinstance(rep_body, dict)
        else []
    )
    replies = [_fireant_post_row(p) for p in items[:limit] if isinstance(p, dict)]
    return {
        "post": _fireant_post_row(root) if root else None,
        "replies": replies,
        "reply_count": len(replies),
    }


@guarded("groq")
def groq_chat(system_msg: str, user_msg: str, max_tokens: int = 300) -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ProviderAuthMissing("GROQ_API_KEY is not set")
    model = os.environ.get("GROQ_MODEL_SENTIMENT", "llama-3.1-8b-instant")
    try:
            response = _client().post(
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


def _event_rows(events: list[Any], limit: int) -> list[dict[str, Any]]:
    """Shape Polymarket events into agent-readable rows with odds (P14)."""
    rows: list[dict[str, Any]] = []
    for event in events[:limit]:
        if not isinstance(event, dict):
            continue
        tag_labels = [
            t.get("label")
            for t in event.get("tags") or []
            if isinstance(t, dict) and t.get("label")
        ]
        best: dict[str, Any] | None = None
        best_vol = -1.0
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            try:
                vol = float(market.get("volume24hr") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            if vol > best_vol:
                best_vol = vol
                best = market
        outcomes: list[dict[str, Any]] = []
        if best:
            raw_out = best.get("outcomes")
            raw_prices = best.get("outcomePrices")
            names = []
            if isinstance(raw_out, str):
                try:
                    names = json.loads(raw_out)
                except ValueError:
                    names = []
            elif isinstance(raw_out, list):
                names = raw_out
            prices = []
            if isinstance(raw_prices, str):
                try:
                    prices = json.loads(raw_prices)
                except ValueError:
                    prices = []
            elif isinstance(raw_prices, list):
                prices = raw_prices
            for name, price in zip(names, prices, strict=False):
                try:
                    prob = round(float(price) * 100, 1)
                except (TypeError, ValueError):
                    prob = None
                outcomes.append({"outcome": name, "prob_pct": prob})
        rows.append(
            {
                "title": event.get("title"),
                "slug": event.get("slug"),
                "tags": tag_labels[:8],
                "volume24h": event.get("volume24hr"),
                "liquidity": event.get("liquidity"),
                "end": event.get("endDate"),
                "top_market": (best or {}).get("question"),
                "outcomes": outcomes,
            }
        )
    return rows


@guarded("polymarket")
def prediction_odds(
    query: str | None = None, tag: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """Polymarket events: jina reader (text mode -> raw JSON) then direct."""
    attempts: list[tuple[str, str | None]] = [
        ("https://r.jina.ai/https://gamma-api.polymarket.com", "text"),
        ("https://gamma-api.polymarket.com", None),
    ]
    for base, return_format in attempts:
        try:
            headers = {"X-Return-Format": return_format} if return_format else None
            qs = "active=true&closed=false&limit=100&order=volume24hr&ascending=false"
            if tag:
                qs += f"&tag_slug={tag}"
            response = _client().get(
                f"{base}/events?{qs}",
                timeout=30,
                headers=headers,
            )
            if response.status_code == 429:
                raise ProviderUnavailable(f"rate limited: {base}")
            body = json.loads(response.text)
            events = body if isinstance(body, list) else []
            if query:
                query_low = query.lower()
                events = [
                    e
                    for e in events
                    if isinstance(e, dict)
                    and (
                        query_low in str(e.get("title", "")).lower()
                        or query_low in str(e.get("slug", "")).lower()
                        or query_low in str(e.get("description", "")).lower()
                    )
                ]
            if tag:
                tag_low = tag.lower()
                events = [
                    e
                    for e in events
                    if isinstance(e, dict)
                    and any(
                        tag_low in str(t.get("label", "")).lower()
                        or tag_low in str(t.get("slug", "")).lower()
                        for t in e.get("tags") or []
                        if isinstance(t, dict)
                    )
                ]
            events.sort(
                key=lambda e: float(e.get("volume24hr") or 0) if isinstance(e, dict) else 0,
                reverse=True,
            )
            return {"source": base, "events": _event_rows(events, limit)}
        except (ProviderUnavailable, ProviderBadData, ValueError, httpx.HTTPError):
            continue
    raise ProviderUnavailable("polymarket unreachable via jina and direct")


@guarded("polymarket")
def polymarket_event(slug: str) -> dict[str, Any]:
    """One Polymarket event detail by slug (all markets + prices) — P14."""
    import datetime

    attempts: list[tuple[str, str | None]] = [
        ("https://r.jina.ai/https://gamma-api.polymarket.com", "text"),
        ("https://gamma-api.polymarket.com", None),
    ]
    for base, return_format in attempts:
        try:
            headers = {"X-Return-Format": return_format} if return_format else None
            response = _client().get(
                f"{base}/events?slug={httpx.QueryParams({'slug': slug})['slug']}",
                timeout=30,
                headers=headers,
            )
            if response.status_code == 429:
                raise ProviderUnavailable(f"rate limited: {base}")
            body = json.loads(response.text)
            events = body if isinstance(body, list) else []
            if not events:
                continue
            event = events[0]
            markets: list[dict[str, Any]] = []
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                raw_out = market.get("outcomes")
                raw_prices = market.get("outcomePrices")
                names = json.loads(raw_out) if isinstance(raw_out, str) else raw_out or []
                prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices or []
                outcomes = []
                for name, price in zip(names, prices, strict=False):
                    try:
                        prob = round(float(price) * 100, 1)
                    except (TypeError, ValueError):
                        prob = None
                    outcomes.append({"outcome": name, "prob_pct": prob})
                markets.append(
                    {
                        "question": market.get("question"),
                        "outcomes": outcomes,
                        "volume24h": market.get("volume24hr"),
                        "end": market.get("endDate"),
                    }
                )
            return {
                "slug": slug,
                "title": event.get("title"),
                "description": str(event.get("description") or "")[:2000],
                "end": event.get("endDate"),
                "volume24h": event.get("volume24hr"),
                "liquidity": event.get("liquidity"),
                "markets": markets,
                "fetched_at": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        except (ProviderUnavailable, ValueError, httpx.HTTPError):
            continue
    raise ProviderUnavailable(f"polymarket event {slug!r} unreachable")


@guarded("alternative")
def fear_greed() -> dict[str, Any]:
    body = _get_json("https://api.alternative.me/fng/?limit=7")
    data = body.get("data", []) if isinstance(body, dict) else []
    return {
        "series": [
            {"t": d.get("timestamp"), "v": d.get("value"), "label": d.get("value_classification")}
            for d in data
        ]
    }


_GDELT_CACHE_TTL = 600
# GDELT 429 responses set this (monotonic seconds); see gdelt_events.
_GDELT_THROTTLED_UNTIL = 0.0
_GDELT_THROTTLE_COOLDOWN = 300.0


@guarded("gdelt")
def gdelt_events(query: str = "stock market", max_records: int = 20) -> dict[str, Any]:
    """GDELT article list with Redis cache + one 20s backoff retry (P15).

    GDELT throttles per-IP aggressively; the cache also keeps news_market /
    news_symbol / geo_intel / event_stats from hammering the same endpoint.
    A 429 sets a 5-minute throttle flag so follow-up calls fail fast instead
    of each burning ~40s on sleep+retry against a throttled endpoint.
    """
    import time

    global _GDELT_THROTTLED_UNTIL
    if time.monotonic() < _GDELT_THROTTLED_UNTIL:
        raise ProviderUnavailable("gdelt throttled, retry later")
    from opentrading_mcp.cache import cache_key
    from opentrading_mcp.providers.store import cache_get, cache_set

    key = cache_key("gdelt_events", f"{query}|{max_records}")
    hit = cache_get(key)
    if hit is not None:
        import json

        cached: dict[str, Any] = json.loads(hit)
        return cached
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": min(max_records, 50),
        "format": "json",
    }
    body = None
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            body = _get_json("https://api.gdeltproject.org/api/v2/doc/doc", params)
            break
        except ProviderUnavailable as exc:
            last_exc = exc
            if attempt == 1 and "rate limited" in str(exc):
                _GDELT_THROTTLED_UNTIL = time.monotonic() + _GDELT_THROTTLE_COOLDOWN
                time.sleep(20)
            else:
                raise
    if body is None:
        raise ProviderUnavailable(str(last_exc) if last_exc else "gdelt failed")
    articles = body.get("articles", []) if isinstance(body, dict) else []
    out = {
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
    cache_set(key, out, _GDELT_CACHE_TTL)
    return out
