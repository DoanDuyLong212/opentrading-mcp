"""#80: the pinned vnstock release candidate expires; source_status must say so."""

from __future__ import annotations

from datetime import date

import pytest

from opentrading_mcp import vnstock_release as rel


@pytest.mark.parametrize(
    ("today", "status", "days_left"),
    [
        (date(2026, 11, 1), "ok", 36),
        (date(2026, 11, 7), "expiring", 30),  # WARN_DAYS boundary warns
        (date(2026, 12, 7), "expiring", 0),  # last usable day
        (date(2026, 12, 8), "expired", -1),
    ],
)
def test_rc4_expiry_windows(today, status, days_left):
    out = rel.release_status(today=today, version="6.0.0rc4")
    assert out["status"] == status
    assert out["days_left"] == days_left
    assert out["expires"] == "2026-12-07"
    assert ("warning" in out) is (status != "ok")


def test_rc5_expiry_from_vnstock_doctor():
    out = rel.release_status(today=date(2026, 11, 9), version="6.0.0rc5")
    assert out["expires"] == "2026-12-09"
    assert out["days_left"] == 30
    assert out["status"] == "expiring"  # rc5 ships inside the 30-day warning window
    assert rel.release_status(today=date(2026, 12, 10), version="6.0.0rc5")["status"] == "expired"


def test_unknown_release_candidate_is_flagged_not_healthy():
    out = rel.release_status(today=date(2026, 11, 9), version="6.0.0rc9")
    assert out["status"] == "unknown_expiry"
    assert "pre-release" in out["warning"]


def test_final_release_without_expiry_is_ok():
    out = rel.release_status(today=date(2026, 11, 9), version="6.0.0")
    assert out == {"version": "6.0.0", "status": "ok"}


def test_missing_package_is_reported(monkeypatch):
    monkeypatch.setattr(rel, "installed_version", lambda: None)
    assert rel.release_status()["status"] == "not_installed"


def test_the_locked_vnstock_version_has_a_recorded_expiry():
    """Bumping vnstock in uv.lock without recording the new release's expiry
    (or confirming it is final) must fail here, not on the expiry date."""
    import pathlib
    import re

    lock = (pathlib.Path(__file__).resolve().parents[1] / "uv.lock").read_text(encoding="utf-8")
    match = re.search(r'name = "vnstock"\nversion = "([^"]+)"', lock)
    assert match, "vnstock not found in uv.lock"
    version = match.group(1)
    if "rc" in version:
        assert version in rel.RELEASE_EXPIRY, f"record the expiry of vnstock {version}"


async def test_source_status_carries_the_release_warning(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import market

    monkeypatch.setattr(
        market, "release_report",
        lambda: rel.release_report(today=date(2026, 11, 20), live=None)
        | rel.release_status(today=date(2026, 11, 20), version="6.0.0rc4"),
    )
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [{"c": 1.0}])
    server = create_server("all")
    register_preset(server, "all")
    env = await server._tool_manager.get_tool("source_status").fn()
    release = env["data"]["upstreams"]["vnstock_release"]
    assert release["status"] == "expiring" and release["days_left"] == 17
    assert any("expires on 2026-12-07" in w for w in env["warnings"])


# --- live verdict (vnstock.status()["release"]) -------------------------------------

LIVE_OK = {
    "allowed": True,
    "build_date": "2026-11-10",
    "expires_at": "2027-11-10T05:34:30Z",
    "version": "6.0.0",
}


def test_live_verdict_gives_the_final_release_its_date():
    out = rel.release_report(today=date(2026, 11, 13), live=LIVE_OK)
    assert out["source"] == "live"
    assert (out["status"], out["expires"], out["days_left"]) == ("ok", "2027-11-10", 362)
    assert "warning" not in out


def test_live_verdict_warns_thirty_days_ahead():
    out = rel.release_report(today=date(2027, 10, 11), live=LIVE_OK)
    assert (out["status"], out["days_left"]) == ("expiring", 30)
    assert "expires on 2027-11-10" in out["warning"]
    assert rel.release_report(today=date(2027, 11, 11), live=LIVE_OK)["status"] == "expired"


