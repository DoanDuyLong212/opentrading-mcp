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

from opentrading_mcp.providers.circuit import guarded
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


@guarded("vietstock")
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


@guarded("vietstock")
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
    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        code = err.get("ErrorCode", "package-limited") if isinstance(err, dict) else err
        raise ProviderAuthMissing(f"vietstock package limited: {code}")
    return {"symbol": symbol.upper(), "norms": len(ids), "rows": body.get("data", body)}


def company_info(symbol: str) -> Any:
    return _post_json("/FinancialStatement/BCTC_CompanyByCodes", {"stockCodes": symbol.upper()})


def overview_trading(symbol: str) -> Any:
    return _post("/data/GetStockDeal_OverviewTrading", {"stockCode": symbol.upper()})


def documents(symbol: str, page_size: int = 60) -> Any:
    return _post("/data/GetDocument", {"code": symbol.upper(), "page": 1, "pageSize": page_size})


def reports_search(symbol: str = "", page_size: int = 50, keywords: str | None = None) -> Any:
    return _post_json(
        "/CompanyReport/CompanyReportSearch",
        {
            "searchModel": {
                "stockCode": symbol.upper() or None,
                "keywords": keywords or None,
                "fromDate": None,
                "toDate": None,
                "categoryId": 2,
                "pageSize": min(page_size, 50),
                "pageIndex": 1,
            }
        },
        referer=f"{BASE}/truy-xuat-du-lieu/tin-tuc.htm",
    )


def _ms_date(raw: Any) -> str | None:
    """Parse /Date(1784739600000)/ to YYYY-MM-DD; pass through ISO strings."""
    import datetime

    text = str(raw or "")
    match = re.search(r"/Date\((\d+)([+-]\d+)?\)/", text)
    if match:
        try:
            tz = datetime.timezone(datetime.timedelta(hours=7))
            ts = datetime.datetime.fromtimestamp(int(match.group(1)) / 1000, tz=tz)
            return ts.date().isoformat()
        except (ValueError, OSError):
            return None
    return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else None


EVENT_TYPE_IDS = {"dividends": 1, "listings": 2, "meetings": 5}


def event_calendar(event: str = "dividends", symbol: str = "", limit: int = 20) -> Any:
    """Corporate-action calendar rows (no earnings-date type exists upstream)."""
    if event not in EVENT_TYPE_IDS:
        raise ProviderBadData(f"unknown event {event!r} (dividends|listings|meetings)")
    raw = _post(
        "/data/eventstypedata",
        {
            "eventTypeID": EVENT_TYPE_IDS[event],
            "code": symbol.upper(),
            "page": 1,
            "pageSize": max(min(int(limit), 100), 1),
            "orderBy": "Date1",
            "orderDir": "desc",
        },
    )
    rows = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else raw
    if not isinstance(rows, list):
        raise ProviderBadData("vietstock event calendar malformed")
    out = []
    for row in rows[: max(int(limit), 1)]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "event_id": row.get("EventID"),
                "code": row.get("Code"),
                "note": row.get("Note"),
                "ex_date": _ms_date(row.get("GDKHQDate")),
                "record_date": _ms_date(row.get("NDKCCDate")),
                "file_url": row.get("FileUrl"),
            }
        )
    return out


def negotiated_trades(
    symbol: str, from_date: str, to_date: str, limit: int = 30
) -> list[dict[str, Any]]:
    """Daily matched (MT_*) vs negotiated put-through (PT_*) splits per symbol."""
    raw = _post(
        "/data/gettradingresult",
        {
            "Code": symbol.upper(),
            "PageIndex": 1,
            "PageSize": max(min(int(limit), 100), 1),
            "FromDate": from_date,
            "ToDate": to_date,
            "Cols": "TKLGD,TGTGD,VHTT,TGG,DC,TGPTG,KLGDKL,GTGDKL",
            "ExchangeID": 1,
        },
    )
    rows = raw.get("Data") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ProviderBadData("vietstock trading result malformed")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "date": _ms_date(row.get("TradingDate")),
                "close": row.get("ClosePrice"),
                "mt_vol": row.get("MT_TotalVol"),
                "mt_val": row.get("MT_TotalVal"),
                "pt_vol": row.get("PT_TotalVol"),
                "pt_val": row.get("PT_TotalVal"),
            }
        )
    return out


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


def stock_industry(industry_id: int) -> list[dict[str, Any]]:
    """Company mappings for a GICS node (level 2-3 ids); empty when upstream has none."""
    raw = _post_json(
        "/FinancialStatementSector/GetBusinessTypeIDCompanyByGICS", {"IndustryID": industry_id}
    )
    if isinstance(raw, dict):
        model = raw.get("model", [])
        if isinstance(model, list):
            return [r for r in model if isinstance(r, dict)]
    raise ProviderBadData("vietstock industry stocks malformed")


_DETAIL_STATEMENTS = {
    "KQKD": (
        "GetListReportNorm_KQKD_ByStockCode",
        "KQKD_GetListReportData",
        "GetReportDataDetailValue_KQKD_ByReportDataIds",
    ),
    "CDKT": (
        "GetListReportNormByStockCode",
        "CDKT_GetListReportData",
        "GetReportDataDetailValueByReportDataIds",
    ),
    "LCTT": (
        "GetListReportNorm_LCTT_ByStockCode",
        "LCTT_GetListReportData",
        "GetReportDataDetailValue_LCTT_ByReportDataIds",
    ),
    "TM": (
        "GetListReportNorm_TM_ByStockCode",
        "TM_GetListReportData",
        "GetReportDataDetailValue_TM_ByReportDataIds",
    ),
    "BCTT": (
        "GetListReportNorm_BCTT_ByStockCode",
        "BCTT_GetListReportData",
        "GetReportDataDetailValue_BCTT_ByReportDataIds",
    ),
}

