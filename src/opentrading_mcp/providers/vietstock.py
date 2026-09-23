"""Vietstock provider (JWT login flow, server-side session).

Flow: GET / (CSRF token) -> POST /Account/Login -> CookieLogin JWT ->
POST finance/macro endpoints. financeinfo mirror is the no-auth fallback
path used when JWT is absent.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)

BASE = "https://finance.vietstock.vn"


def _jwt() -> str:
    token = os.environ.get("VIETSTOCK_COOKIE_LOGIN")
    if not token:
        raise ProviderAuthMissing("VIETSTOCK_COOKIE_LOGIN is not set")
    return token


def _post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
    try:
        response = httpx.post(
            f"{BASE}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {_jwt()}"},
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"vietstock timeout: {path}") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock unreachable: {path}") from exc
    if response.status_code == 401:
        raise ProviderAuthMissing("vietstock jwt rejected")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderBadData(f"vietstock bad json: {path}") from exc


def auth_status() -> dict[str, Any]:
    try:
        _jwt()
    except ProviderAuthMissing:
        return {"authenticated": False}
    return {"authenticated": True}


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
