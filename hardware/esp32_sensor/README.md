# Novera ESP32 sensor node

Wireless reading source for the Dashboard. An ESP32 on your WiFi network
POSTs directly to the live backend (`POST /api/readings`) — no laptop, USB
cable, or browser involved. The endpoint already accepts a partial JSON body
and fills in anything missing with its own randomized values, so this sketch
needed zero backend or frontend changes.

It also heartbeats `POST /api/device/ping` every `PING_INTERVAL_MS` (3s)
with its current SSID. That heartbeat does two things:
- Lets the Dashboard show live connected/offline status + which WiFi
  network the device is on (`GET /api/device/status`, derived purely from
  how recently a ping landed — see `backend/app/routers/device.py`).
- Carries back whether the Dashboard's **"Take New Sample"** button was
  clicked (`POST /api/device/request-sample` sets a flag). If so, the ESP32
  takes and sends a reading immediately instead of waiting for the next
  `SEND_INTERVAL_MS` tick.

## Current state: real temperature, color-calibrated pH/urea/creatinine

- **Temperature**: real, from a DHT11 (`VCC→3V3, GND→GND, DATA→D4`).
- **pH / urea / creatinine**: read from **2** colorimetric reagent pads on a
  single test strip, using one AS7341 spectral color sensor
  (`VIN→3V3, GND→GND, SCL→D22, SDA→D21`, I2C). Top pad = Creatinine
  (Jaffe reaction: pinkish → reddish as it rises). Bottom pad = Urea **and**
  pH together, from the same capture (yellowish-green → blueish-green as
  urea rises). Since there's only one sensor, the strip is slid by hand to
  the second pad position during a brief pause between the two captures.
  Each capture is a **fixed 2.5-second window** (not stability-detected) —
  the AS7341's onboard LED and the external ready LED are both on for the
  whole window, off briefly between the two windows as the "reposition now"
  signal. Two windows = 5 seconds total, matching the intended UX for the
  Dashboard's "Take New Sample" button. See `runFullTest()` in
  `esp32_sensor.ino`.
- **MQ gas sensor**: wired for power only (`VCC→VIN`, `GND→GND`, no signal
  pin connected) — its onboard LED just lights up when powered. Not read,
  not sent anywhere.

**Calibration happens on the backend, not here.** This sketch's only job is
capturing the two pads' raw AS7341 channels (F1–F8, Clear, NIR) as
accurately as it can and sending both raw channel sets to
`POST /api/readings`. Converting those raw colors into an actual pH/mg-dL
number — an RGB/hex conversion, then matching against a calibration chart —
happens in `backend/app/core/color_calibration.py`. This keeps math off the
ESP32 (same pattern the rest of NOVERA's decision logic already follows)
and means calibration data can be updated without reflashing firmware.

**Dummy fallback**: if the AS7341 isn't responding at all, or neither
capture window gets a single successful read, that cycle sends temperature
only (no raw-channel fields) — the backend's existing jitter-based fallback
fills in a plausible ph/urea/creatinine, the same fallback path a totally
sensorless reading has always used. There's no per-field dummy value on the
ESP32 side anymore for color-derived fields, since there's no on-device
calibration left to fall back from.

**AS7341 init/recovery**: the sensor is initialized once (not re-initialized
every cycle — see `ensureAS7341Ready()` in the sketch), with a few retries on
first init for a transient glitch. If it later stops responding mid-cycle
(both pads fail to capture even though init succeeded), the firmware
automatically marks it for re-initialization on the next cycle — no manual
reset needed for that case. The one failure mode that still needs a person:
if the chip's internal state gets corrupted by a genuine brownout (e.g. a
marginal VIN supply sagging when the LED turns on), only a full physical
power removal (disconnect VIN, not just the ESP32's reset button) clears
it — software retries alone can't recover from that. Power VIN directly
from the ESP32's own 3V3 pin, not a separate/external 3.3V source, to avoid
that scenario entirely.

**Not real calibration yet.** Every calibration chart in
`color_calibration.py` is placeholder data — illustrative colors, not
measured ones. Building a real calibration curve means running
known-concentration reference solutions through the actual pads + AS7341,
recording the resulting raw channels, and replacing the placeholder points
in `CREATININE_CHART` / `UREA_CHART` / `PH_CHART` there. Say so in any demo
until that's done.

Libraries needed (Arduino Library Manager, in addition to the ESP32 board
package): **"DHT sensor library"** by Adafruit (+ its "Adafruit Unified
Sensor" dependency), and **"Adafruit AS7341"**.

## Flashing it

1. Arduino IDE → Preferences → Additional Board Manager URLs, add:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. Boards Manager → install **esp32** (by Espressif Systems). This also
   provides `WiFi.h`, `WiFiClientSecure.h`, `HTTPClient.h` — no other
   libraries to install.
3. Select your board (e.g. "ESP32 Dev Module") and its serial port.
3. Open `esp32_sensor.ino`, fill in `WIFI_SSID_1` / `WIFI_PASSWORD_1` (and
   `_2`, `_3`, ... for any extra networks, e.g. a phone hotspot — it joins
   whichever is in range).
4. Upload, then open the Serial Monitor at 115200 baud — it connects to
   WiFi, then prompts you over Serial to position the strip at the
   Creatinine (top) pad for 2.5s, reposition to the Urea/pH (bottom) pad
   for another 2.5s, then reads the DHT11 and `POST`s to
   `/api/readings -> 201`. From then on, clicking **Take New Sample** on
   the Dashboard triggers the same 5-second sequence within a few seconds
   (one `PING_INTERVAL_MS` cycle).

## Building a real calibration curve

`CREATININE_CHART` / `UREA_CHART` / `PH_CHART` in
`backend/app/core/color_calibration.py` are currently guessed placeholder
(value, RGB color) points — not the ESP32 sketch anymore, since calibration
moved to the backend. To make them real: prepare a handful of reference
solutions at known concentrations (or known pH values), run each through
the pad + AS7341, note the raw channels `captureAveragedWindow()` prints
for that pad, convert to RGB via `color_calibration.raw_to_rgb()` (or just
read the `hex` field the backend already returns per match — see
`MatchResult`), and use those as the new chart points — more points,
especially near clinically relevant thresholds, means better interpolation.

## Notes

- **TLS**: the sketch uses `WiFiClientSecure::setInsecure()` — it skips
  certificate verification, which is fine for a research prototype hitting
  one fixed, known host. If this ever ships as real product hardware, pin
  the cert with `setCACert()` instead.
- **Auth**: `POST /api/readings` currently has no auth requirement (matches
  the rest of the dashboard's demo-data endpoints), so the ESP32 needs no
  API key or token to push readings.
- **Send interval**: defaults to every 5 minutes (`SEND_INTERVAL_MS`) plus
  one immediately on boot. Adjust freely — a real sensor node might read
  and send more or less often depending on what it's measuring.
