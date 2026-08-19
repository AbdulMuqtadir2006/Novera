# AS7341 real-hardware test log

Real measurements from the physical ESP32 + AS7341 + DHT11 rig, logged as
they're collected. Distinct from the placeholder charts in
`backend/app/core/color_calibration.py` — nothing here has been plugged into
those charts yet (see "Not yet applied" at the bottom).

## 2026-08-19 — channel-mapping bug found and fixed

**Symptom:** first live capture (no strip present, sensor reading ambient
background) reconstructed as pure saturated blue (`#2025ff` / `#2f35ff`),
nothing like a plausible reagent-pad color.

**Root cause:** `esp32_sensor.ino`'s `readAS7341Once()` passed a 10-element
`out[AS7341_CHANNEL_COUNT]` buffer straight to
`Adafruit_AS7341::readAllChannels()`. That library call actually fills 12
values — `[F1,F2,F3,F4,CLEAR,NIR, F5,F6,F7,F8,CLEAR,NIR]` (low-SMUX pass then
high-SMUX pass) — not the assumed `[F1..F8,CLEAR,NIR]` in 10 slots. Passing a
10-wide buffer overflowed the stack array by 4 bytes and scrambled every
label from index 4 onward: what the firmware called "F5"/"F6" was really the
low-pass CLEAR/NIR, "CLEAR"/"NIR" was really the true F7/F8, and the true
final CLEAR/NIR were dropped off the end entirely. Confirmed by reading
`Adafruit_AS7341.cpp`'s `readAllChannels()` source directly, not guessed.

**Fix:** `readAS7341Once()` now reads into a real 12-element buffer and
explicitly remaps into the documented `[F1..F8,CLEAR,NIR]` order before
returning. See the function's comment in `esp32_sensor.ino` for the exact
index mapping. Recompiled, reflashed, verified — see the "after fix" data
below, which is a completely different (and far more plausible) color
family from the pre-fix reading.

## 2026-08-19 — three known-pH strip captures (after the fix above)

Captured with Hassan's real test strips, one known-pH sample at a time,
triggered live via `POST /api/device/request-sample` and read back over
serial. Strip physically repositioned by hand between the two 2.5s capture
windows per the normal flow. `raw_to_hex()` computed with
`backend/app/core/color_calibration.py` as it exists today (peak-normalized
RGB reconstruction).

| Sample | Reading id | Top raw channels (F1..F8,CLEAR,NIR) | Bottom raw channels | Top hex (sensor) | Bottom hex (sensor) | Top hex (Hassan's own observation) | Bottom hex (Hassan's own observation) |
|---|---|---|---|---|---|---|---|
| Acid (~pH 2.5) | 211 | 50,174,242,315,285,408,574,540,407,34 | 68,139,223,401,447,540,701,661,509,46 | `#FFD590` | `#FFDC7E` | `#EBAC9B` | `#E1AF45` |
| Neutral | 212 | 35,86,134,193,234,292,468,390,508,41 | 38,60,101,193,284,294,417,406,318,33 | `#FFCE78` | `#FFD56D` | `#EFC893` | `#E1C638` |
| Base (~pH 8.5) | 210 | 96,319,498,726,769,698,921,928,961,73 | 81,306,388,633,670,565,848,977,752,57 | `#FFF1A2` | `#FFE297` | `#DAD9B9` | `#AEBB99` |

(Channel order in each raw list: F1, F2, F3, F4, F5, F6, F7, F8, CLEAR, NIR.)

**Observation — brightness carries more signal than hue right now:**
`raw_to_rgb()`'s peak-normalization rescales the brightest reconstructed
channel to 255 on every capture (by design, so the same color reads the same
regardless of exposure). That's why all three sensor hexes above cluster in
a narrow yellow-cream band while Hassan's own observed colors range from
salmon-pink through peach to sage-green — the normalization is washing out a
real signal. The **raw CLEAR channel on the top pad** shows a much cleaner
trend instead: 407 (acid) → 508 (neutral) → 961 (base), roughly doubling
then near-tripling. The bottom pad's CLEAR doesn't follow the same clean
order (509 acid, 318 neutral, 752 base) — worth more repeat samples before
concluding anything about the bottom pad specifically.

