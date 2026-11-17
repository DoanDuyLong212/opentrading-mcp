"""#142: an expired Vietstock JWT with credentials is "will re-login", not down.

The client re-logs-in with email/password whenever the cookie JWT is expired,
so the health probe must not report an outage for a state that self-heals on
the next paid call. Without credentials an expired JWT really is down.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from opentrading_mcp import health
from opentrading_mcp.providers import vietstock as vs_p


def _jwt(exp: float) -> str:
    def seg(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"


def _env_with(monkeypatch, **values: str) -> None:
    monkeypatch.setattr(vs_p, "_env", lambda name: values.get(name))


def test_expired_jwt_with_credentials_reports_will_relogin(monkeypatch):
    _env_with(
        monkeypatch,
        VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() - 3600),
        VIETSTOCK_EMAIL="a@b.c",
        VIETSTOCK_PASSWORD="pw",
    )
    status = vs_p.auth_status()
    assert status["authenticated"] is True
    assert "re-login" in status["reason"]
    assert status["relogin_available"] is True


def test_expired_jwt_without_credentials_stays_down(monkeypatch):
    _env_with(monkeypatch, VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() - 3600))
    status = vs_p.auth_status()
    assert status["authenticated"] is False
    assert status["reason"] == "jwt expired"
    assert status["relogin_available"] is False


def test_jwt_expiring_within_7_days_warns(monkeypatch):
    _env_with(
        monkeypatch,
        VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() + 2 * 86400 + 3600),
        VIETSTOCK_EMAIL="a@b.c",
        VIETSTOCK_PASSWORD="pw",
    )
    status = vs_p.auth_status()
    assert status["authenticated"] is True
    assert status["expiring_soon"] is True
    assert status["expires_in_days"] == 2


def test_jwt_expiring_later_does_not_warn(monkeypatch):
    _env_with(
        monkeypatch,
        VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() + 30 * 86400),
        VIETSTOCK_EMAIL="a@b.c",
        VIETSTOCK_PASSWORD="pw",
    )
    status = vs_p.auth_status()
    assert status["authenticated"] is True
    assert not status.get("expiring_soon")


async def test_deep_probe_treats_expired_with_credentials_as_available(monkeypatch):
    _env_with(
        monkeypatch,
        VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() - 3600),
        VIETSTOCK_EMAIL="a@b.c",
        VIETSTOCK_PASSWORD="pw",
    )
    probe = health.probe_vietstock()
    assert probe["ok"] is True
    assert "re-login" in probe["detail"]


async def test_deep_probe_warns_before_expiry(monkeypatch):
    _env_with(monkeypatch, VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() + 2 * 86400))
    probe = health.probe_vietstock()
    assert probe["ok"] is True
    assert "expires" in probe["detail"].lower()


async def test_deep_probe_fails_when_expired_without_credentials(monkeypatch):
    _env_with(monkeypatch, VIETSTOCK_COOKIE_LOGIN=_jwt(time.time() - 3600))
    probe = health.probe_vietstock()
    assert probe["ok"] is False
