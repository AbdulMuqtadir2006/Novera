# NOVERA: Button-Triggered Dual-Pad Reading Integration — Start Here

**Read this whole file before touching code.** It tells you what's in this folder, what to do with it, and — critically — what I could NOT determine without access to the real repo, which you need to check before assuming.

---

## What this delivers

End-to-end flow: dashboard button click → ESP32 turns light-blue LED on → 5 second window → ESP32 captures a spectral reading → backend calibrates it → dashboard shows urea, creatinine (and flags where pH/temperature are still missing — see below).

## Read order

1. This file
2. `docs/API_CONTRACT.md` — exact request/response shapes between dashboard, backend, ESP32
3. `backend/spectral_match.py` + `backend/test_spectral_match.py` — the matching engine, already tested, run the tests yourself to confirm
4. `backend/calibration_data.py` — placeholder calibration tables + the combination formula
5. `backend/reading_session.py` — the trigger state machine + FastAPI routes
6. `firmware/reading_trigger_module.ino` — firmware logic to merge into the real `esp32_sensor.ino`

---

## Why spectral vectors instead of hex/RGB color matching

Earlier version of this work matched on hex color (converted to Lab space). Your discovery pass showed the **real, live firmware never builds a hex value at all** — it reads raw AS7341 channel counts directly (Clear channel for urea, F6 for creatinine). Matching on the full raw spectral vector instead of collapsing to 3 RGB channels first uses more of the sensor's actual information and skips a conversion step your firmware doesn't currently do. `spectral_match.py` normalizes by the CLEAR channel so matching is robust to reading-to-reading brightness variation (verified in the self-tests — same colors at half brightness produce identical normalized vectors). Keep hex/RGB only if you want a color swatch in the dashboard UI — never feed it back into matching.

---

## A bug I caught and fixed — worth knowing about

First draft of `calibration_data.py` had `CREATININE_CHART` placeholder values written as if they were mg/dL (0.6–2.0) but labeled/used downstream as µmol/L, which `combine_readings()` then divided by 88.42 again. Result: a BUN:Creatinine ratio of **503** instead of a sane number. Caught this because I ran the pipeline end-to-end and looked at the actual output rather than trusting the code by inspection — the corrected version is in this folder, values are now genuinely µmol/L (53/88/115/177, i.e. the same 0.6/1.0/1.3/2.0 mg/dL converted once, not twice). **Do the same check** after you plug in real lab data: run `reading_session.py`'s `compute_results()` on a known standard and confirm the ratio lands somewhere plausible before trusting it.

---

## This is additive, not a rebuild

Most of the existing system already works and should not be touched: WiFi/network layer, the AS7341 read call itself, the existing `POST /api/readings` endpoint, the DB schema, the dashboard's display logic, the `confirmed_cases` matching system. Nothing below replaces any of that.

