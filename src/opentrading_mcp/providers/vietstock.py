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
import unicodedata
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
    root = _env("TRADING_AGENTS_DIR") or os.path.expanduser("~/Trading_Agents")
    for candidate in (
        _env("VIETSTOCK_SESSION_FILE"),
        os.path.join(root, "backend/mcp/tools/vietstock/session.json"),
    ):
        if not candidate:
            continue
        path = candidate
        if not os.path.isabs(path):
            # Trading_Agents/.env stores this relative to that repo, but this
            # process runs elsewhere: resolve against the repo root, otherwise
            # the seed is silently never found.
            path = os.path.join(root, path)
        try:
            with open(path, encoding="utf-8") as fh:
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

# Term → label dùng chung cho financial_detail + báo kỳ bị loại trong warnings.
# 1 = cả năm, 9 = 6 tháng, 12 = 9 tháng (đồng bộ với financial_lctt, issue #37).
_DETAIL_TERM_LABELS = {1: "NAM", 2: "Q1", 3: "Q2", 4: "Q3", 5: "Q4", 9: "6T", 12: "9T"}


def _detail_session_post(path: str, data: dict[str, Any]) -> Any:
    """POST the /data detail chain via the browser-session when seeded,
    else the JWT login session.

    Verified 2026-10-08: the JWT login session serves real values for detail
    endpoints (the old "Package_Permission/HTML" claim no longer holds with a
    valid CookieLogin JWT) — HAR seed is now optional, not required.
    """
    try:
        client = har_client()
        token = _env("VIETSTOCK_PAGE_TOKEN") or _har_seed()[1]
        payload = {**{k: str(v) for k, v in data.items()}, "__RequestVerificationToken": token}
        response = client.post(f"{BASE}{path}", data=payload)
        raw = response.content.decode("utf-8-sig")
        if raw.startswith("<!DOCTYPE") or "<html" in raw[:60].lower():
            raise ProviderAuthMissing(f"vietstock {path} session rejected")
        return json.loads(raw)
    except ProviderAuthMissing:
        pass  # fall through to the JWT login session below
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock {path} unreachable: {exc}") from exc
    try:
        client = _session_client()
        token = _form_token(client)
        payload = {**{k: str(v) for k, v in data.items()}, "__RequestVerificationToken": token}
        response = client.post(
            f"{BASE}{path}",
            data=payload,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": f"{BASE}/",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30,
        )
        raw = response.content.decode("utf-8-sig")
        if raw.startswith("<!DOCTYPE") or "<html" in raw[:60].lower():
            raise ProviderAuthMissing(f"vietstock {path} session rejected")
        return json.loads(raw)
    except ProviderAuthMissing:
        raise
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock {path} unreachable: {exc}") from exc


def _batch_objects(key: str, objs: list[dict[str, Any]]) -> dict[str, str]:
    """Browser-style indexed form keys: key[i][Field]=value (P15 probe-verified)."""
    out: dict[str, str] = {}
    for i, obj in enumerate(objs):
        for field, value in obj.items():
            out[f"{key}[{i}][{field}]"] = str(value)
    return out