def test_switched_off_release_is_disabled_whatever_its_date():
    """6.0.0rc5 on 13/11/2026: refused, while its date still said 09/12."""
    refused = {**LIVE_OK, "allowed": False, "version": "6.0.0rc5", "expires_at": "2026-12-09"}
    out = rel.release_report(today=date(2026, 11, 13), live=refused)
    assert out["status"] == "disabled"
    assert "switched off by the vendor" in out["warning"]


def test_unreadable_live_verdict_falls_back_to_the_table(monkeypatch):
    monkeypatch.setattr(rel, "installed_version", lambda: "6.0.0rc5")
    out = rel.release_report(today=date(2026, 11, 13), live=None)
    assert out["source"] == "table"
    assert out["expires"] == "2026-12-09"


def test_live_lookup_is_cached_and_failures_retry_sooner(monkeypatch):
    results = [None, None, LIVE_OK]
    calls: list[int] = []

    def read() -> dict | None:
        calls.append(1)
        return results[len(calls) - 1]

    monkeypatch.setattr(rel, "_read_live_release", read)
    monkeypatch.setattr(rel, "_live_cache", None)
    assert rel.live_release() is None
    assert rel.live_release() is None  # the failure is cached for _LIVE_FAIL_TTL_S
    assert len(calls) == 1
    monkeypatch.setattr(rel, "_LIVE_FAIL_TTL_S", 0.0)
    monkeypatch.setattr(rel, "_live_cache", None)
    assert rel.live_release() is None  # failure again, expires at once
    assert rel.live_release() == LIVE_OK
    assert rel.live_release() == LIVE_OK  # success cached for _LIVE_TTL_S
    assert len(calls) == 3


def test_live_reader_never_raises(monkeypatch):
    import sys
    import types

    def boom() -> None:
        raise RuntimeError("network down")

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(status=boom))
    assert rel._read_live_release() is None


async def test_deep_readyz_reports_a_switched_off_release(monkeypatch):
    from opentrading_mcp import health

    refused = {**LIVE_OK, "allowed": False, "version": "6.0.0rc5"}
    monkeypatch.setattr(rel, "live_release", lambda: refused)
    probes = {p["name"]: p for p in await health.deep_probes()}
    vn = probes["vnstock"]
    assert vn["ok"] is False and vn["required"] is False
    assert "6.0.0rc5 disabled (live)" in vn["detail"]


async def test_deep_readyz_vnstock_ok_needs_a_real_candle(monkeypatch):
    from opentrading_mcp import health
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(rel, "live_release", lambda: LIVE_OK)
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [{"c": 1.0}])
    probes = {p["name"]: p for p in await health.deep_probes()}
    assert probes["vnstock"]["ok"] is True
    assert "until 2027-11-10" in probes["vnstock"]["detail"]


# --- scripts/vnstock_canary.py -------------------------------------------------------


def _canary():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "vnstock_canary.py"
    spec = importlib.util.spec_from_file_location("vnstock_canary", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("release", "code"),
    [
        ({**LIVE_OK}, 0),
        ({**LIVE_OK, "allowed": False}, 1),
        ({**LIVE_OK, "expires_at": "2026-11-20T00:00:00Z"}, 1),  # inside 30 days
    ],
)
def test_canary_exit_code_follows_the_vendor_verdict(monkeypatch, release, code):
    from opentrading_mcp.providers import vnstock as vn_p

    canary = _canary()
    monkeypatch.setattr(rel, "live_release", lambda: release)
    monkeypatch.setattr(vn_p, "ensure_api_key", lambda: "keyed")
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [{"c": 1.0}] * 5)
    got, lines = canary.run()
    assert got == code
    assert any("candle VCB: ok (5 rows)" in line for line in lines)


def test_canary_fails_on_a_refused_candle_but_not_on_a_network_error(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    canary = _canary()
    monkeypatch.setattr(rel, "live_release", lambda: LIVE_OK)
    monkeypatch.setattr(vn_p, "ensure_api_key", lambda: "keyed")

    def refused(*a, **k):
        raise ProviderUnavailable("refused", reason="vendor_disabled")

    def offline(*a, **k):
        raise ProviderUnavailable("ssi unreachable", reason="upstream_down")

    monkeypatch.setattr(vn_p, "quote_history", refused)
    assert canary.run()[0] == 1
    monkeypatch.setattr(vn_p, "quote_history", offline)
    code, lines = canary.run()
    assert code == 0
    assert any("FAILED, reason upstream_down" in line for line in lines)