The only genuinely placeholder pieces are the actual calibration **numbers** (this is by the codebase's own admission — `esp32_sensor.ino`'s header comment says so directly, and `REGULATORY_AND_CLINICAL_PATHWAY.md` says the same about clinical thresholds) — not the plumbing around them. What this folder adds is new and specific: the button-trigger session flow (didn't exist before) and a better matching algorithm to slot in once real calibration data exists. Everything else stays as-is. If you find yourself refactoring something outside that scope, stop and check it's actually necessary.

## Task checklist

### 1. Backend merge
- [ ] Copy `spectral_match.py`, `calibration_data.py`, `reading_session.py` into your backend, alongside the existing `scoring.py` / `reference_data.py`.
- [ ] Run `test_spectral_match.py` — confirm it passes in your real environment.
- [ ] Replace `SessionStore`'s in-memory dict with your real Postgres layer — add a `reading_sessions` table mirroring your existing `readings` table pattern. Keep the state-machine logic in `SessionStore` the same; only the storage calls change.
- [ ] Mount `reading_session.router` into your FastAPI app.
- [ ] `creatinine_umol_l` conversion already reuses `CREATININE_MGDL_TO_UMOLL = 88.42` — don't redefine this constant a third time, import it from wherever `scoring.py` already defines it if that's cleaner than the copy in `calibration_data.py`.

### 2. Firmware merge — **do not overwrite the real file with the .ino in this folder**
- [ ] Open the real `esp32_sensor.ino`.
- [ ] Merge in the state machine, LED functions, and HTTP calls from `firmware/reading_trigger_module.ino` — every `TODO` in that file needs a real answer from the actual file/hardware, not a guess. Specifically:
  - **Status LED GPIO pin** — not defined anywhere in the discovered code. Confirm actual wiring before picking a pin number. If it's an RGB/NeoPixel module rather than a single blue LED, use the commented-out NeoPixel variant instead of the plain `digitalWrite` version.
  - **AS7341 channel read call** — reuse whatever the existing firmware already uses (likely `Adafruit_AS7341::readAllChannels()`), and double-check the channel **index order** returned by that call maps correctly onto `F1..F8, CLEAR, NIR` — don't assume the library's array order matches that label order without checking the library source/docs.
  - **WiFi/HTTP boilerplate** — reuse what's already in the file for `POST /api/readings`; don't duplicate a second HTTP client setup.
- [ ] Call `callReadingStateMachine()` every `loop()` iteration, non-blocking (uses `millis()`, not `delay()`) so it doesn't block other firmware housekeeping during the 5-second window.

### 3. Dashboard button
- [ ] "Start Reading" button → `POST /api/reading-sessions`, store returned `id`, begin polling `GET /api/reading-sessions/{id}` every ~1s.
- [ ] UI states: `requested` (waiting for device) → `acknowledged` (reading in progress, ~5s+) → `complete` (show results — check `overall_valid` first, show a retry prompt if false) → `failed`/`timed_out` (show `error`, offer retry).
- [ ] Full shapes for every state are in `docs/API_CONTRACT.md`.

### 4. Real calibration data (blocks going live, not blocks integration)
- [ ] Everything above will run end-to-end today on placeholder numbers. Before this touches a real sample: run known-concentration urea and creatinine standards through the actual strips + AS7341, capture the raw channel readings, and replace the placeholder points in `UREA_CHART` / `CREATININE_CHART`. More points, especially near clinically relevant thresholds, means better interpolation.
- [ ] Tune `SpectralCalibrationChart.OUT_OF_RANGE_DISTANCE` (currently a placeholder guess) once you have real repeat-measurement variance to know what "normal noise" vs. "genuinely off-chart" looks like.

---

## Two things that need Hassan's (or a clinician's) confirmation, not a guess

1. **pH and temperature are not wired into any of this.** The discovered firmware only maps urea and creatinine to AS7341 channels — no channel or sensor is documented for pH or temperature anywhere in the discovery pass. Before adding them: check whether there's a third colorimetric pad (pH) and what physical sensor handles temperature (e.g. DS18B20, thermistor — different code either way). Do not invent a channel mapping for these without checking the actual hardware.
2. **`combine_readings()` (the BUN:Creatinine ratio)** is still the textbook default, not a validated NOVERA/clinical-partner threshold. `REGULATORY_AND_CLINICAL_PATHWAY.md` already says real cutoffs need to come from a clinician — get that sign-off before this ratio (or whatever combined metric you actually want) feeds anything user-facing.

---

## Files in this folder

```
START_HERE.md                          <- this file
docs/
  API_CONTRACT.md                      <- exact request/response schemas
backend/
  spectral_match.py                    <- matching engine (tested)
  test_spectral_match.py               <- run this after any change to spectral_match.py
  calibration_data.py                  <- placeholder calibration tables + combine_readings()
  reading_session.py                   <- trigger state machine + FastAPI routes (tested)
firmware/
  reading_trigger_module.ino           <- merge into real esp32_sensor.ino, don't overwrite
```