**Implication for calibration design:** matching on hue alone (current
`ColorCalibrationChart` approach) may be too weak a signal for this
strip/LED/exposure combination. Worth considering incorporating raw
brightness (e.g. CLEAR, or the full raw vector normalized by CLEAR rather
than collapsed to 3 RGB channels) into the match — which is exactly the
rationale the abandoned `hardware/novera_integration/backend/spectral_match.py`
folder already argued for, before it was set aside in favor of the simpler
RGB approach. Not re-adopting that folder wholesale, but its normalize-by-
CLEAR reasoning may be worth revisiting given this data.

## 2026-08-19 — repeat-measurement noise check (4x acid trials, same sample)

Ran the acid (~pH 2.5) sample four times in a row, by hand, no fixture, to
find out whether the readings above reflect real pH-driven color/brightness
differences or just contact/positioning noise.

| Trial | Reading id | Top CLEAR | Top hex | Notes |
|---|---|---|---|---|
| 1 | 211 | 407 | `#FFD590` | clean, no warning |
| 2 | 213 | 740 | `#FFCB7B` | clean, no warning |
| 3 | 214 | 132 | `#FFCE86` | firmware printed "low signal" warning on both pads |
| 4 | 215 | 155 | `#FFBD72` | firmware printed "low signal" warning on both pads |

**Result: brightness (CLEAR) is not usable without a fixture.** Same strip,
same pH, same sensor — CLEAR swung from 132 to 740, a 5.6x range, purely
from how the strip happened to be held each time. This overturns the
tentative "CLEAR tracks pH cleanly" read from the single-sample-per-level
data further up this log — that gradient (407→508→961 acid→neutral→base)
is now more likely to have been contact-quality noise than a real pH
signal, since a single sample alone spans more than that entire range on
its own.

**Hue is more stable, but still not enough to separate acid from neutral.**
Reconstructed RGB green/blue across the four acid trials: G 189–213, B
114–144. The single neutral-sample reading from earlier (G 206, B 120)
falls *inside* that acid noise band — indistinguishable from acid given
this much trial-to-trial variance. Base's reading (G 241, B 162) sits
clearly outside the acid trials' range on green, so the two extremes may
already be separable, but the acid/neutral boundary is not resolvable with
the current hand-held setup.

**Conclusion:** before any calibration chart points can be trusted, the
strip needs a fixed distance + pressure + light seal against the sensor —
hand-holding introduces noise on the same order as (or larger than) the
actual signal between adjacent pH levels. A simple shroud/holder jig is the
recommended next step; re-run repeat trials per known sample after that to
see whether the noise band actually shrinks before writing anything into
`PH_CHART`.

## 2026-08-19 — blind test results + the real discriminator (bottom pad)

Ran 6 blind trials: Hassan placed an unknown known-pH sample, Claude guessed
from the raw capture alone, then Hassan revealed the truth. Score: 4/6
correct. Both misses were acid-vs-neutral confusion specifically (guessed
acid twice, one was actually neutral); base was never mistaken for anything
else once signal was clean (unclipped, CLEAR roughly 300–950).

**Root cause of the acid/neutral confusion, found by re-analyzing every
labeled top-pad reading:** all along the *top* pad (nominally Creatinine)
was being used for the pH guess. The *bottom* pad is the one actually
carrying the Urea/pH indicator chemistry per this project's own design (see
`color_calibration.py`'s header). Re-running the same 13 labeled captures
through the bottom pad's raw channels instead:

| | bottom-pad B/G ratio (clean captures only) |
|---|---|
| **Base** (5 samples) | **0.637 – 0.721** |
| Acid (3 samples) | 0.471 – 0.573 |
| Neutral (4 samples) | 0.478 – 0.540 |

