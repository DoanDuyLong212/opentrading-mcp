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
        market, "release_status",
        lambda: rel.release_status(today=date(2026, 11, 20), version="6.0.0rc4"),
    )
    monkeypatch.setattr(vn_p, "quote_history", lambda *a, **k: [{"c": 1.0}])
    server = create_server("all")
    register_preset(server, "all")
    env = await server._tool_manager.get_tool("source_status").fn()
    release = env["data"]["upstreams"]["vnstock_release"]
    assert release["status"] == "expiring" and release["days_left"] == 17
    assert any("expires on 2026-12-07" in w for w in env["warnings"])
