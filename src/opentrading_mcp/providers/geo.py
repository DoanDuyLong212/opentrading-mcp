"""Geo provider: military ADS-B flights + conflict-zone proximity (port of 8010 ORACLE).

Sources: adsb.lol /v2/mil (public, no key) + GDELT. Conflict zones and the
haversine/nearest-zone logic are adapted from
~/Trading_Agents/ai_training/signal_viewer/oracle.py (2026-10).
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

import httpx

from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.providers.pool import shared_client

MIL_CACHE_TTL = 60.0
_MIL_CACHE: dict[str, Any] = {"ts": 0.0, "data": []}

CONFLICT_ZONES: list[dict[str, Any]] = [
    {"id": "ukraine", "label": "Ukraine War", "lat": 48.5, "lng": 31.2},
    {"id": "gaza", "label": "Gaza Conflict", "lat": 31.35, "lng": 34.35},
    {"id": "lebanon", "label": "Lebanon Border", "lat": 33.377, "lng": 35.483},
    {"id": "sudan", "label": "Sudan Civil War", "lat": 15.0, "lng": 30.0},
    {"id": "myanmar", "label": "Myanmar Conflict", "lat": 19.5, "lng": 96.5},
    {"id": "yemen", "label": "Yemen War", "lat": 15.5, "lng": 48.0},
    {"id": "syria", "label": "Syria", "lat": 35.0, "lng": 38.5},
    {"id": "drc", "label": "DRC Eastern", "lat": -1.0, "lng": 28.5},
    {"id": "red-sea", "label": "Red Sea Threat", "lat": 16.0, "lng": 40.0},
    {"id": "taiwan-strait", "label": "Taiwan Strait", "lat": 24.0, "lng": 119.5},
    {"id": "korean-dmz", "label": "Korean DMZ", "lat": 38.3, "lng": 127.0},
    {"id": "sahel", "label": "Sahel Instability", "lat": 14.0, "lng": 5.0},
    {"id": "somalia", "label": "Somalia", "lat": 5.0, "lng": 46.0},
    {"id": "iraq", "label": "Iraq Instability", "lat": 33.3, "lng": 44.4},
    {"id": "ethiopia", "label": "Ethiopia", "lat": 9.0, "lng": 38.7},
]

_ZONE_PROXIMITY_KM = 400

_ICAO_OPS = {
    "ae": "US", "af": "US", "a0": "US", "a1": "US", "a2": "US", "a3": "US", "a4": "US",
    "a5": "US", "a6": "US", "a7": "US", "a8": "US", "a9": "US", "aa": "US", "ab": "US",
    "ac": "US", "ad": "US", "71": "Australia", "78": "Germany", "7c": "France",
    "44": "UK", "43": "UK", "3f": "Japan", "84": "Japan", "c0": "Canada", "c1": "Canada",
}

_MIL_TYPE_MAP = {
    "J10": "fighter", "J11": "fighter", "J15": "fighter", "J16": "fighter", "J20": "fighter",
    "SU27": "fighter", "SU30": "fighter", "SU35": "fighter", "SU57": "fighter",
    "MIG29": "fighter", "MIG31": "fighter",
    "TU95": "bomber", "TU160": "bomber", "TU22": "bomber",
    "C17": "transport", "C5": "transport", "C130": "transport", "C30J": "transport",
    "A400": "transport", "IL76": "transport", "AN124": "transport", "Y20": "transport",
    "B737": "transport", "B767": "tanker", "B707": "tanker",
    "K35": "tanker", "K46": "tanker", "A33": "tanker", "A332": "tanker",
    "P8": "recon", "E3": "recon", "E8": "recon", "U2": "recon", "E6": "recon",
    "RC35": "recon", "E767": "recon",
    "H60": "heli", "H64": "heli", "AH64": "heli", "UH60": "heli", "CH47": "heli",
    "V22": "transport", "MV22": "transport",
}

_UAV_KEYWORDS = ("RQ-", "MQ-", "REAPER", "GLOBALHAWK", "TRITON", "PREDATOR", "BAYRAKTAR", "HERON")


def classify_mil_type(model: str, callsign: str) -> str:
    m = model.upper().replace("-", "").replace(" ", "")
    cs = callsign.upper().strip()
    for kw in _UAV_KEYWORDS:
        if kw in m or kw in cs:
            return "uav"
    for k, v in _MIL_TYPE_MAP.items():
        if k in m:
            return v
    return "mil-other"


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_zone(lat: float, lng: float) -> tuple[str, str, float]:
    best_id, best_label, best_km = "", "", 1e9
    for zn in CONFLICT_ZONES:
        km = haversine_km(lat, lng, zn["lat"], zn["lng"])
        if km < best_km:
            best_id, best_label, best_km = zn["id"], zn["label"], km
    return best_id, best_label, best_km


def military_flights(timeout: float = 15.0) -> list[dict[str, Any]]:
    """ADS-B military flights from adsb.lol /v2/mil (public, no key), cached 60s.

    Rows: {hex, callsign, model, type, operator_country, lat, lng, alt_m, gs_kt,
    nearest_zone, zone_km}.
    """
    now = time.time()
    if now - _MIL_CACHE["ts"] < MIL_CACHE_TTL and _MIL_CACHE["data"]:
        return _MIL_CACHE["data"]
    try:
        resp = shared_client().get(
            "https://api.adsb.lol/v2/mil",
            headers={"User-Agent": "opentrading-mcp/1.0"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"adsb.lol unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise ProviderUnavailable(f"adsb.lol HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderUnavailable("adsb.lol bad json") from exc
    out: list[dict[str, Any]] = []
    for ac in data.get("ac", []) or []:
        if not isinstance(ac, dict):
            continue
        lat, lng = ac.get("lat"), ac.get("lon")
        if lat is None or lng is None:
            continue
        model = str(ac.get("t", "UNKNOWN")).upper()
        if model == "TWR":
            continue
        callsign = str(ac.get("flight", "MIL")).strip()
        hex_id = str(ac.get("hex", "")).lower()[:2]
        alt_raw = ac.get("alt_baro")
        alt = int(alt_raw * 0.3048) if isinstance(alt_raw, (int, float)) else 0
        zid, zlabel, zkm = nearest_zone(float(lat), float(lng))
        out.append(
            {
                "hex": str(ac.get("hex", "")),
                "callsign": callsign,
                "model": model,
                "type": classify_mil_type(model, callsign),
                "operator_country": _ICAO_OPS.get(hex_id, "Unknown"),
                "lat": float(lat),
                "lng": float(lng),
                "alt_m": alt,
                "gs_kt": ac.get("gs"),
                "nearest_zone": zid,
                "zone_label": zlabel,
                "zone_km": round(zkm, 1),
            }
        )
    _MIL_CACHE["ts"] = now
    _MIL_CACHE["data"] = out
    return out


# Signal-loss diff (in-process; MCP is stateless so this tracks only this process's polls)
_SEEN: dict[str, float] = {}


def track_signal_loss(flights: list[dict[str, Any]]) -> dict[str, Any]:
    """Diff current flights near zones vs the last poll.

    Flags: lost_near_zone (was near a zone, now gone), reacquired (was lost, back).
    """
    now_ms = int(time.time() * 1000)
    current: dict[str, float] = {}
    for f in flights or []:
        if f.get("zone_km", 1e9) <= _ZONE_PROXIMITY_KM:
            current[str(f.get("hex"))] = now_ms
    lost, reacquired = [], []
    for hexid, last_ms in _SEEN.items():
        if hexid not in current:
            lost.append({"hex": hexid, "last_seen_ms": last_ms})
    for hexid in current:
        if hexid in _SEEN and now_ms - _SEEN[hexid] > 10 * 60_000:
            reacquired.append({"hex": hexid})
    _SEEN.clear()
    _SEEN.update(current)
    return {
        "tracked": len(current),
        "lost_near_zone": lost[:20],
        "reacquired": reacquired[:20],
        "zone_radius_km": _ZONE_PROXIMITY_KM,
        "note": "stateless in-process diff — first poll always 0 lost",
    }


def political_filter(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only politically relevant articles (drops sports/noise)."""
    keys = (
        "conflict", "war", "sanction", "military", "election", "protest", "politic",
        "strike", "coup", "ceasefire", "nato", "diplomat", "trade war", "tariff",
        "missile", "drone", "border", "government", "minister", "president",
    )
    kept = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        text = f"{a.get('title', '')} {a.get('url', '')}".lower()
        if any(k in text for k in keys):
            kept.append(a)
    return kept


def aggregate(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """{count, by_day, top_sources, date_range} over an article list."""
    by_day: dict[str, int] = {}
    by_source: dict[str, int] = {}
    dates: list[str] = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        day = str(a.get("date", ""))[:10]
        if day:
            by_day[day] = by_day.get(day, 0) + 1
            dates.append(day)
        url = str(a.get("url", ""))
        try:
            host = url.split("/")[2] if url.count("/") >= 2 else "unknown"
        except Exception:
            host = "unknown"
        by_source[host] = by_source.get(host, 0) + 1
    return {
        "count": len(articles),
        "by_day": dict(sorted(by_day.items(), reverse=True)[:14]),
        "top_sources": sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:8],
        "date_range": [min(dates), max(dates)] if dates else None,
    }


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)
