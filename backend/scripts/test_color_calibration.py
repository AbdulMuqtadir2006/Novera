#!/usr/bin/env python
"""Self-tests for app/core/color_calibration.py — run after any change to
that file. No DB/network needed (pure stdlib math).

Usage (from backend/):
    python scripts/test_color_calibration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import color_calibration as cc  # noqa: E402


def test_exact_match_and_interpolation():
    chart = cc.ColorCalibrationChart.from_pairs(
        [(10, (255, 0, 0)), (20, (0, 255, 0)), (30, (0, 0, 255))], name="synthetic"
    )
    orig = cc.raw_to_rgb
    try:
        cc.raw_to_rgb = lambda raw: (255, 0, 0)
        r = chart.match({})
        assert r.distance == 0 and abs(r.value - 10) < 1e-6 and r.in_range, r

        cc.raw_to_rgb = lambda raw: (0, 255, 0)
        r = chart.match({})
        assert r.distance == 0 and abs(r.value - 20) < 1e-6, r

        cc.raw_to_rgb = lambda raw: (127.5, 127.5, 0)
        r = chart.match({})
        assert abs(r.value - 15) < 0.5, r

        cc.raw_to_rgb = lambda raw: (255, 255, 255)
        r = chart.match({})
        assert not r.in_range and r.warning
    finally:
        cc.raw_to_rgb = orig


def test_rgb_to_hex_handles_floats():
    # raw_to_rgb always returns rounded ints, but rgb_to_hex should be
    # robust to floats too (e.g. if ever called directly on an interpolated
    # color for a UI swatch) rather than crashing on format().
    assert cc.rgb_to_hex((127.5, 0.4, 254.9)) == "#8000ff"


def test_raw_to_hex_end_to_end():
    raw = {"F1": 420, "F2": 440, "F3": 460, "F4": 480, "F5": 500, "F6": 900,
           "F7": 850, "F8": 950, "CLEAR": 4000, "NIR": 200}
    h = cc.raw_to_hex(raw)
    assert isinstance(h, str) and h.startswith("#") and len(h) == 7


def test_calibrate_reading_shape():
    top = {"F1": 420, "F2": 440, "F3": 460, "F4": 480, "F5": 500, "F6": 900,
           "F7": 850, "F8": 950, "CLEAR": 4000, "NIR": 200}
    bottom = {"F1": 300, "F2": 350, "F3": 500, "F4": 900, "F5": 1200, "F6": 600,
              "F7": 300, "F8": 200, "CLEAR": 3500, "NIR": 180}
    result = cc.calibrate_reading(top, bottom)
    assert isinstance(result.ph.value, float)
    assert isinstance(result.urea.value, float)
    assert isinstance(result.creatinine.value, float)
    assert result.ph.hex.startswith("#") and result.urea.hex.startswith("#") and result.creatinine.hex.startswith("#")
    assert isinstance(result.overall_valid, bool)


if __name__ == "__main__":
    test_exact_match_and_interpolation()
    test_rgb_to_hex_handles_floats()
    test_raw_to_hex_end_to_end()
    test_calibrate_reading_shape()
    print("All tests passed.")
