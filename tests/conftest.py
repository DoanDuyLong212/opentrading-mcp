"""Test isolation: the process-memory cache tier must not leak between tests.

Each test gets a fresh memory cache so a cached success from one test can
never mask another test's live fetch, auth-missing failure, or source
assertion. (Production Redis is untouched — tests run without REDIS_URL.)
Single-flight and negative-cache registries are cleared for the same reason.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

import pytest


def _install_vnstock_stand_ins() -> list[str]:
    """Inert stand-ins for the private-index wheels (#100).

    vnstock and vnstock_quant install only from vnstocks.com. Without that index
    the suite used to fail at collection (``ModuleNotFoundError: vnstock_quant``),
    although every vnstock-facing test monkeypatches what it uses. When a wheel is
    missing — or ``OT_TEST_VNSTOCK_STUBS=1`` forces it, which CI uses to keep this
    path green — register modules whose entry points raise if anything reaches
    them unpatched. ``tests/contract/test_vnstock_signatures.py`` checks the real
    classes and skips under stand-ins.
    """

    def _unpatched(name: str) -> type:
        class _Unpatched:
            def __init__(self, *args: object, **kwargs: object) -> None:
                raise RuntimeError(
                    f"{name} stand-in: vnstock is not installed and this was not patched"
                )

        _Unpatched.__name__ = name
        return _Unpatched

    forced = os.environ.get("OT_TEST_VNSTOCK_STUBS") == "1"
    installed: list[str] = []
    if forced or importlib.util.find_spec("vnstock") is None:
        mod = types.ModuleType("vnstock")
        for name in ("Market", "Reference", "Fundamental", "Retail"):
            setattr(mod, name, _unpatched(name))
        mod.__stand_in__ = True  # type: ignore[attr-defined]
        sys.modules["vnstock"] = mod
        installed.append("vnstock")
    if forced or importlib.util.find_spec("vnstock_quant") is None:
        quant = types.ModuleType("vnstock_quant")
        fa = types.ModuleType("vnstock_quant.fa")

        def _raise(*_a: object, **_k: object) -> None:
            raise RuntimeError("vnstock_quant stand-in: not installed and not patched")

        fa.Dataset = type(  # type: ignore[attr-defined]
            "Dataset", (), {"load": staticmethod(_raise), "from_frames": staticmethod(_raise)}
        )
        fa.ratios = _raise  # type: ignore[attr-defined]
        quant.fa = fa  # type: ignore[attr-defined]
        quant.__stand_in__ = True  # type: ignore[attr-defined]
        sys.modules["vnstock_quant"] = quant
        sys.modules["vnstock_quant.fa"] = fa
        installed.append("vnstock_quant")
    return installed


VNSTOCK_STAND_INS = _install_vnstock_stand_ins()

from opentrading_mcp.providers.store import _memory  # noqa: E402 — after the stand-ins


@pytest.fixture(autouse=True)
def _isolate_memory_cache():
    _memory.clear()
    try:
        from opentrading_mcp.tools import shared as _shared

        _shared._neg.clear()
        with _shared._inflight_guard:
            _shared._inflight.clear()
    except Exception:
        pass
    _clear_ratio_caches()
    yield
    _memory.clear()
    _clear_ratio_caches()


def _clear_ratio_caches() -> None:
    """In-process ratio caches (6 h TTL) must not carry a stubbed table from one
    test module into another (#91: only test_vn6_ratios cleared its own)."""
    for module, attr in (
        ("opentrading_mcp.providers.vnstock", "_fa_cache"),
        ("opentrading_mcp.providers.vs_ratios", "_cache"),
    ):
        cache = getattr(sys.modules.get(module), attr, None)
        if cache is not None:
            cache.clear()