def financial_lctt(symbol: str, years: int = 2) -> dict[str, Any]:
    """Cash-flow statement via /FinancialStatement BCTC endpoints (Vietstock HAS LCTT).

    The /data detail-norms endpoint returns {} for LCTT, but BCTC_GetChiTieuForTable
    carries the full LCTT-GT section — load values via BCTC_LoadReportData_Async.
    Returns {symbol, unit VNDbn, periods, rows: [{norm_id, name, values}]}; periods are
    Q1..Q4/yyyy, 6T/yyyy (first six months, cumulative), 9T/yyyy or NAM/yyyy.
    """
    norms = financial_norms(1)
    nl = norms if isinstance(norms, list) else norms.get("data", [])
    if not isinstance(nl, list):
        raise ProviderBadData("vietstock norms malformed")
    start = next(
        (i for i, n in enumerate(nl)
         if isinstance(n, dict) and "lưu chuyển tiền tệ" in str(n.get("Name", "")).lower()
         and "gián tiếp" in str(n.get("Name", "")).lower()),
        None,
    )
    if start is None:
        raise ProviderBadData("vietstock has no LCTT section")
    ids: list[str] = []
    names: dict[str, str] = {}
    for n in nl[start + 1:]:
        if not isinstance(n, dict):
            continue
        nm = str(n.get("Name", "")).strip()
        nid = n.get("ReportNormID")
        # next top-level section ends the LCTT block
        if (nid is None or (isinstance(nid, int) and nid < 0)) and "lưu chuyển" not in nm.lower():
            break
        if isinstance(nid, int) and nid > 0:
            ids.append(str(nid))
            names[str(nid)] = nm
    if not ids:
        raise ProviderBadData("vietstock LCTT norms empty")
    params = build_list_params(symbol, max(int(years), 1), full=True)
    body = _post_json(
        "/FinancialStatement/BCTC_LoadReportData_Async",
        {"ReportNormIds": ",".join(ids), "ListParams": params},
        timeout=60,
    )
    if isinstance(body, dict) and body.get("error"):
        raise ProviderAuthMissing("vietstock BCTC package limited")
    rows = body.get("data", body) if isinstance(body, dict) else body
    if not isinstance(rows, list) or not rows:
        raise ProviderBadData(f"vietstock no LCTT values for {symbol}")
    # Term → label. 1 = cả năm, 9 = 6 tháng, 12 = 9 tháng (issue #37: term 9
    # từng bị gắn nhãn "NAM" sai, và term 1/12 không bao giờ được request).
    _TERM_LABELS = _DETAIL_TERM_LABELS  # một bảng nhãn kỳ duy nhất cho cả module
    # Thứ tự thời gian thực của kỳ kết thúc: (tháng, phụ). Q2 và 6T cùng kết
    # thúc tháng 6 (6T sau Q2), Q3/9T cùng tháng 9, Q4/NAM cùng tháng 12.
    # Sort theo term id sẽ xếp 6T/9T/NAM sai chỗ (issue #37).
    _TERM_ORDER = {2: (3, 0), 3: (6, 0), 9: (6, 1), 4: (9, 0), 12: (9, 1), 5: (12, 0), 1: (12, 1)}
    # periods from ACTUAL response terms (endpoint may lack latest quarters)
    seen_terms: list[tuple] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (r.get("YearPeriod"), r.get("ReportTermID"))
        if key not in seen_terms:
            seen_terms.append(key)
    seen_terms.sort(key=lambda k: (k[0] or 0, *_TERM_ORDER.get(k[1] or 0, (k[1] or 0, 0))))
    periods = [
        f"{_TERM_LABELS.get(tid, tid)}/{yr}" for yr, tid in seen_terms
    ]
    by_norm: dict[tuple, Any] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (str(r.get("ReportNormId")), r.get("YearPeriod"), r.get("ReportTermID"))
        by_norm[key] = r.get("Value")
    series = []
    for nid in ids:
        vals = []
        for yr, tid in seen_terms:
            v = by_norm.get((nid, yr, tid))
            try:
                # raw VND → VND billions (match detail shape)
                vals.append(round(float(v) / 1e9, 1) if v is not None else None)
            except (TypeError, ValueError):
                vals.append(None)
        if any(v is not None for v in vals):
            series.append({"norm_id": int(nid), "name": names[nid], "values": vals})
    if not series:
        raise ProviderBadData(f"vietstock LCTT all-empty for {symbol}")
    return {"symbol": symbol.upper(), "unit": "VNDbn", "periods": periods, "rows": series}


