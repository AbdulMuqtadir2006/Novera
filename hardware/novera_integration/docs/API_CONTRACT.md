# Reading-Session API Contract

Three parties, all talking through the backend (ESP32 never talks to the dashboard directly):

```
Dashboard  --POST-->  Backend  <--poll (GET)--  ESP32
Dashboard  <--poll (GET)--  Backend  <--PATCH--  ESP32
```

## 1. Dashboard starts a reading

`POST /api/reading-sessions`

Request body: `{}` (or `{"device_id": "NOVERA-ESP32-001"}` if targeting a specific device in a multi-device setup)

Response:
```json
{
  "id": "c5cc97da-...",
  "device_id": null,
  "status": "requested",
  "created_at": "2026-08-18T12:40:00Z",
  ...
}
```

Dashboard stores `id`, immediately starts polling step 4.

## 2. ESP32 polls for work (every ~1.5s while idle)

`GET /api/reading-sessions/pending?device_id=NOVERA-ESP32-001`

- Nothing pending → `null` / empty response
- Session found → claims it (status becomes `acknowledged`), returns the session object. **ESP32 turns its status LED light-blue the moment it receives this response** and starts its internal 5-second window.

## 3. ESP32 posts the result (after its 5s window + capture)

Success:
`PATCH /api/reading-sessions/{id}/complete`
```json
{
  "raw_channels": {
    "F1": 460.3, "F2": 480.1, "F3": 500.0, "F4": 520.7, "F5": 540.2,
    "F6": 1100.5, "F7": 580.0, "F8": 460.9, "CLEAR": 4600.0, "NIR": 220.1
  }
}
```
Backend runs calibration matching server-side and returns the full session including computed `results`.

Failure (e.g. sensor read error):
`PATCH /api/reading-sessions/{id}/fail`
```json
{"error": "AS7341 I2C timeout"}
```

## 4. Dashboard polls for the result (every ~1s while waiting)

`GET /api/reading-sessions/{id}`

```json
{
  "id": "c5cc97da-...",
  "status": "complete",
  "raw_channels": {...},
  "results": {
    "urea_mg_dl": 10.49,
    "urea_confidence": 0.87,
    "urea_in_range": true,
    "creatinine_umol_l": 75.86,
    "creatinine_confidence": 0.91,
    "creatinine_in_range": true,
    "bun_creatinine_ratio": 5.71,
    "ratio_flag": "below typical range (~10:1) -- confirm with clinical partner; not a diagnosis",
    "overall_valid": true,
    "warnings": []
  }
}
```

Dashboard states to design for:
- `requested` → "Waiting for device..."
- `acknowledged` → "Reading in progress — do not remove the strip" (this is the 5s+ window; if you want the UI to visually count down, it can, but the LED is the real user-facing signal)
- `complete` → show results (check `overall_valid` — if false, show a "reading failed, please retry" state instead of the raw numbers, and surface `warnings`)
- `failed` / `timed_out` → show retry prompt with the `error` message

## Notes

- **pH and temperature are not in this contract yet.** `raw_channels` only carries AS7341 spectral data. Once the pH pad / temperature sensor situation is confirmed (see `calibration_data.py` docstring and `START_HERE.md`), extend `raw_channels` (or add a sibling field, e.g. `"temperature_c": 36.4` read directly if it's a non-colorimetric sensor) and extend `compute_results()` in `reading_session.py` to match.
- Session timeouts (`CLAIM_TIMEOUT_SECONDS`, `RESULT_TIMEOUT_SECONDS` in `reading_session.py`) exist so the dashboard doesn't poll forever if the device is offline or something goes wrong mid-capture — surface these as a clear "device didn't respond" state, not a silent infinite spinner.
