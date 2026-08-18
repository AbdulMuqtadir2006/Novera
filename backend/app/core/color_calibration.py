"""Color-based calibration for the two-pad AS7341 test strip.

Scope, deliberately narrow: raw AS7341 spectral channels -> an RGB/hex
color -> a biomarker value, by comparing that color against a calibration
chart of (known_value, reference_color) points. Nothing else. This does
NOT introduce new API endpoints, a session/polling system, or a
BUN:Creatinine ratio — those were explored in a separate, disconnected
folder (hardware/novera_integration/) and were explicitly NOT adopted;
only the "raw channels -> hex -> calibrated value" piece was wanted here.

Physical setup this models (confirmed with Hassan, not guessed):
  - TWO reagent pads on one strip, read sequentially, strip repositioned
    by hand between the two captures (same manual-slide mechanic the
    existing 3-pad flow already uses, just simplified to 2 pads + fixed
    timing instead of stability-detection — see esp32_sensor.ino).
  - Top pad: Creatinine. Jaffe reaction -> pinkish (normal) shifting to
    reddish (high/dangerous). Matches this codebase's own existing
    chemistry note (esp32_sensor.ino's header comment on the Jaffe
    reaction) — not a new invention.
  - Bottom pad: Urea AND pH, from the SAME capture (pH is not a separate
    pad — it "rides along" on the urea pad's color, per Hassan). Plausible
    real chemistry: a urease-based strip using a pH indicator that shifts
    yellowish-green (normal) -> blueish-green (high urea / high pH from
    ammonia release).
  - Temperature is NOT part of this module at all — it's a real DHT11
    sensor reading, untouched by any color logic.

*** ALL CALIBRATION CHART VALUES BELOW ARE PLACEHOLDERS. ***
Same situation as esp32_sensor.ino's own mapRawToRange() before it: this
lets the pipeline run end-to-end for testing, but every real anchor point
must come from running actual known-concentration standards through the
real strips + AS7341 and recording the resulting raw channels. Do not
trust any output of this module against a real sample until that's done.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Canonical channel order — matches what Adafruit_AS7341::readAllChannels()
# returns per esp32_sensor.ino's own header-comment warning (verify against
# the actual library version before trusting real readings from a new
# library install: File -> Examples -> Adafruit AS7341 -> as7341).
CHANNELS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "CLEAR", "NIR"]


# ---------------------------------------------------------------------------
# raw channels -> RGB/hex
# ---------------------------------------------------------------------------
# Weighted-sum reconstruction of the 8 visible-spectrum channels into an
# approximate RGB color. These weights are not new — they're the same ones
# already used in hardware/esp32_sensor/as7341_urine_strip_calibration.html
# (a rough approximation of each channel's contribution to red/green/blue
# perception), ported to Python here rather than re-derived, so the two
# tools agree. Same caveat as that file states: "indicative...not a
# clinical colour reference" — good enough to compare against a
# calibration chart of colors captured the same way, not a certified
# colorimetric transform.
def raw_to_rgb(raw: dict[str, float]) -> tuple[int, int, int]:
    f = lambda n: float(raw.get(f"F{n}", 0) or 0)
    r = 0.04*f(1) + 0.05*f(2) + 0.08*f(3) + 0.16*f(4) + 0.32*f(5) + 0.58*f(6) + 0.86*f(7) + 1.00*f(8)
    g = 0.05*f(1) + 0.12*f(2) + 0.34*f(3) + 0.72*f(4) + 1.00*f(5) + 0.72*f(6) + 0.29*f(7) + 0.08*f(8)
    b = 0.82*f(1) + 1.00*f(2) + 0.94*f(3) + 0.49*f(4) + 0.13*f(5) + 0.03*f(6) + 0.01*f(7)
    peak = max(r, g, b, 1.0)
    return tuple(min(255, round(255 * ((v / peak) ** 0.72))) for v in (r, g, b))


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(v))) for v in rgb)
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def raw_to_hex(raw: dict[str, float]) -> str:
    return rgb_to_hex(raw_to_rgb(raw))


# ---------------------------------------------------------------------------
# color -> biomarker value, by nearest + interpolated-neighbor match
# against a calibration chart, same conceptual approach used (and tested)
# for the earlier spectral-vector version — applied to RGB distance instead,
# since that's what was asked for here.
# ---------------------------------------------------------------------------
def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


@dataclass
class CalibrationPoint:
    value: float                     # known concentration/value for this standard
    rgb: tuple[int, int, int]


@dataclass
class MatchResult:
    value: float
    nearest_value: float
    confidence: float
    distance: float
    in_range: bool
    hex: str
    warning: Optional[str] = None


class ColorCalibrationChart:
    """One biomarker's calibration curve: known values mapped to reference colors."""

    # RGB-distance above which a reading is considered "doesn't match this
    # chart at all" (0-255 scale per channel, so max possible distance is
    # ~441). Placeholder — tune once real repeat-measurement variance from
    # the actual strips is known.
    OUT_OF_RANGE_DISTANCE = 60.0

    def __init__(self, points: list[CalibrationPoint], name: str = ""):
        self.points = sorted(points, key=lambda p: p.value)
        self.name = name

    @classmethod
    def from_pairs(cls, pairs: list[tuple[float, tuple[int, int, int]]], name: str = "") -> "ColorCalibrationChart":
        return cls([CalibrationPoint(v, rgb) for v, rgb in pairs], name)

    def match(self, raw: dict[str, float]) -> MatchResult:
        rgb = raw_to_rgb(raw)
        dists = [_rgb_distance(rgb, p.rgb) for p in self.points]

        best_i = min(range(len(self.points)), key=lambda i: dists[i])
        best_pt, best_d = self.points[best_i], dists[best_i]

        neighbor_i = None
        if best_i > 0:
            neighbor_i = best_i - 1
        if best_i < len(self.points) - 1:
            if neighbor_i is None or dists[best_i + 1] < dists[neighbor_i]:
                neighbor_i = best_i + 1

        interp_value = best_pt.value
        if neighbor_i is not None:
            other_pt, d_other = self.points[neighbor_i], dists[neighbor_i]
            span = best_d + d_other
            if span > 1e-9:
                t = best_d / span
                interp_value = best_pt.value + t * (other_pt.value - best_pt.value)

        confidence = max(0.0, 1.0 - best_d / self.OUT_OF_RANGE_DISTANCE)
        in_range = best_d <= self.OUT_OF_RANGE_DISTANCE
        warning = None
        if not in_range:
            warning = (
                f"'{self.name}' reading (dist={best_d:.1f}) doesn't match any calibrated "
                f"color closely — do not trust this value."
            )

        return MatchResult(
            value=round(interp_value, 3),
            nearest_value=best_pt.value,
            confidence=round(confidence, 3),
            distance=round(best_d, 2),
            in_range=in_range,
            hex=rgb_to_hex(rgb),
            warning=warning,
        )


