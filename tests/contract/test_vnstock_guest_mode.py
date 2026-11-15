"""vnstock 6 stays in guest mode: the account key never reaches the vnstock core.

A login registers the machine as one of the account's devices; the Render free
instance has no persistent VNSTOCK_HOME, so every cold start could cost a device.
"""

from __future__ import annotations

import opentrading_mcp


def test_account_key_is_dropped(monkeypatch):
    monkeypatch.setenv("VNSTOCK_API_KEY", "vnstock_testkey123")
    monkeypatch.delenv("VNSTOCK_ALLOW_LOGIN", raising=False)
    opentrading_mcp._force_vnstock_guest()
    import os

    assert "VNSTOCK_API_KEY" not in os.environ


def test_explicit_opt_in_keeps_the_key(monkeypatch):
    monkeypatch.setenv("VNSTOCK_API_KEY", "vnstock_testkey123")
    monkeypatch.setenv("VNSTOCK_ALLOW_LOGIN", "1")
    opentrading_mcp._force_vnstock_guest()
    import os

    assert os.environ["VNSTOCK_API_KEY"] == "vnstock_testkey123"


def test_pins_are_final_releases():
    """6.0.0rc5 was switched off remotely on 11/11/2026: never resolve an rc again."""
    import pathlib
    import re

    text = (pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml").read_text("utf-8")
    pins = re.findall(r'"(vnstock(?:-oapi|-quant)?)>=([^,"]+)', text)
    assert {name for name, _ in pins} == {"vnstock", "vnstock-oapi", "vnstock-quant"}
    for name, floor in pins:
        assert "rc" not in floor and "a" not in floor and "b" not in floor, (name, floor)