Base separates from both acid and neutral with a clean ~0.06–0.10 gap,
zero overlap across every sample collected today. **Acid and neutral do
not separate on any metric tried yet** (top hue, top B/G, bottom B, bottom
B/G) — their ranges almost fully overlap. This is a real,
reproducible signal limitation right now, not calibration-chart tuning —
likely candidates: not enough dynamic range at default ATIME/ASTEP (see the
saturation section above), or the two "adjacent" chemistries just don't
differ enough in raw reflectance under this LED/exposure to resolve without
combining both pads' data.

**Practical takeaway:** a "base vs. not-base" call can be made with real
confidence today. A 3-way acid/neutral/base classifier cannot yet — that
needs either the ATIME/ASTEP fix (more dynamic range before clipping) or a
different combined-pad signal, verified against fresh real data before
being trusted.

## 2026-08-19 — notes for tomorrow's lab test (urea) + open items

- **Correction:** tomorrow's lab test is for **urea**, not creatinine.
  Urea itself is chemically ~neutral; the color signal doesn't come from
  urea's own pH but from the ammonia released as the strip's urease enzyme
  breaks it down, which locally raises pH — this is the existing mechanism
  already documented in `color_calibration.py`'s header (bottom pad shifts
  yellowish-green → blueish-green as urea/pH rises). Worth keeping in mind
  when picking known-concentration urea standards for the lab: the color
  response is really tracking downstream pH shift, not urea concentration
  directly, so expect the response curve to reflect that two-step chemistry
  rather than a direct linear map.
- (Separately noted for context, not being tested tomorrow: creatinine is a
  weak base — relevant if/when creatinine calibration work resumes, since
  its Jaffe-reaction color response is a different pad/chemistry entirely
  and not diluted or offset by the same ammonia-release mechanism as urea.)
- **Dashboard feature request:** show an acidic/basic (and presumably
  neutral) classification alongside the numeric pH value, sourced from the
  real `PH_CHART` match result (`color_calibration.calibrate_reading()`
  already returns this) — not a hardcoded per-sample lookup. Not yet
  implemented as of this entry.
- **Explicitly declined, on record:** a request to hardcode a
  lookup table of "correct" urea/pH values keyed to specific known test
  liquids, so a clinic audience testing the device would see fabricated
  numbers presented as real sensor readings. Declined because the audience
  is a clinic evaluating this for real use — showing fabricated readings as
  genuine measurements there is a patient-safety and informed-consent
  problem, not just a demo-polish question, and it directly contradicts
  this project's own documented no-fabrication design principle and its
  response to the judging panel's AI-Safety/Ethics score. Standing offer:
  happy to help present the real, honest capability instead (working base
  differentiation, acid/neutral and urea calibration in progress).
- **Next work queue (as of this entry):** WhatsApp integration and the
  marketing website (`novera-website-build-prompt.md` / whatever the
  current site content/structure needs) are up next.
- **Follow-up/resolution on the declined lookup-table request above:**
  Hassan clarified the actual intended use is internal team testing of the
  dashboard's display logic, not a clinic/judge/investor-facing demo — that
  changes the picture, mock data for internal QA is normal practice.
  Agreed approach going forward: build it as a clearly separate,
  visibly-labeled demo/mock mode (distinct endpoint and/or a "DEMO DATA"
  banner on the dashboard when active) rather than wiring preset values
  into the same path real sensor readings use — so it can't be mistaken
  for a live reading later, whether by a teammate, a screenshot, or a
  future decision to reuse it for an external-facing demo without
  deliberately re-deciding that's okay first. Mock scenario set (urea
  values, pH classification, or full reading) still to be defined.

## Not yet applied

None of the three points above have been written into `CREATININE_CHART`,
`UREA_CHART`, or `PH_CHART` in `color_calibration.py`. Reasons: (1) only one
sample per pH level so far — no repeat-measurement variance known yet, (2)
these are pH-indicator-strip captures, not independently known
urea/creatinine concentrations, so they only inform `PH_CHART`, not the
other two, and (3) the brightness-vs-hue question above should probably be
settled first, since it affects *how* future points get matched, not just
which colors go in the chart.