# ---------------------------------------------------------------------------
# PLACEHOLDER calibration charts. Units match what POST /api/readings and
# reference_data.py already use (mg/dL, unitless pH) — deliberately NOT the
# µmol/L creatinine unit scoring.py uses internally, so there is exactly one
# unit in play at the readings-table layer; scoring.py's existing
# CREATININE_MGDL_TO_UMOLL conversion still runs downstream, unchanged.
#
# Anchor points below span each biomarker's existing normal band
# (reference_data.py's REFERENCE dict) plus a "dangerous" point beyond it,
# with placeholder RGB colors following the pinkish->reddish (creatinine)
# and yellowish-green->blueish-green (urea/pH) progressions Hassan
# described. These colors are illustrative guesses, not measured — replace
# every point here with a real color captured from a known-concentration
# standard before trusting this against a real sample.
# ---------------------------------------------------------------------------

CREATININE_CHART = ColorCalibrationChart.from_pairs([
    (0.6, (235, 150, 170)),   # low-normal: light pink
    (1.0, (225, 110, 140)),   # mid-normal: pink
    (1.3, (210, 80, 110)),    # high-normal edge: deeper pink
    (2.5, (190, 40, 50)),     # dangerous: red
], name="creatinine_mg_dl")

UREA_CHART = ColorCalibrationChart.from_pairs([
    (7,  (185, 205, 90)),     # low-normal: yellowish-green
    (14, (140, 195, 110)),    # mid-normal: green
    (20, (100, 185, 130)),    # high-normal edge: green, cooler
    (45, (55, 150, 165)),     # dangerous: blueish-green
], name="urea_mg_dl")

# pH "rides along" on the same bottom-pad color as urea (Hassan's design —
# one physical pad, one capture, two separate value charts matched against
# the same color). Anchor points reuse the same color progression, mapped
# onto pH's own normal band instead of urea's.
PH_CHART = ColorCalibrationChart.from_pairs([
    (6.2, (185, 205, 90)),
    (6.9, (140, 195, 110)),
    (7.6, (100, 185, 130)),
    (8.2, (55, 150, 165)),
], name="ph")


@dataclass
class DualPadResult:
    ph: MatchResult
    urea: MatchResult
    creatinine: MatchResult
    overall_valid: bool
    warnings: list[str] = field(default_factory=list)


def calibrate_reading(top_raw: dict[str, float], bottom_raw: dict[str, float]) -> DualPadResult:
    """top_raw = creatinine pad capture, bottom_raw = urea+pH pad capture."""
    creat = CREATININE_CHART.match(top_raw)
    urea = UREA_CHART.match(bottom_raw)
    ph = PH_CHART.match(bottom_raw)

    warnings = [w for w in (creat.warning, urea.warning, ph.warning) if w]
    return DualPadResult(
        ph=ph,
        urea=urea,
        creatinine=creat,
        overall_valid=creat.in_range and urea.in_range and ph.in_range,
        warnings=warnings,
    )
