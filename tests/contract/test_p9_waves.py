"""P2.1 contract: Elliott/Wyckoff heuristics in technicals.compute (TDD)."""

from __future__ import annotations

import math
from typing import Any


def _candles(prices: list[float], vols: list[float] | None = None) -> list[dict[str, Any]]:
    rows = []
    for i, c in enumerate(prices):
        rows.append(
            {
                "t": f"2026-01-{(i % 28) + 1:02d}",
                "o": c - 0.1,
                "h": c + 0.3,
                "l": c - 0.3,
                "c": c,
                "v": (vols[i] if vols else 1000.0),
            }
        )
    return rows


def _impulse(n: int = 182) -> list[float]:
    # 7 clean legs + short flat tail so the final top registers as a pivot
    legs = [
        (0, 30, 20.0, 30.0),
        (30, 45, 30.0, 26.0),
        (45, 80, 26.0, 40.0),
        (80, 95, 40.0, 35.0),
        (95, 130, 35.0, 52.0),
        (130, 143, 52.0, 46.0),
        (143, 170, 46.0, 60.0),
        (170, 182, 60.0, 59.4),
    ]
    out = []
    for a, b, pa, pb in legs:
        for i in range(a, b):
            f = (i - a) / max(b - a - 1, 1)
            out.append(pa + (pb - pa) * f + 0.3 * math.sin(i / 3))
    return out


def test_elliott_detects_impulse():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_candles(_impulse()))
    el = out["elliott"]
    assert el["pattern"] == "impulse"
    assert len(el["waves"]) == 5
    assert el["confidence"] in ("low", "medium", "high")


def test_elliott_none_on_noise():
    from opentrading_mcp.providers import technicals as tech_p

    prices = [20.0 + 0.5 * math.sin(i * 1.7) for i in range(60)]
    out = tech_p.compute(_candles(prices))
    assert out["elliott"]["pattern"] in ("corrective", "none")


def test_wyckoff_accumulation():
    from opentrading_mcp.providers import technicals as tech_p

    # long range + drying volume + spring below range then recovery
    base = [30.0 + 1.5 * math.sin(2 * math.pi * i / 25) for i in range(100)]
    vols = [3000.0 - 15 * i for i in range(100)]
    base[90] = 27.0  # spring
    base[95] = 30.5  # recovery
    out = tech_p.compute(_candles(base, vols))
    assert out["wyckoff"]["phase"] in ("accumulation", "ranging")
    assert isinstance(out["wyckoff"]["evidence"], list)


def test_wyckoff_keys_always_present():
    from opentrading_mcp.providers import technicals as tech_p

    out = tech_p.compute(_candles([20.0 + 0.1 * i for i in range(40)]))
    assert set(out["wyckoff"]) >= {"phase", "confidence", "evidence"}
    assert set(out["elliott"]) >= {"pattern", "waves", "confidence", "invalidation"}
