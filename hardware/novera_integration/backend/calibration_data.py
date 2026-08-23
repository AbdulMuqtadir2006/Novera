"""
NOVERA per-analyte calibration tables + combination logic.

Field names match your existing schema (scoring.py / schemas.py):
    urea_mg_dl, creatinine_umol_l, ph, temperature_c

*** ALL CHARTS BELOW ARE PLACEHOLDER DATA. *** Same situation as before --
these let the pipeline run end-to-end for testing, but every real value must
come from your own standards run through the real device. See
docs/START_HERE.md section on calibration data collection.

Known from the real firmware (esp32_sensor.ino) at discovery time:
    - urea       -> CLEAR channel
    - creatinine -> F6 (~590nm)
    - ph, temperature -> NOT YET MAPPED to any channel/sensor in the
      discovered firmware. Claude Code: check the current esp32_sensor.ino
      for whether a pH pad / temperature sensor (e.g. DS18B20, thermistor)
      exists in hardware before assuming a channel for these two -- don't
      guess a channel mapping that isn't backed by the real wiring.
"""

from spectral_match import SpectralCalibrationChart
from typing import Optional


# ---------------------------------------------------------------------------
# PLACEHOLDER calibration standards. Replace via the real lab-standards
# workflow (see START_HERE.md) before trusting any output.
# Structure: (known_value, {channel: raw_count, ...})
# ---------------------------------------------------------------------------

UREA_CHART = SpectralCalibrationChart.from_pairs([
    (7,  {"F1":420,"F2":440,"F3":460,"F4":480,"F5":500,"F6":520,"F7":540,"F8":560,"CLEAR":3800,"NIR":200}),
    (14, {"F1":440,"F2":460,"F3":480,"F4":500,"F5":520,"F6":540,"F7":560,"F8":580,"CLEAR":4200,"NIR":210}),
    (20, {"F1":460,"F2":480,"F3":500,"F4":520,"F5":540,"F6":560,"F7":580,"F8":600,"CLEAR":4600,"NIR":220}),
    (30, {"F1":480,"F2":500,"F3":520,"F4":540,"F5":560,"F6":580,"F7":600,"F8":620,"CLEAR":5000,"NIR":230}),
], name="urea_mg_dl")

CREATININE_CHART = SpectralCalibrationChart.from_pairs([
    # values in umol/L directly (matches scoring.py's unit) -- these are
    # 0.6/1.0/1.3/2.0 mg/dL converted via *88.42, NOT independently chosen,
    # so there is exactly one unit in play here and nothing to reconcile later.
    (53,  {"F1":380,"F2":400,"F3":420,"F4":440,"F5":460,"F6":700, "F7":460,"F8":440,"CLEAR":3600,"NIR":190}),
    (88,  {"F1":390,"F2":410,"F3":430,"F4":450,"F5":470,"F6":900, "F7":470,"F8":450,"CLEAR":3700,"NIR":195}),
    (115, {"F1":400,"F2":420,"F3":440,"F4":460,"F5":480,"F6":1100,"F7":480,"F8":460,"CLEAR":3800,"NIR":200}),
    (177, {"F1":410,"F2":430,"F3":450,"F4":470,"F5":490,"F6":1400,"F7":490,"F8":470,"CLEAR":3900,"NIR":205}),
], name="creatinine_umol_l")

CREATININE_MGDL_TO_UMOLL = 88.42  # already used in scoring.py -- reuse the same constant, don't redefine it twice

# pH and temperature charts intentionally left undefined here -- see the
# docstring above. Claude Code should add these once the real sensor/pad
# mapping is confirmed, following the exact same SpectralCalibrationChart
# pattern as urea/creatinine above (or a simple analog-sensor read function
# for temperature if it's not colorimetric at all).


def combine_readings(urea_mg_dl: float, creatinine_umol_l: float) -> tuple:
    """
    BUN:Creatinine ratio, same default + same caveats as the earlier version:
    textbook formula (~10:1-20:1 commonly cited normal range), NOT a validated
    NOVERA/clinical-partner-confirmed threshold. Confirm real cutoffs with
    Ester Hospital / Racks Lab before this feeds anything user-facing.

    Uses creatinine_umol_l directly since that's the unit scoring.py already
    standardizes on -- converts to mg/dL internally for the ratio formula.
    """
    creat_mgdl = creatinine_umol_l / CREATININE_MGDL_TO_UMOLL
    if creat_mgdl <= 0:
        return None, "creatinine reading was zero or invalid, cannot compute ratio"

    bun = urea_mg_dl * 0.467
    ratio = round(bun / creat_mgdl, 2)

    if ratio > 20:
        flag = "above typical range (~20:1) -- commonly associated with prerenal causes; not a diagnosis"
    elif ratio < 10:
        flag = "below typical range (~10:1) -- confirm with clinical partner; not a diagnosis"
    else:
        flag = "within commonly cited normal range (~10:1-20:1)"

    return ratio, flag