def annual_forensic_lines(symbol: str, *, years: tuple[int, int]) -> dict[str, Any]:
    """Raw annual VND lines from the existing BCTC endpoint, with report metadata.

    The response observed for FPT on 2026-10-24 has StockCode, YearPeriod,
    ReportTermID, UnitedName, audit and publication metadata on each line.
    It has no fiscal boundaries or revision order; the forensic adapter must
    verify a same-scope financeinfo annual report and matching anchor values
    before using any line. Never use ``financial_lctt`` here: it rounds to VNDbn
    and drops report identity.
    """
    # 3005 is an aggregate including seller advances; 3022 is customer trade
    # receivables, narrower than Compustat Receivables Total [2]. Preserve both
    # as observations; neither becomes canonical DSRI without a source bridge.
    # 2242 combines fixed-asset and investment-property depreciation/amortization
    # and cannot establish pure DEPI expense. 3083-3086 are observed gross and
    # accumulated PPE lines; strict DEPI v3 follows Appendix A's net PPE [8].
    ids = (
        2212, 2216, 2224, 2227, 2234, 2242, 2996, 2998, 3005, 3022,
        3035, 3036, 3078, 3083, 3084, 3085, 3086,
    )
    if (
        len(years) != 2
        or any(not isinstance(y, int) or isinstance(y, bool) or y < 1900 for y in years)
        or years[0] - years[1] != 1
    ):
        raise ProviderBadData("annual BCTC requires two consecutive fiscal years")
    # Keep the verified BCTC request shape but anchor its years to the actual
    # financeinfo window. In early 2027, a still-current FY2025 report needs
    # FY2024 comparison; wall-clock build_list_params(years=3) would lose it.
    templates = [
        p for p in build_list_params(symbol, years=2, full=True)
        if p["ReportTermId"] == 1
    ]
    params = [{**p, "YearPeriod": year} for p, year in zip(templates, years, strict=True)]
    raw = _post_json(
        "/FinancialStatement/BCTC_LoadReportData_Async",
        {"ReportNormIds": ",".join(map(str, ids)), "ListParams": params},
        timeout=60,
    )
    rows = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ProviderBadData("vietstock annual BCTC lines malformed")
    return {"symbol": symbol.upper(), "unit_request": 1, "rows": rows}



def _united_id(period: dict[str, Any]) -> Any:
    return period.get("UnitedId", period.get("UnitedID"))


def _report_class(period: dict[str, Any]) -> str:
    """'consolidated' | 'parent' | 'unknown', đọc từ ``UnitedName`` (NFC, chữ thường).

    Dữ liệu thật (BVH, FPT 24/10/2026) có ``UnitedName`` nhưng KHÔNG có khóa
    ``UnitedId``, nên phân loại theo tên chứ không theo id.
    """
    name = unicodedata.normalize("NFC", str(period.get("UnitedName") or "")).lower()
    if "hợp nhất" in name:
        return "consolidated"
    if any(marker in name for marker in ("công ty mẹ", "riêng", "đơn lẻ")):
        return "parent"
    return "unknown"


