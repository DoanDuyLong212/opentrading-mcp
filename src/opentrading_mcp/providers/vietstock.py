"""Vietstock provider (cookie session, mirrors Trading_Agents flow).

Real flow: GET / (CSRF __RequestVerificationToken + session cookies) ->
POST /Account/Login (form-encoded Email/Password/Remember +
__RequestVerificationToken) -> CookieLogin JWT cookie -> API POSTs with
browser headers (Accept json, Referer) on the same cookie session.
If the env JWT (VIETSTOCK_COOKIE_LOGIN) is still valid it seeds the
session; otherwise EMAIL/PASSWORD re-login runs automatically.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any

import httpx

from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)

BASE = "https://finance.vietstock.vn"
BROWSER_UA = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"

_session: httpx.Client | None = None
_session_at: float = 0.0
_REFRESH_INTERVAL = 600.0


def _decode_jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0.0


def _extract_form_token(html: str) -> str | None:
    match = re.search(
        r"name=[\"']?__RequestVerificationToken[\"']?[^>]*?value=[\"']?([^\"'\s>]+)",
        html,
    )
    return match.group(1) if match else None


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def auth_status() -> dict[str, Any]:
    token = _env("VIETSTOCK_COOKIE_LOGIN")
    if not token:
        return {"authenticated": False, "reason": "no jwt configured"}
    exp = _decode_jwt_exp(token)
    if exp and exp < time.time():
        return {"authenticated": False, "reason": "jwt expired"}
    return {"authenticated": True, "jwt_expires_at": int(exp) if exp else None}


def _login(client: httpx.Client) -> None:
    email = _env("VIETSTOCK_EMAIL")
    password = _env("VIETSTOCK_PASSWORD")
    if not email or not password:
        raise ProviderAuthMissing("VIETSTOCK_EMAIL/VIETSTOCK_PASSWORD are not set")
    home = client.get(f"{BASE}/", timeout=30)
    home.raise_for_status()
    form_token = _extract_form_token(home.text)
    if not form_token:
        raise ProviderBadData("vietstock homepage has no CSRF token")
    resp = client.post(
        f"{BASE}/Account/Login",
        data={
            "Email": email,
            "Password": password,
            "Remember": "true",
            "responseCaptchaLoginPopup": "",
            "__RequestVerificationToken": form_token,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE}/",
            "Origin": BASE,
        },
        timeout=30,
    )
    try:
        result = json.loads(resp.text.encode().decode("utf-8-sig"))
    except ValueError as exc:
        raise ProviderBadData(f"vietstock login not JSON: {resp.text[:120]}") from exc
    if not result.get("success"):
        message = (result.get("data") or {}).get("message", "login failed")
        raise ProviderAuthMissing(f"vietstock login rejected: {message}")


def _session_client() -> httpx.Client:
    global _session, _session_at
    now = time.time()
    if _session is not None and now - _session_at < _REFRESH_INTERVAL:
        return _session
    client = httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    jwt = _env("VIETSTOCK_COOKIE_LOGIN")
    exp = _decode_jwt_exp(jwt)
    if jwt and (not exp or exp > now + 300):
        client.cookies.set("CookieLogin", jwt, domain="finance.vietstock.vn")
    else:
        _login(client)
    _form_token(client)
    _session, _session_at = client, now
    return client


def _form_token(client: httpx.Client) -> str:
    try:
        home = client.get(f"{BASE}/", timeout=30)
        token = _extract_form_token(home.text)
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("vietstock homepage unreachable") from exc
    if not token:
        raise ProviderBadData("vietstock homepage has no CSRF token")
    client.headers["__RequestVerificationToken"] = token
    return token


def _post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
    try:
        client = _session_client()
    except (ProviderAuthMissing, ProviderBadData):
        raise
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock session unreachable: {path}") from exc
    body = {k: ("" if v is None else str(v)) for k, v in payload.items()}
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": f"{BASE}/",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    for attempt in (1, 2):
        try:
            token = client.headers.get("__RequestVerificationToken") or _form_token(client)
            response = client.post(
                f"{BASE}{path}",
                data={**body, "__RequestVerificationToken": token},
                headers=headers,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"vietstock timeout: {path}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"vietstock unreachable: {path}") from exc
        if response.status_code == 401:
            raise ProviderAuthMissing("vietstock session rejected")
        text = response.text.encode().decode("utf-8-sig")
        if text.startswith("<!DOCTYPE") or text.startswith("<html"):
            global _session_at
            _session_at = 0.0
            if attempt == 1:
                _session_client()
                continue
            raise ProviderBadData(f"vietstock HTML shell for {path} (session rejected?)")
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ProviderBadData(
                f"vietstock non-JSON {response.status_code}: {text[:120]}"
            ) from exc
    raise ProviderUnavailable(f"vietstock retry exhausted: {path}")


def financeinfo(symbol: str, period: str = "quarter") -> dict[str, Any]:
    term = 2 if period == "quarter" else 1
    pages = 3 if period == "quarter" else 1
    sections: list[Any] = []
    for page in range(1, pages + 1):
        sections.append(
            _post(
                "/data/financeinfo",
                {
                    "Code": symbol,
                    "Page": page,
                    "PageSize": 4,
                    "ReportTermType": term,
                    "ReportType": "BCTQ",
                    "Unit": 1,
                },
            )
        )
    return {"symbol": symbol, "period": period, "pages": sections}


def market_price() -> Any:
    return _post("/data/getmarketprice", {"type": 2})


def indicator_categories() -> Any:
    return _post("/Macro/GetIndicatorCategoryData", {})
