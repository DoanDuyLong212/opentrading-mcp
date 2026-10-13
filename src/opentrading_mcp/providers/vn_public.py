"""VN public-page scrapers: HNX auctions, Vietstock analyst titles, NSO releases, SBV rates.

All anonymous, static HTML (bs4 is a hard dep). HNX chain needs a TLS
fallback (verify=False) with an explicit warning.
"""

from __future__ import annotations

import re
from typing import Any

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

_BROWSER_UA = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"

HNX_CALENDAR_URL = "https://www.hnx.vn/dau-gia/lich-dau-gia.html"
HNX_NEWS_URL = "https://www.hnx.vn/dau-gia/dau-gia-tin-cong-bo.html"
ANALYST_URL = "https://finance.vietstock.vn/bao-cao-phan-tich/phan-tich-doanh-nghiep"
NSO_CALENDAR_URL = "https://www.nso.gov.vn/lich-pho-bien-thong-tin/"
NSO_CPI_URL = "https://www.nso.gov.vn/cpi-vi/"
SBV_RATES_PATH = "/lãi-suất1"
SBV_BASE = "https://sbv.gov.vn"

_DATE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")


def _fetch(url: str, timeout: int = 20) -> tuple[str, bool]:
    """Return (html, tls_unverified). Falls back to verify=False on SSLError."""
    try:
        import httpx
    except ImportError as exc:
        raise ProviderUnavailable("httpx not installed") from exc
    try:
        resp = httpx.get(
            url, headers={"User-Agent": _BROWSER_UA}, timeout=timeout, follow_redirects=True
        )
        resp.raise_for_status()
        return resp.text, False
    except Exception as exc:
        if "SSL" not in type(exc).__name__ and "SSL" not in str(exc):
            raise ProviderUnavailable(f"public page fetch failed: {url}: {exc}") from exc
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": _BROWSER_UA},
            timeout=timeout,
            verify=False,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text, True
    except Exception as exc:
        raise ProviderUnavailable(f"public page fetch failed: {url}: {exc}") from exc


def _soup(html: str) -> Any:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ProviderUnavailable("beautifulsoup4 not installed") from exc
    return BeautifulSoup(html, "html.parser")


def _table_rows(table: Any) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


BTMC_URL = "https://api.btmc.vn/api/BTMCAPI/getpricebtmc?key=3kd8ub1llcg9t45hnoh8hmn7t5kc2v"


def _parse_btmc(payload: Any) -> list[dict[str, Any]]:
    """Parse BTMC DataList rows (same shape as vnstock lib, minus the hang)."""
    try:
        items = payload["DataList"]["Data"]
    except (KeyError, TypeError) as exc:
        raise ProviderBadData("BTMC payload malformed") from exc
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = str(item.get("@row", ""))
        out.append(
            {
                "name": item.get(f"@n_{row}", ""),
                "karat": item.get(f"@k_{row}", ""),
                "gold_content": item.get(f"@h_{row}", ""),
                "buy_price": item.get(f"@pb_{row}", ""),
                "sell_price": item.get(f"@ps_{row}", ""),
                "world_price": item.get(f"@pt_{row}", ""),
                "time": item.get(f"@d_{row}", ""),
            }
        )
    return out


@guarded("vn_public")
def btmc_gold() -> list[dict[str, Any]]:
    """BTMC retail gold over HTTPS with timeout (P11).

    The vnstock lib hits the http:// URL with no timeout and hangs when the
    host stalls; https answers. Same default key the lib uses.
    """
    try:
        import httpx
    except ImportError as exc:
        raise ProviderUnavailable("httpx not installed") from exc
    try:
        resp = httpx.get(BTMC_URL, timeout=15.0)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        raise ProviderUnavailable(f"BTMC fetch failed: {exc}") from exc
    return _parse_btmc(payload)


