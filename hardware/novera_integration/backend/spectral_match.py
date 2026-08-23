"""
NOVERA spectral calibration matching engine — v2.

CHANGE FROM v1 (color_match.py / hex+Lab approach):
Discovery of the real repo showed the live firmware (esp32_sensor.ino) never
builds an RGB/hex value at all — it reads raw AS7341 channel counts directly
(Clear channel for urea, F6/~590nm for creatinine). Converting 10 spectral
channels down to 3 RGB channels before matching throws away information for
no benefit, and requires an extra conversion step that doesn't exist in your
firmware today. This version matches directly on the normalized spectral
vector instead. Keep hex/RGB purely for drawing a color swatch in the
dashboard UI if you want one — never use it as the matching input.

Pipeline:
    raw AS7341 channels (F1..F8, Clear, NIR)
        -> normalize (divide by Clear or by vector norm, to cancel out
           brightness/distance/ambient-light differences between readings)
        -> compare against calibration vectors for one analyte
        -> nearest + second-nearest -> interpolated concentration
"""

from dataclasses import dataclass, field
from typing import List, Optional
import math

# Canonical channel order used throughout this module and the firmware payload.
CHANNELS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "CLEAR", "NIR"]


def normalize_vector(raw: dict) -> List[float]:
    """
    Convert a raw channel-count dict into a normalized vector that's
    comparable across readings taken at slightly different brightness/
    distance/integration-time (as long as gain/ATIME/ASTEP are held fixed
    for a given reading, which they should be for calibration to be valid).

    Normalizes by the CLEAR channel (a broadband brightness reference) --
    this is the standard trick for making paper-strip colorimetry robust to
    lighting variation between reads. If CLEAR is 0 or missing, falls back
    to unit-vector normalization.
    """
    vec = [float(raw.get(ch, 0)) for ch in CHANNELS]
    clear = raw.get("CLEAR", 0)
    if clear and clear > 0:
        return [v / clear for v in vec]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        return [v / norm for v in vec]
    return vec


def vector_distance(v1: List[float], v2: List[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))


@dataclass
class CalibrationPoint:
    value: float                 # known concentration for this standard
    raw_channels: dict           # {"F1": ..., ..., "CLEAR": ..., "NIR": ...}
    normalized: List[float] = field(init=False)

    def __post_init__(self):
        self.normalized = normalize_vector(self.raw_channels)


@dataclass
class MatchResult:
    value: float
    nearest_value: float
    confidence: float
    distance: float
    in_range: bool
    warning: Optional[str] = None


class SpectralCalibrationChart:
    """One analyte's calibration curve: a list of (value, raw_channel_dict) standards."""

    # Distance above which a reading is considered "doesn't match this chart
    # at all" -- this is in *normalized* vector-distance units, not deltaE,
    # so it needs its own tuning once you have repeat-measurement data from
    # your real strips. Starting value is a rough placeholder.
    OUT_OF_RANGE_DISTANCE = 0.35

    def __init__(self, points: List[CalibrationPoint], name: str = ""):
        self.points = sorted(points, key=lambda p: p.value)
        self.name = name

    @classmethod
    def from_pairs(cls, pairs, name: str = ""):
        return cls([CalibrationPoint(v, raw) for v, raw in pairs], name)

    def match(self, raw_channels: dict) -> MatchResult:
        target = normalize_vector(raw_channels)
        dists = [vector_distance(target, p.normalized) for p in self.points]

        best_i = min(range(len(self.points)), key=lambda i: dists[i])
        best_pt = self.points[best_i]
        best_d = dists[best_i]

        neighbor_i = None
        if best_i > 0:
            neighbor_i = best_i - 1
        if best_i < len(self.points) - 1:
            if neighbor_i is None or dists[best_i + 1] < dists[neighbor_i]:
                neighbor_i = best_i + 1

        interp_value = best_pt.value
        if neighbor_i is not None:
            other_pt = self.points[neighbor_i]
            d_best, d_other = best_d, dists[neighbor_i]
            span = d_best + d_other
            if span > 1e-9:
                t = d_best / span
                interp_value = best_pt.value + t * (other_pt.value - best_pt.value)

        confidence = max(0.0, 1.0 - best_d / self.OUT_OF_RANGE_DISTANCE)
        in_range = best_d <= self.OUT_OF_RANGE_DISTANCE

        warning = None
        if not in_range:
            warning = (f"Reading is far (dist={best_d:.3f}) from every point on the "
                       f"'{self.name}' calibration chart. Do not trust this value.")

        return MatchResult(
            value=round(interp_value, 3),
            nearest_value=best_pt.value,
            confidence=round(confidence, 3),
            distance=round(best_d, 4),
            in_range=in_range,
            warning=warning,
        )
