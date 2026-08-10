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

## Current state: dummy mode

No sensors are wired up yet. `esp32_sensor.ino` sends plausible random
values inside the dashboard's own reference bands — either every
`SEND_INTERVAL_MS` (5 min) on its own, or immediately when the Dashboard
requests a sample — purely so the whole pipeline — WiFi → HTTPS POST →
Dashboard → AI report/voice/self-care — can be exercised end-to-end with a
bare ESP32.

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
4. Upload, then open the Serial Monitor at 115200 baud — you should see it
   connect to WiFi and `POST /api/readings -> 201` within a few seconds. A
   new reading appears on the Dashboard almost immediately. From then on,
   clicking **Take New Sample** on the Dashboard triggers a fresh reading
   within a few seconds (one `PING_INTERVAL_MS` cycle), and the exact values
   sent are printed to Serial each time (`Reading -> {...}`).

## Switching to real sensors later

Replace the body of `readPH()`, `readCreatinine()`, `readUrea()`,
`readTemperature()` in the sketch with real sensor reads (`analogRead(pin)`,
a sensor library call, etc.), returning the same units the dashboard
expects:

| Function | Unit | Reference band |
|---|---|---|
| `readPH()` | unitless | 6.2–7.6 |
| `readCreatinine()` | mg/dL | 0.6–1.3 |
| `readUrea()` | mg/dL | 7–20 |
| `readTemperature()` | °C | 36.1–37.2 |

Nothing else in the sketch, backend, or website needs to change.

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
