"""Synthesizes a plausible biomarker reading when no real sensor value was
supplied — shared by routers/readings.py's add_reading (the "Take New
Sample" / no-body POST path, and any caller that omits ph/creatinine/urea/
temperature) and core/demo_account.py's admin-account auto-seeding, so both
stay byte-for-byte the same generator instead of two copies drifting apart.

Extracted 2026-08-23 while wiring up the admin/demo account — folded in a
real bug fix at the same time: routers/readings.py used to compute
`temperature` once up front (respecting config.SENSOR_STABILIZATION_ENABLED)
but then silently discarded it in the no-raw-channels branch, recomputing a
second, different temperature that ignored the stabilization setting
entirely. `synthesize()` below computes it exactly once.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from .. import config
from . import reference_data


def _round(v: float, dp: int) -> float:
    f = 10**dp
    return round(v * f) / f


def _jitter(base: float, amp: float, dp: int) -> float:
    return _round(base + (random.random() - 0.5) * amp, dp)


def _stabilize(base: float, amp: float, lo: float, hi: float, dp: int) -> float:
    return _round(min(hi, max(lo, base + (random.random() - 0.5) * amp)), dp)


def synthesize_mixed_range() -> dict[str, float]:
    """Exactly 2 of the 4 biomarkers land inside their clinical reference
    range, the other 2 land outside it — which 2 is randomized every call.
    Backs the admin/demo account's on-demand "Take New Sample" (2026-08-26,
    Hassan's call): unlike synthesize() above (near-normal-only jitter),
    this deliberately produces a mixed-signal reading so a demo can exercise
    the real screening/flagging pipeline on request, not just show a
    healthy-looking dashboard."""
    keys = list(reference_data.REFERENCE.keys())
    random.shuffle(keys)
    in_range_keys = set(keys[:2])
    values: dict[str, float] = {}
    for key, spec in reference_data.REFERENCE.items():
        lo, hi = spec["range"]
        span = hi - lo
        if key in in_range_keys:
            value = random.uniform(lo + span * 0.2, hi - span * 0.2)
        else:
            overshoot = span * random.uniform(0.15, 0.45)
            value = (lo - overshoot) if random.random() < 0.5 else (hi + overshoot)
        values[key] = _round(value, spec["dp"])
    return values


def synthesize(last: Optional[dict[str, Any]] = None) -> dict[str, float]:
    """A plausible reading near clinically-normal baselines, or drifted off
    `last` if given. Temperature respects config.SENSOR_STABILIZATION_ENABLED
    for consistency with the real-sensor code path in routers/readings.py,
    even though no real hardware is involved here."""
    if config.SENSOR_STABILIZATION_ENABLED:
        temp_lo, temp_hi = reference_data.REFERENCE["temperature"]["range"]
        temperature = _stabilize(last["temperature"] if last else (temp_lo + temp_hi) / 2, 0.2, temp_lo, temp_hi, 1)
    else:
        temperature = _jitter(last["temperature"] if last else 36.9, 0.6, 1)
    return {
        "ph": _jitter(last["ph"] if last else 6.8, 0.6, 2),
        "creatinine": _jitter(last["creatinine"] if last else 1.0, 0.4, 2),
        "urea": _jitter(last["urea"] if last else 22, 8, 1),
        "temperature": temperature,
    }