_DETAIL_FILTER = {
    "StockCode": "",
    "UnitedId": -1,
    "AuditedStatusId": -1,
    "Unit": 1000000000,
    "IsNamDuongLich": True,
    "PeriodType": "QUY",
    "SortTimeType": "Time_ASC",
}


def financial_detail(
    symbol: str, statement: str = "KQKD", periods_n: int = 8
) -> dict[str, Any]:
    """Free detailed statements via /data/* chain (P11, no paid package).

    norms -> periods -> batched detail values. Unit is VND billions.
    """
    code = statement.strip().upper()
    if code not in _DETAIL_STATEMENTS:
        raise ProviderBadData(f"unknown statement {statement!r} (KQKD|CDKT|LCTT|TM|BCTT)")
    norm_ep, per_ep, val_ep = (f"/data/{name}" for name in _DETAIL_STATEMENTS[code])
    norms_raw = _post(norm_ep, {"stockCode": symbol.upper()})
    norms = norms_raw.get("data", norms_raw) if isinstance(norms_raw, dict) else norms_raw
    if not isinstance(norms, list) or not norms:
        raise ProviderBadData(f"vietstock no norms for {symbol} {code}")
    filt = {**_DETAIL_FILTER, "StockCode": symbol.upper()}
    per_raw = _post(per_ep, filt)
    periods = per_raw.get("data", per_raw) if isinstance(per_raw, dict) else per_raw
    if not isinstance(periods, list) or not periods:
        raise ProviderBadData(f"vietstock no periods for {symbol} {code}")
    periods = periods[: max(int(periods_n), 1)]
    ids: list[Any] = []
    for period in periods:
        if not isinstance(period, dict):
            continue
        for key in ("ReportDataID", "ReportDataId", "ID", "id"):
            if period.get(key) is not None:
                ids.append(period[key])
                break
    if not ids:
        raise ProviderBadData(f"vietstock periods carry no ids for {symbol} {code}")
    val_raw = _post(
        val_ep,
        {
            "StockCode": symbol.upper(),
            "Unit": 1000000000,
            "TypeCompare": "1",
            "listReportDataIds": ids,
        },
    )
    rows = val_raw.get("data", val_raw) if isinstance(val_raw, dict) else val_raw
    if not isinstance(rows, list):
        raise ProviderBadData(f"vietstock detail values malformed for {symbol} {code}")
    return {
        "symbol": symbol.upper(),
        "statement": code,
        "unit": "VNDbn",
        "norms": len(norms) if isinstance(norms, list) else 0,
        "periods": ids,
        "rows": rows,
    }


def industry_heatmap() -> Any:
    return _post_industry_form(
        "/Data/GetHeatmapGICS",
        {"industryCode": "0", "detailIndustry": "true", "detailStockCode": "false"},
    )


def top_liquidity(index: str = "VNINDEX") -> Any:
    return _post("/Data/GetTopStockLiquidity", {"index": index})


def gics_index(group: int = 1) -> Any:
    """GICS index group rows. Requires type (P10); groups differ by index set."""
    return _post("/data/GetGICSIndexMain", {"type": group})


def currency() -> Any:
    return _post("/data/GetCurrency", {})


EXCHANGE_TYPE_IDS = {"HOSE": 1, "HNX": 2, "UPCOM": 3}


def market_info_board(exchange: str = "HOSE") -> Any:
    """Per-exchange board row (index, breadth, put-through). Requires type (P10)."""
    venue = exchange.strip().upper()
    if venue not in EXCHANGE_TYPE_IDS:
        raise ProviderBadData(f"unknown exchange {exchange!r} (HOSE|HNX|UPCOM)")
    return _post("/data/marketinfo", {"type": EXCHANGE_TYPE_IDS[venue]})


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
        parsed = json.loads(response.text.encode().decode("utf-8-sig"))
    except ValueError as exc:
        raise ProviderBadData("vietstock search bad json") from exc
    return _coerce_articles(parsed)


def _coerce_articles(payload: Any) -> list[dict[str, Any]]:
    """Normalize article search shapes; error-message dicts become ProviderBadData.

    The dc endpoint returns {"Message": "No HTTP resource..."} when the route
    is gone — previously passed through as available with garbage data.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "articles", "items", "results"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [r for r in nested if isinstance(r, dict)]
        msg = payload.get("Message") or payload.get("message") or ""
        if isinstance(msg, str) and msg.strip():
            raise ProviderBadData(f"vietstock search error: {msg.strip()[:200]}")
    raise ProviderBadData("vietstock search malformed")


def nn_flow_chart() -> Any:
    """Foreign buy/sell chart. Requires selectType/code/type/isRealTime (P10)."""
    return _post(
        "/data/KQGDGiaoDichNDTNNChart",
        {"selectType": 1, "code": "", "type": 1, "isRealTime": False},
    )


def selftrading_chart() -> Any:
    """Prop-desk buy/sell chart. Requires selectType/code/type (P10)."""
    return _post(
        "/data/KQGDGiaoDichTuDoanhChart",
        {"selectType": 1, "code": "", "type": 1},
    )


def selftrading() -> Any:
    return selftrading_chart()


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


def market_price(board_type: int = 2) -> Any:
    return _post("/data/getmarketprice", {"type": board_type})


def indicator_categories() -> Any:
    return _post("/Macro/GetIndicatorCategoryData", {})
