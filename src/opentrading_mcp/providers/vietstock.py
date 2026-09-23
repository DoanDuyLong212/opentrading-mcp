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


def _seed_token_from_trading_agents() -> str:
    """Extra JWT seed from the Trading_Agents repo session (team-shared login).

    Priority: VIETSTOCK_COOKIE_LOGIN env -> Trading_Agents session.json ->
    "" (caller falls back to EMAIL/PASSWORD re-login).
    """
    for candidate in (
        _env("VIETSTOCK_SESSION_FILE"),
        "/home/doanlong/Trading_Agents/backend/mcp/tools/vietstock/session.json",
    ):
        if not candidate:
            continue
        try:
            with open(candidate, encoding="utf-8") as fh:
                saved = json.load(fh)
            token = str((saved.get("cookies") or {}).get("CookieLogin", ""))
            if token and _decode_jwt_exp(token) > time.time() + 300:
                return token
        except (OSError, ValueError):
            continue
    return ""


def auth_status() -> dict[str, Any]:
    token = _env("VIETSTOCK_COOKIE_LOGIN") or _seed_token_from_trading_agents()
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
    jwt = _env("VIETSTOCK_COOKIE_LOGIN") or _seed_token_from_trading_agents()
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
            parsed = json.loads(text)
        except ValueError as exc:
            raise ProviderBadData(
                f"vietstock non-JSON {response.status_code}: {text[:120]}"
            ) from exc
        error = parsed.get("errorModel") if isinstance(parsed, dict) else None
        if isinstance(error, dict) and error.get("ErrorCode"):
            code = str(error.get("ErrorCode"))
            message = str(error.get("ErrorMessage", code))
            if "Permission" in code or "Upgrade" in code or "Limit" in code:
                raise ProviderAuthMissing(f"vietstock {code}: {message}")
            raise ProviderBadData(f"vietstock {code}: {message}")
        return parsed
    raise ProviderUnavailable(f"vietstock retry exhausted: {path}")


def _post_json(
    path: str, payload: dict[str, Any], timeout: int = 30, referer: str | None = None
) -> Any:
    """JSON variant for /FinancialStatement* endpoints (same cookie session)."""
    try:
        client = _session_client()
    except (ProviderAuthMissing, ProviderBadData):
        raise
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock session unreachable: {path}") from exc
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": referer or f"{BASE}/",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        response = client.post(f"{BASE}{path}", json=payload, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderUnavailable(f"vietstock timeout: {path}") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock unreachable: {path}") from exc
    if response.status_code == 401:
        raise ProviderAuthMissing("vietstock session rejected")
    try:
        parsed = json.loads(response.text.encode().decode("utf-8-sig"))
    except ValueError as exc:
        raise ProviderBadData(f"vietstock non-JSON {response.status_code}") from exc
    error = parsed.get("errorModel") if isinstance(parsed, dict) else None
    if isinstance(error, dict) and error.get("ErrorCode"):
        raise ProviderAuthMissing(
            f"vietstock {error.get('ErrorCode')}: {error.get('ErrorMessage')}"
        )
    return parsed


BCTC_TIDS = (2, 3, 4, 5, 9)
BCTC_TIDS_FULL = (1, 2, 3, 4, 5, 9, 12)


def build_list_params(symbol: str, years: int = 3, full: bool = False) -> list[dict[str, Any]]:
    current = time.gmtime().tm_year
    tids = BCTC_TIDS_FULL if full else BCTC_TIDS
    params: list[dict[str, Any]] = []
    index = 1
    for year in range(current, current - years, -1):
        for tid in tids:
            params.append(
                {
                    "Index": index,
                    "YearPeriod": year,
                    "AuditedStatusId": "-1",
                    "UnitedId": "-1",
                    "ReportTermId": tid,
                    "StockCode": symbol.upper(),
                    "Unit": "1",
                    "ColumnIndex": index,
                }
            )
            index += 1
    return params


def financial_terms() -> Any:
    return _post_json("/financedata/GetListReportTerm", {})


def financial_norms(btype: int = 1) -> Any:
    return _post_json(
        "/FinancialStatement/BCTC_GetChiTieuForTable",
        {"BusinessTypeId": btype, "ReportComponentCodes": "CD,KQ,LCTT"},
    )


