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

## Current state: real temperature, estimated pH/urea/creatinine

- **Temperature**: real, from a DHT11 (`VCC→3V3, GND→GND, DATA→D4`).
- **pH / urea / creatinine**: read from 3 colorimetric reagent pads on a
  single test strip, using one AS7341 spectral color sensor
  (`VIN→3V3, GND→GND, SCL→D22, SDA→D21`, I2C). Since there's only one
  sensor, the strip is slid by hand through 3 marked positions — the
  firmware watches the sensor and auto-captures each pad once its reading
  stabilizes, no button needed. See the header comment in
  `esp32_sensor.ino` for the exact stability-detection logic.
- **MQ gas sensor**: wired for power only (`VCC→VIN`, `GND→GND`, no signal
  pin connected) — its onboard LED just lights up when powered. Not read,
  not sent anywhere.

**Dummy fallback**: if the AS7341 isn't responding, a pad times out (no
strip presented within 60s), or the DHT11 read fails, that specific value
falls back to a random plausible number in its reference range instead of
blocking the send — a reading always goes out every cycle, useful for
testing the rest of the pipeline before all sensors/pads are ready. Serial
prints which fields (if any) were dummy for a given cycle.

**AS7341 init/recovery**: the sensor is initialized once (not re-initialized
every cycle — see `ensureAS7341Ready()` in the sketch), with a few retries on
first init for a transient glitch. If it later stops responding mid-cycle
(all three pads fail to capture even though init succeeded), the firmware
automatically marks it for re-initialization on the next cycle — no manual
reset needed for that case. The one failure mode that still needs a person:
if the chip's internal state gets corrupted by a genuine brownout (e.g. a
marginal VIN supply sagging when the LED turns on), only a full physical
power removal (disconnect VIN, not just the ESP32's reset button) clears
it — software retries alone can't recover from that. Power VIN directly
from the ESP32's own 3V3 pin, not a separate/external 3.3V source, to avoid
that scenario entirely.

**Not real calibration yet.** Converting a raw AS7341 color reading into an
actual pH/mg-dL number needs a calibration curve built from testing
known-concentration reference solutions against the pads. That hasn't been
done — `mapRawToRange()` in the sketch currently just linearly stretches a
raw value between two guessed endpoints onto the reference band, as a
placeholder so the pipeline produces *some* number for demo purposes. Say
so in any demo; replace `PH_RAW_MIN/MAX` etc. with real endpoints once
trials against known references are run.

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
   WiFi, then prompts you over Serial to slide the strip through the pH,
   Urea, and Creatinine pad positions in turn, then reads the DHT11 and
   `POST`s to `/api/readings -> 201`. From then on, clicking **Take New
   Sample** on the Dashboard triggers the same prompt sequence within a few
   seconds (one `PING_INTERVAL_MS` cycle).

## Building a real calibration curve

`PH_RAW_MIN/MAX`, `UREA_RAW_MIN/MAX`, `CREATININE_RAW_MIN/MAX` in the
sketch are currently guessed placeholders. To make them real: prepare a
handful of reference solutions at known concentrations (or known pH
values), run each through the pad + AS7341, note the raw channel value
`captureStablePad()` prints for that pad, and use the lowest/highest values
you observe as the new endpoints — or better, fit a proper regression
across several points instead of just two, if the color response isn't
linear.

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