@guarded("vn_public")
def hnx_auctions() -> dict[str, Any]:
    """HNX auction calendar table; falls back to the announcement list."""
    html, tls_off = _fetch(HNX_CALENDAR_URL)
    tables = _soup(html).find_all("table")
    auctions: list[dict[str, Any]] = []
    for table in tables:
        rows = _table_rows(table)
        if not rows or "phát hành" not in " ".join(rows[0]).lower():
            continue
        for cells in rows[1:]:
            if len(cells) < 6:
                continue
            auctions.append(
                {
                    "issuer": cells[1],
                    "security_type": cells[2],
                    "charter_capital": cells[3],
                    "offer_volume": cells[4],
                    "auction_date": cells[5],
                }
            )
        break
    announcements: list[dict[str, Any]] = []
    if not auctions:
        news_html, news_tls = _fetch(HNX_NEWS_URL)
        tls_off = tls_off or news_tls
        for table in _soup(news_html).find_all("table"):
            rows = _table_rows(table)
            if not rows or "tiêu đề" not in " ".join(rows[0]).lower():
                continue
            for cells in rows[1:11]:
                if len(cells) < 3:
                    continue
                announcements.append({"posted": cells[1], "title": cells[2]})
            break
    note = "no upcoming auctions" if not auctions else None
    out: dict[str, Any] = {"auctions": auctions, "announcements": announcements}
    if note:
        out["note"] = note
    if tls_off:
        out["tls"] = "unverified (HNX chain)"
    return out


_RATING_RE = re.compile(
    r"\b(MUA MẠNH|BÁN MẠNH|TĂNG TỶ TRỌNG|GIẢM TỶ TRỌNG|NẮM GIỮ|KHẢ QUAN|TRUNG LẬP|"
    r"KÉM KHẢ QUAN|THEO DÕI|MUA|BÁN)\b"
)
_TARGET_RE = re.compile(r"giá mục tiêu\s*([\d\.,]+)", re.IGNORECASE)


def _norm_macro(text: str) -> str:
    """Uppercase ASCII fold for keyword matching (stdlib only)."""
    import unicodedata

    folded = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    return stripped.upper().replace("Đ", "D")


_MACRO_KEYWORDS = (
    "GDP",
    "CPI",
    "LAM PHAT",
    "LAI SUAT",
    "TY GIA",
    "VI MO",
    "KINH TE",
    "FED",
    "FOMC",
    "CHINH SACH TIEN TE",
    "TRIEN VONG THI TRUONG",
    "NHAN DINH THI TRUONG",
    "XUAT KHAU",
    "NHAP KHAU",
    "DAU TU CONG",
    "NGAN SACH",
    "NO CONG",
    "USD/",
    "DXY",
)


def is_macro_title(title: str) -> str | None:
    """Return the matched macro topic, or None. Pure function (testable)."""
    norm = _norm_macro(title)
    for kw in _MACRO_KEYWORDS:
        if kw in norm:
            return kw
    return None