def financial_values(
    symbol: str, btype: int = 1, years: int = 3, tids: list[int] | None = None
) -> Any:
    norms = _post_json(
        "/FinancialStatement/BCTC_GetChiTieuForTable",
        {"BusinessTypeId": btype, "ReportComponentCodes": "CD,KQ,LCTT"},
    )
    norm_list = norms if isinstance(norms, list) else norms.get("data", [])
    ids = [
        str(n.get("ReportNormID") or n.get("ReportNormId") or "")
        for n in norm_list
        if isinstance(n, dict) and (n.get("ReportNormID") or n.get("ReportNormId"))
    ]
    if not ids:
        raise ProviderBadData("vietstock returned no norms")
    params = build_list_params(symbol, years)
    if tids:
        params = [p for p in params if p["ReportTermId"] in tids]
    body = _post_json(
        "/FinancialStatement/BCTC_LoadReportData_Async",
        {"ReportNormIds": ",".join(ids), "ListParams": params},
        timeout=60,
    )
    return {"symbol": symbol.upper(), "norms": len(ids), "rows": body.get("data", body)}


def company_info(symbol: str) -> Any:
    return _post_json("/FinancialStatement/BCTC_CompanyByCodes", {"stockCodes": symbol.upper()})


def overview_trading(symbol: str) -> Any:
    return _post("/data/GetStockDeal_OverviewTrading", {"stockCode": symbol.upper()})


def documents(symbol: str, page_size: int = 60) -> Any:
    return _post("/data/GetDocument", {"code": symbol.upper(), "page": 1, "pageSize": page_size})


def reports_search(symbol: str = "", page_size: int = 50) -> Any:
    return _post_json(
        "/CompanyReport/CompanyReportSearch",
        {
            "searchModel": {
                "stockCode": symbol.upper() or None,
                "keywords": None,
                "fromDate": None,
                "toDate": None,
                "categoryId": 2,
                "pageSize": min(page_size, 50),
                "pageIndex": 1,
            }
        },
        referer=f"{BASE}/truy-xuat-du-lieu/tin-tuc.htm",
    )


def industry_tree() -> Any:
    return _post_industry_form("/FinancialStatementSector/GetTreeViewIndustryGICS", {})


def _post_industry_form(path: str, payload: dict[str, Any]) -> Any:
    """Industry endpoints use form posts with the analysis-page referer."""
    try:
        client = _session_client()
    except (ProviderAuthMissing, ProviderBadData):
        raise
    try:
        token = client.headers.get("__RequestVerificationToken") or _form_token(client)
        response = client.post(
            f"{BASE}{path}",
            data={**{k: str(v) for k, v in payload.items()}, "__RequestVerificationToken": token},
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE}/truy-xuat-du-lieu/phan-tich-nganh.htm",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock unreachable: {path}") from exc
    try:
        return json.loads(response.text.encode().decode("utf-8-sig"))
    except ValueError as exc:
        raise ProviderBadData(
            f"vietstock non-JSON {response.status_code}: {response.text[:80]}"
        ) from exc


def stock_industry(industry_id: int) -> Any:
    return _post_json(
        "/FinancialStatementSector/GetBusinessTypeIDCompanyByGICS", {"IndustryID": industry_id}
    )


def industry_heatmap() -> Any:
    return _post_industry_form(
        "/Data/GetHeatmapGICS",
        {"industryCode": "0", "detailIndustry": "true", "detailStockCode": "false"},
    )


def top_liquidity(index: str = "VNINDEX") -> Any:
    return _post("/Data/GetTopStockLiquidity", {"index": index})


def gics_index() -> Any:
    return _post("/data/GetGICSIndexMain", {})


def currency() -> Any:
    return _post("/data/GetCurrency", {})


def market_info(symbol: str = "") -> Any:
    return _post("/data/marketinfo", {"symbol": symbol.upper()} if symbol else {})


def news_search(query: str, page_size: int = 20) -> Any:
    try:
        response = httpx.post(
            "https://dc.vietstock.vn/api/Search/SearchArticleNewAsync",
            json={"keySearch": query, "pageSize": min(page_size, 50), "filterTime": "all"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable("vietstock search unreachable") from exc
    try:
        return json.loads(response.text.encode().decode("utf-8-sig"))
    except ValueError as exc:
        raise ProviderBadData("vietstock search bad json") from exc


def selftrading() -> Any:
    return _post("/data/KQGDGiaoDichTuDoanhChart", {})


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