def _report_scope(allowed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Giữ MỘT loại báo cáo cho cả chuỗi kỳ (issue #36); trả (kỳ giữ lại, căn cứ).

    - Có kỳ phân loại được theo tên: ưu tiên hợp nhất, không có thì lấy loại của kỳ
      mới nhất phân loại được; kỳ khác loại hoặc không rõ loại bị loại bỏ.
    - Không kỳ nào có tên nhưng có id: giữ id của kỳ mới nhất (hành vi của #40).
    - Không có cả hai: giữ nguyên (căn cứ None) — người gọi phải cảnh báo.
    """
    classes = [_report_class(p) for p in allowed]
    known = [c for c in classes if c != "unknown"]
    if known:
        target = "consolidated" if "consolidated" in known else known[-1]
        return [p for p, c in zip(allowed, classes, strict=True) if c == target], "UnitedName"
    ids = [_united_id(p) for p in allowed]
    if any(i is not None for i in ids):
        newest = next(i for i in reversed(ids) if i is not None)
        return [p for p, i in zip(allowed, ids, strict=True) if i == newest], "UnitedId"
    return list(allowed), None


# Dòng "TỔNG CỘNG TÀI SẢN" của các mẫu thường / ngân hàng / chứng khoán / bảo hiểm.
_TOTAL_ASSETS_NORMS = (2996, 4375, 4476, 3095)
# Tổng tài sản đổi quá hệ số này giữa hai kỳ liền kề: nghi trộn loại báo cáo.
_ASSET_JUMP = 3.0


def _period_label(year: Any, term_id: Any) -> str:
    label = _DETAIL_TERM_LABELS.get(int(term_id or 0), str(term_id or "?"))
    return f"{label}/{year}"


def financial_detail(symbol: str, statement: str = "KQKD", periods_n: int = 8) -> dict[str, Any]:
    """Full detailed statements via /data/* chain — REAL values on Standard pack (P15).

    Chain: norms (names for this stock) -> periods (filter
    IsShowData_Permission=True, latest N) -> values batched by 9 with
    browser-shaped listReportDataIds[i][...] objects. Unit VND billions.
    Raises ProviderAuthMissing when the session gate rejects.
    """
    code = statement.strip().upper()
    if code not in _DETAIL_STATEMENTS:
        raise ProviderBadData(f"unknown statement {statement!r} (KQKD|CDKT|LCTT|TM|BCTT)")
    norm_ep, per_ep, val_ep = (f"/data/{name}" for name in _DETAIL_STATEMENTS[code])
    norms_raw = _detail_session_post(norm_ep, {"stockCode": symbol.upper()})
    norms = norms_raw.get("data", norms_raw) if isinstance(norms_raw, dict) else norms_raw
    if not isinstance(norms, list) or not norms:
        raise ProviderBadData(f"vietstock no norms for {symbol} {code}")
    filt = {**_DETAIL_FILTER, "StockCode": symbol.upper()}
    per_raw = _detail_session_post(per_ep, filt)
    periods = per_raw.get("data", per_raw) if isinstance(per_raw, dict) else per_raw
    if not isinstance(periods, list) or not periods:
        raise ProviderBadData(f"vietstock no periods for {symbol} {code}")
    allowed = [
        p for p in periods if isinstance(p, dict) and p.get("IsShowData_Permission") is not False
    ]
    # Issue #36: upstream trả cả báo cáo hợp nhất lẫn công ty mẹ. Trộn hai loại làm
    # QoQ sai (BVH: Q1 hợp nhất 307k tỷ vs Q2 công ty mẹ 19k tỷ). Giữ MỘT loại cho cả
    # chuỗi kỳ, báo rõ kỳ bị loại, và không bao giờ khẳng định "hợp nhất" khi không biết.
    scoped, basis = _report_scope(allowed)
    warnings: list[str] = []
    dropped = [p for p in allowed if not any(p is q for q in scoped)]
    if dropped:
        dropped_labels = ", ".join(
            _period_label(p.get("YearPeriod"), p.get("ReportTermID")) for p in dropped[:6]
        )
        warnings.append(
            f"vietstock mixed report types ({basis}) — kept one report type;"
            f" dropped {len(dropped)} period(s): {dropped_labels}"
        )
    if basis is None:
        warnings.append(
            "vietstock period list carries no report type (UnitedName/UnitedId):"
            " consolidated and parent-only periods may be mixed"
        )
    # Hai bản cùng kỳ (ví dụ soát xét và kiểm toán): giữ bản đứng sau trong danh sách.
    by_period: dict[tuple[Any, Any], dict[str, Any]] = {}
    for p in scoped:
        by_period[(p.get("YearPeriod"), p.get("ReportTermID"))] = p
    if len(by_period) < len(scoped):
        warnings.append(
            f"vietstock lists {len(scoped) - len(by_period)} duplicate period(s); kept the last"
        )
    scoped = [p for p in scoped if any(p is q for q in by_period.values())]
    kept = scoped[-max(int(periods_n), 1) :]
    if not kept:
        raise ProviderAuthMissing(f"vietstock no permitted periods for {symbol} {code}")
    batch = [
        {
            "Index": idx,
            "ReportDataID": p.get("ReportDataID"),
            "YearPeriod": p.get("YearPeriod"),
            "ReportTermID": p.get("ReportTermID"),
        }
        for idx, p in enumerate(kept)
    ]
    _TERM_LABELS = _DETAIL_TERM_LABELS
    period_labels = [
        _TERM_LABELS.get(int(p.get("ReportTermID") or 0), str(p.get("ReportTermID")))
        + f"/{p.get('YearPeriod')}"
        if code != "CTKH" and int(p.get("ReportTermID") or 0) in _TERM_LABELS
        else str(p.get("YearPeriod"))
        for p in kept
    ]
    val_data = {
        "StockCode": symbol.upper(),
        "Unit": 1000000000,
        "TypeCompare": "1",
        **_batch_objects("listReportDataIds", batch),
    }
    val_raw = _detail_session_post(val_ep, val_data)
    rows = val_raw.get("data", val_raw) if isinstance(val_raw, dict) else val_raw
    if not isinstance(rows, list):
        raise ProviderBadData(f"vietstock detail values malformed for {symbol} {code}")
    name_by_id = {
        n.get("ReportNormId") or n.get("ReportNormID"): (n.get("ReportNormName") or n.get("Name"))
        for n in norms
        if isinstance(n, dict)
    }
    series: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nid = row.get("ReportNormId") or row.get("ReportNormID")
        values = [
            row.get(f"Value{i}") if row.get(f"Value{i}") is not None else None
            for i in range(1, len(kept) + 1)
        ]
        series.append({"norm_id": nid, "name": name_by_id.get(nid), "values": values})
        if nid in _TOTAL_ASSETS_NORMS:
            # Phòng thủ thêm khi tên loại báo cáo sai/thiếu: tổng tài sản không nhảy
            # hàng chục lần giữa hai quý liền kề nếu cùng một pháp nhân.
            for i in range(1, len(values)):
                a, b = values[i - 1], values[i]
                if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > 0 < b:
                    if max(a, b) / min(a, b) > _ASSET_JUMP:
                        warnings.append(
                            f"total assets change x{max(a, b) / min(a, b):.1f} between"
                            f" {period_labels[i - 1]} and {period_labels[i]}:"
                            " possible consolidated/parent-only mix"
                        )
    classes = [_report_class(p) for p in kept]
    ids = {_united_id(p) for p in kept}
    return {
        "symbol": symbol.upper(),
        "statement": code,
        "unit": "VNDbn",
        "periods": period_labels,
        "rows": series,
        # Issue #36: loại báo cáo của chuỗi kỳ. consolidated chỉ True/False khi MỌI kỳ
        # giữ lại cùng một loại đã biết; còn lại là None (không khẳng định điều không biết).
        "report_type": {
            "UnitedId": next(iter(ids)) if len(ids) == 1 else None,
            "consolidated": (
                True if classes and all(c == "consolidated" for c in classes)
                else False if classes and all(c == "parent" for c in classes)
                else None
            ),
            "basis": basis,
            "periods": {
                label: p.get("UnitedName") for label, p in zip(period_labels, kept, strict=True)
            },
        },
        **({"warnings": warnings} if warnings else {}),
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


# Statement keys models pass (financial_detail's codes) → financeinfo section names.
_FINANCEINFO_ALIASES = {
    "kqkd": "Kết quả kinh doanh",
    "cdkt": "Báo cáo tình hình tài chính",
    "cstc": "Chỉ số tài chính",
    "ratios": "Chỉ số tài chính",
}


def _financeinfo_label(header: dict[str, Any]) -> str:
    term = str(header.get("TermCode") or "")
    year = header.get("YearPeriod")
    return f"{term}/{year}" if re.fullmatch(r"Q[1-4]", term) else str(year)


def align_financeinfo(
    raw: Any, statement: str = "all", periods_n: int | None = None
) -> tuple[dict[str, Any], list[str]]:
    """financeinfo pages → {periods, statements{name: [{..., values{period: v}}]}}.

    Each page holds period headers oldest→newest, but row ValueN belongs to the
    header whose ID is N, and ID counts down from the newest (Value1 = newest
    period). Read in list order the values run backwards, which made models
    swap quarters; keying every value by its period label removes the guess.
    IDs restart on each page (Row does not), so the mapping is per page.
    Returns (data, warnings); a page whose headers can't be mapped is skipped,
    and ProviderBadData when no page could be mapped.
    """
    raw = raw if isinstance(raw, dict) else {}
    warnings: list[str] = []
    labels: dict[str, tuple[int, int]] = {}  # label → sort key (year, term)
    sections: dict[str, dict[Any, dict[str, Any]]] = {}
    for n, page in enumerate(raw.get("pages") or [], start=1):
        parts = page if isinstance(page, list) else []
        headers = next(
            (
                p
                for p in parts
                if isinstance(p, list) and p and all(
                    isinstance(h, dict) and "YearPeriod" in h for h in p
                )
            ),
            None,
        )
        stmts = next((p for p in parts if isinstance(p, dict)), None)
        if not headers or stmts is None:
            continue
        ids = [h.get("ID") for h in headers]
        if not all(isinstance(i, int) for i in ids) or len(set(ids)) != len(ids):
            warnings.append(f"page {n}: period headers without unique IDs, skipped")
            continue
        by_id = {h["ID"]: _financeinfo_label(h) for h in headers}
        page_labels = list(by_id.values())
        dupes = sorted({lbl for lbl in page_labels if page_labels.count(lbl) > 1})
        if dupes:
            # e.g. a consolidated and a parent-only report for one quarter: both map to
            # one label and only the first header's values are kept.
            warnings.append(f"page {n}: headers share period label {', '.join(dupes)}")
        for h in headers:
            labels[_financeinfo_label(h)] = (
                int(h.get("YearPeriod") or 0),
                int(h.get("ReportTermID") or 0),
            )
        for name, rows in stmts.items():
            out = sections.setdefault(str(name), {})
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                key = row.get("ReportNormID") or row.get("Name")
                entry = out.setdefault(
                    key,
                    {
                        "norm_id": row.get("ReportNormID"),
                        "name": str(row.get("Name") or "").strip(),
                        "name_en": str(row.get("NameEn") or "").strip(),
                        "unit": row.get("Unit") or "VND",
                        "values": {},
                    },
                )
                for hid, label in by_id.items():
                    # earlier pages are newer — keep their value on overlap
                    entry["values"].setdefault(label, row.get(f"Value{hid}"))
    periods = sorted(labels, key=labels.__getitem__)
    if not periods:
        raise ProviderBadData(
            f"vietstock financeinfo: no usable period headers for {raw.get('symbol')}"
            + (f" ({'; '.join(warnings)})" if warnings else "")
        )
    if periods_n is not None:
        periods = periods[-max(int(periods_n), 1):]
    wanted = statement.strip()
    if wanted.lower() != "all":
        target = _FINANCEINFO_ALIASES.get(wanted.lower(), wanted).lower()
        picked = {k: v for k, v in sections.items() if target in k.lower()}
        if picked:
            sections = picked
        else:
            warnings.append(
                f"statement {statement!r} not found (have: {', '.join(sections)}), "
                "returning all"
            )
    return {
        "symbol": str(raw.get("symbol") or "").upper(),
        "period": raw.get("period"),
        "periods": periods,
        "statements": {
            name: [
                {**r, "values": {p: r["values"].get(p) for p in periods}}
                for r in rows.values()
            ]
            for name, rows in sections.items()
        },
    }, warnings


def market_price(board_type: int = 2) -> Any:
    return _post("/data/getmarketprice", {"type": board_type})


def indicator_categories() -> Any:
    return _post("/Macro/GetIndicatorCategoryData", {})


# ------------------------------------------------------------------ P14: HAR session


def _har_seed() -> tuple[str, str]:
    """(cookie_header, page_token) for the browser-session replay mode.

    Priority: VIETSTOCK_COOKIE_HEADER + VIETSTOCK_PAGE_TOKEN env → newest
    docs/*.har (VIETSTOCK_HAR_FILE overrides). Empty strings when absent.
    """
    cookie = _env("VIETSTOCK_COOKIE_HEADER")
    token = _env("VIETSTOCK_PAGE_TOKEN")
    if cookie and token:
        return cookie, token
    import glob

    candidates = [_env("VIETSTOCK_HAR_FILE")] or []
    candidates += sorted(glob.glob("docs/*.har"), reverse=True)
    for path in candidates:
        if not path:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                har = json.load(fh)
        except (OSError, ValueError):
            continue
        for entry in har.get("log", {}).get("entries", []):
            if "finance.vietstock.vn" not in str(entry.get("request", {}).get("url", "")):
                continue
            if not cookie:
                for header in entry.get("request", {}).get("headers", []):
                    if header.get("name", "").lower() == "cookie":
                        cookie = str(header.get("value", ""))
            if not token:
                for param in entry.get("request", {}).get("postData", {}).get("params", []):
                    if param.get("name") == "__RequestVerificationToken":
                        token = str(param.get("value", ""))
            if cookie and token:
                return cookie, token
    return "", ""


_HAR_CLIENT: httpx.Client | None = None


def har_client() -> httpx.Client:
    """Browser-session replay client (full cookie jar + page token)."""
    global _HAR_CLIENT
    if _HAR_CLIENT is not None:
        return _HAR_CLIENT
    cookie, _token = _har_seed()
    if not cookie:
        raise ProviderAuthMissing("VIETSTOCK_COOKIE_HEADER/HAR not configured")
    _HAR_CLIENT = httpx.Client(
        timeout=30,
        headers={
            "User-Agent": BROWSER_UA,
            "Cookie": cookie,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE,
            "Referer": f"{BASE}/vi-mo/du-lieu",
        },
    )
    return _HAR_CLIENT


MACRO_PAGE = f"{BASE}/vi-mo/du-lieu"


def _parse_pipe_rows(raw: Any, group_default: str = "") -> list[dict[str, Any]]:
    """Parse GetReportDataByIDs pipe-rows (DataStructure header + Data lines)."""
    if not isinstance(raw, dict):
        return []
    structure = str(raw.get("DataStructure", "")).split("|")
    out: list[dict[str, Any]] = []
    for row in raw.get("Data") or []:
        parts = row.split("|") if isinstance(row, str) else [str(v) for v in row]
        if len(parts) < 16:
            continue
        item = dict(zip(structure, parts, strict=False))
        try:
            value = float(str(item.get("Value", "")).replace(",", "."))
        except ValueError:
            value = None
        out.append(
            {
                "name": item.get("NormName"),
                "group": item.get("GroupName") or group_default,
                "period": item.get("ReportTime"),
                "year": item.get("TermYear"),
                "value": value,
                "unit": item.get("UnitCode"),
                "timeorder": int(item.get("TimeOrder") or 0),
            }
        )
    return out


@guarded("vietstock")
def _browser_post(path: str, payload: dict[str, Any]) -> Any:
    """POST via HAR browser-session, else the JWT login session.

    Shared by macro_report_data (Standard pack works with either — verified
    2026-10-08: JWT session serves real values, HAR seed optional).
    Returns parsed JSON body (raises on HTML/permission).
    """
    try:
        client = har_client()
        token = _env("VIETSTOCK_PAGE_TOKEN") or _har_seed()[1]
        response = client.post(
            f"{BASE}{path}",
            data={**{k: str(v) for k, v in payload.items()},
                  "__RequestVerificationToken": token},
        )
        raw = response.content.decode("utf-8-sig")
        if raw.startswith("<!DOCTYPE") or "<html" in raw[:60].lower():
            raise ProviderAuthMissing(f"vietstock {path} session rejected")
        return json.loads(raw)
    except ProviderAuthMissing:
        pass  # fall through to JWT login session
    client = _session_client()
    token = _form_token(client)
    try:
        response = client.post(
            f"{BASE}{path}",
            data={**{k: str(v) for k, v in payload.items()},
                  "__RequestVerificationToken": token},
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": f"{BASE}/",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock {path} unreachable: {exc}") from exc
    raw = response.content.decode("utf-8-sig")
    if raw.startswith("<!DOCTYPE") or "<html" in raw[:60].lower():
        raise ProviderAuthMissing(f"vietstock {path} session rejected")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ProviderBadData(f"vietstock {path} non-JSON: {response.status_code}") from exc


def macro_report_data(
    term_type_id: int,
    category_id: int,
    sub_term_type_id: str = "",
    from_date: str = "2022-01-01",
    to_date: str | None = None,
) -> dict[str, Any]:
    """Macro series via browser-session replay (Standard pack works — P14).

    Returns {rows, source} with pipe-row parse; raises ProviderAuthMissing
    when the session is rejected (upgrade/permission body).
    """
    import datetime

    from opentrading_mcp.cache import cache_key
    from opentrading_mcp.providers.store import cache_get, cache_set

    to_date = to_date or datetime.date.today().isoformat()
    cache_key_str = cache_key(
        "vs_macro", f"{term_type_id}|{category_id}|{sub_term_type_id}|{from_date}|{to_date}"
    )
    hit = cache_get(cache_key_str)
    if hit is not None:
        cached: dict[str, Any] = json.loads(hit) if isinstance(hit, str) else hit
        return cached
    payload = {
        "termTypeID": str(term_type_id),
        "subTermTypeID": sub_term_type_id or "",
        "fromDate": from_date,
        "toDate": to_date,
        "type": "CATEGORY",
        "listID[]": str(category_id),
    }
    try:
        body = _browser_post("/Macro/GetReportDataByIDs", payload)
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"vietstock macro unreachable: {exc}") from exc
    error = body.get("errorModel") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("ErrorCode"):
        raise ProviderAuthMissing(
            f"vietstock macro {error.get('ErrorCode')}: {error.get('ErrorMessage')}"
        )
    rows = _parse_pipe_rows(body)
    out = {"category": category_id, "term_type": term_type_id, "rows": rows}
    cache_set(cache_key_str, out, 21600)
    return out


@guarded("vietstock")
def planned_targets(symbol: str, years: int = 3) -> dict[str, Any]:
    """Business-plan targets (CTKH: planned revenue/profit by year) — FIXED P15.

    Key shape verified live: YearPeriods[i][YearPeriod] (object-array).
    Returns named rows {name, plan: {year: value}} in VND billions.
    """
    rows_per = _detail_session_post(
        "/data/CTKH_GetListYearPeriods",
        {
            "StockCode": symbol.upper(),
            "UnitedId": -1,
            "AuditedStatusId": -1,
            "Unit": 1000000000,
            "IsNamDuongLich": True,
            "PeriodType": "NAM",
            "SortTimeType": "Time_ASC",
        },
    )
    periods = rows_per.get("data", rows_per) if isinstance(rows_per, dict) else rows_per
    if not isinstance(periods, list) or not periods:
        raise ProviderBadData(f"vietstock CTKH periods malformed for {symbol}")
    years_latest = [
        p.get("YearPeriod") for p in periods if isinstance(p, dict) and p.get("YearPeriod")
    ][-max(int(years), 1) :]
    if not years_latest:
        raise ProviderBadData(f"vietstock CTKH carries no years for {symbol}")
    batch = [{"Index": i, "YearPeriod": y} for i, y in enumerate(years_latest)]
    val_raw = _detail_session_post(
        "/data/GetPlannedTargetsCompanyValue_CTKH_ByYearPeriods",
        {
            "StockCode": symbol.upper(),
            "Unit": 1000000000,
            **_batch_objects("YearPeriods", batch),
        },
    )
    rows = val_raw.get("data", val_raw) if isinstance(val_raw, dict) else val_raw
    if not isinstance(rows, list):
        raise ProviderBadData("vietstock CTKH values malformed")
    norms_raw = _detail_session_post("/data/GetListReportNorm_CTKH", {"stockCode": symbol.upper()})
    norms = norms_raw.get("data", norms_raw) if isinstance(norms_raw, dict) else norms_raw
    names: dict[Any, Any] = {}
    if isinstance(norms, list):
        for n in norms:
            if isinstance(n, dict):
                names[n.get("ReportNormId") or n.get("PlannedTargetID")] = n.get(
                    "ReportNormName"
                ) or n.get("PlannedTargetName")
    out_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        plan = {
            str(years_latest[i]): row.get(f"Value{i + 1}")
            for i in range(len(years_latest))
            if row.get(f"Value{i + 1}") is not None
        }
        if not plan:
            continue
        out_rows.append(
            {
                "name": names.get(row.get("PlannedTargetID")),
                "planned_target_id": row.get("PlannedTargetID"),
                "plan": plan,
            }
        )
    return {
        "symbol": symbol.upper(),
        "unit": "VNDbn",
        "years": years_latest,
        "rows": out_rows,
    }