def _parse_consensus_title(title: str) -> dict[str, Any]:
    """Extract ticker/rating/target. Ticker prefix required (rejects 'bán lẻ' noise)."""
    symbol = None
    prefix = re.match(r"\s*([A-Z0-9]{3,6})\s*:", title.upper())
    if prefix:
        symbol = prefix.group(1)
    else:
        return {"symbol": None, "rating": None, "target": None}
    rating = None
    match = _RATING_RE.search(title.upper())
    if match:
        rating = match.group(1)
    target = None
    tmatch = _TARGET_RE.search(title)
    if tmatch:
        try:
            target = float(tmatch.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            target = None
    return {"symbol": symbol, "rating": rating, "target": target}


@guarded("vn_public")
def analyst_reports(limit: int = 30, kind: str = "equity") -> list[dict[str, Any]]:
    """Analyst report titles with rating/target parsed (Vietstock listing page).

    kind='equity': ticker-prefixed titles only (current behavior).
    kind='macro': titles WITHOUT ticker prefix that match macro keywords
    (GDP/CPI/rates/FX/Fed...); rating/target may be absent, macro_topic set.
    Only the latest listing page exists: ?page=N is ignored server-side.
    """
    html, tls_off = _fetch(ANALYST_URL)
    soup = _soup(html)
    out: list[dict[str, Any]] = []
    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        if not title or len(title) < 10:
            continue
        href = str(anchor["href"])
        parsed = _parse_consensus_title(title)
        if kind == "macro":
            # article links only: skip /vi-mo/ nav, courses, symbol pages
            if "bao-cao-phan-tich" not in href:
                continue
            if parsed["symbol"]:
                continue  # equity reports belong to the equity feed
            topic = is_macro_title(title)
            if not topic:
                continue
            parsed = {"symbol": None, "rating": parsed["rating"], "target": parsed["target"]}
        elif not parsed["symbol"] or not parsed["rating"]:
            continue
        url = href if href.startswith("http") else f"https://finance.vietstock.vn{href}"
        parent_text = anchor.parent.get_text(" ", strip=True) if anchor.parent else ""
        dates = _DATE_RE.findall(parent_text)
        extra: dict[str, Any] = {}
        if kind == "macro":
            # Vietstock exposes no dated CTCK-macro feed; listing carries section
            # pointers (/vi-mo/...) plus dated articles when present.
            dated = bool(dates)
            extra = {"macro_topic": topic, "entry_kind": "report" if dated else "section"}
        source = None
        for token in re.split("[\u2014\u2013\\-|]", parent_text):
            token = token.strip()
            if token and not _DATE_RE.search(token) and len(token) <= 12:
                source = token
                break
        out.append(
            {
                "title": title,
                "source": source,
                "date": dates[0] if dates else None,
                "url": url,
                **parsed,
            }
            | extra
        )
        if len(out) >= max(int(limit), 1):
            break
    if tls_off:
        out.append({"title": "", "tls": "unverified"})
    return out


@guarded("vn_public")
def nso_releases() -> list[dict[str, Any]]:
    """NSO release listings with reference period and next-release dates."""
    out: list[dict[str, Any]] = []

    def _clean_date(text: str) -> str | None:
        found = _DATE_RE.findall(text or "")
        return found[0] if found else None

    for url, indicator in ((NSO_CPI_URL, "CPI"), (NSO_CALENDAR_URL, "schedule")):
        try:
            html, _ = _fetch(url)
        except ProviderUnavailable:
            continue
        soup = _soup(html)
        for section in soup.find_all("section", class_="item", limit=30):
            title_tag = section.find(["h2", "h3", "h4"])
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            if not title:
                continue
            link = section.find("a", href=True)
            posted = section.find(class_="archive-issue-date")
            ref = section.find(class_="archive-reference-period")
            ref_text = ref.get_text(" ", strip=True) if ref else ""
            reference = ref_text.split(":")[-1].strip() or None
            nxt_match = re.search(
                r"(lần công bố sắp tới|công bố tới|sắp tới)[^:]*:\s*(\d{1,2}/\d{1,2}/\d{4})",
                section.get_text(" ", strip=True),
                re.IGNORECASE,
            )
            out.append(
                {
                    "indicator": indicator,
                    "title": title[:160],
                    "url": str(link["href"]) if link else None,
                    "reference": reference,
                    "published": _clean_date(posted.get_text() if posted else ""),
                    "next": nxt_match.group(2) if nxt_match else None,
                }
            )
    return out


@guarded("vn_public")
def sbv_rates() -> dict[str, Any]:
    """SBV policy + interbank rate tables (static HTML, cached upstream rarely changes)."""
    from urllib.parse import quote

    html, tls_off = _fetch(f"{SBV_BASE}{quote(SBV_RATES_PATH)}")
    soup = _soup(html)
    policy: list[dict[str, Any]] = []
    interbank: list[dict[str, Any]] = []
    as_of = None
    for table in soup.find_all("table"):
        for cells in _table_rows(table):
            if len(cells) < 2:
                continue
            label, value = cells[0], cells[1]
            if "%" not in value and "%" not in " ".join(cells):
                dates = _DATE_RE.findall(" ".join(cells))
                if dates and as_of is None:
                    as_of = dates[0]
                continue
            if not re.search(r"\d", value):
                continue
            entry = {"name": label, "value": value}
            low = label.lower()
            policy_keys = ("tái chiết khấu", "tái cấp vốn", "omo", "tín phiếu", "dự trữ")
            if any(k in low for k in policy_keys):
                policy.append(entry)
            else:
                interbank.append(entry)
    out: dict[str, Any] = {"policy": policy, "interbank": interbank, "as_of": as_of}
    if tls_off:
        out["tls"] = "unverified"
    if not policy and not interbank:
        raise ProviderBadData("SBV rates page shape changed")
    return out
