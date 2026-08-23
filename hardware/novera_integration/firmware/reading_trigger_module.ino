/*
  NOVERA reading-trigger module.

  *** THIS IS NOT A STANDALONE SKETCH. ***
  I don't have your actual esp32_sensor.ino in front of me (only the
  snippets from the discovery pass), so this is written as functions to
  MERGE into your existing file -- reusing your existing WiFi connection,
  AS7341 object/init, and HTTP client setup. Do NOT just flash this file
  as-is; Claude Code should:
    1. Open the real esp32_sensor.ino
    2. Add the #includes / globals / functions below into it
    3. Replace whatever the current loop() does for triggering a reading
       with callReadingStateMachine() below, called every loop() iteration
    4. Fill in every TODO marked below against the real hardware -- do not
       guess pin numbers or WiFi/backend config that already exist elsewhere
       in the file.

  FLOW:
    idle -> poll backend every POLL_INTERVAL_MS for a pending session
    -> session claimed -> LED light-blue ON, non-blocking 5000ms timer starts
    -> timer elapses -> capture spectral reading (averaged over a few quick
       samples) -> POST result to backend -> LED green (success) or red
       (failure) for LED_RESULT_FLASH_MS -> back to idle
*/

#include <ArduinoJson.h>   // TODO Claude Code: confirm this is already a
                           // dependency in the real project (likely is,
                           // since the firmware already POSTs JSON) -- if not, add it.
// #include <HTTPClient.h>  // TODO: uncomment if not already included elsewhere in the file

// ---------------------------------------------------------------------------
// CONFIG -- TODO Claude Code: fill these in from the REAL project config
// (likely already defined elsewhere in esp32_sensor.ino -- reuse those
// constants instead of duplicating, this block just documents what's needed)
// ---------------------------------------------------------------------------
// const char* BACKEND_HOST = "...";           // already exists for /api/readings
// const char* DEVICE_ID = "...";               // already exists?
// #define STATUS_LED_PIN <TODO_GPIO_NUMBER>    // NOT YET DEFINED ANYWHERE -- confirm
                                                 // actual wiring before picking a pin.
                                                 // If it's an RGB/NeoPixel module instead
                                                 // of a single blue LED, use the
                                                 // NeoPixel variant further down instead.

#define POLL_INTERVAL_MS       1500
#define READING_WINDOW_MS      5000   // LED-on duration before capture, per spec
#define LED_RESULT_FLASH_MS    1500
#define CAPTURE_SAMPLES        3      // average a few quick reads to reduce noise
#define CAPTURE_SAMPLE_GAP_MS  80

enum TriggerState { TS_IDLE, TS_ACKNOWLEDGED, TS_CAPTURING, TS_RESULT_FLASH };

TriggerState triggerState = TS_IDLE;
unsigned long stateEnteredAt = 0;
unsigned long lastPollAt = 0;
String currentSessionId = "";
bool lastResultOk = false;

// ---------------------------------------------------------------------------
// LED control -- SIMPLE SINGLE-COLOR LED VERSION (default assumption)
// If your status indicator is actually a NeoPixel/RGB module, comment this
// block out and uncomment the NeoPixel version below instead.
// ---------------------------------------------------------------------------
void ledOff()        { digitalWrite(STATUS_LED_PIN, LOW); }
void ledLightBlue()  { digitalWrite(STATUS_LED_PIN, HIGH); } // single blue LED: just on
void ledSuccess()    { digitalWrite(STATUS_LED_PIN, HIGH); } // TODO: differentiate from
void ledFailure()    { digitalWrite(STATUS_LED_PIN, LOW);  } //   "ready" state if you only
                                                               //   have one LED color --
                                                               //   e.g. blink pattern instead.

/*
// --- NeoPixel version (uncomment + delete the block above if applicable) ---
// #include <Adafruit_NeoPixel.h>
// #define NEOPIXEL_PIN <TODO_GPIO_NUMBER>
// Adafruit_NeoPixel statusPixel(1, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
// void ledOff()       { statusPixel.setPixelColor(0, 0,0,0); statusPixel.show(); }
// void ledLightBlue() { statusPixel.setPixelColor(0, 100,180,255); statusPixel.show(); }
// void ledSuccess()   { statusPixel.setPixelColor(0, 0,255,0); statusPixel.show(); }
// void ledFailure()   { statusPixel.setPixelColor(0, 255,0,0); statusPixel.show(); }
*/

// ---------------------------------------------------------------------------
// Backend calls -- TODO Claude Code: match these to however the existing
// firmware already does HTTP (WiFiClient / HTTPClient patterns already used
// for POST /api/readings -- reuse the same helper functions if they exist).
// ---------------------------------------------------------------------------

// Returns "" if nothing pending, else the session id.
String pollForPendingSession() {
  // HTTPClient http;
  // http.begin(String(BACKEND_HOST) + "/api/reading-sessions/pending?device_id=" + DEVICE_ID);
  // int code = http.GET();
  // if (code == 200) {
  //   StaticJsonDocument<512> doc;
  //   deserializeJson(doc, http.getString());
  //   if (!doc.isNull() && doc.containsKey("id")) {
  //     return String((const char*)doc["id"]);
  //   }
  // }
  // http.end();
  return "";  // TODO: implement per above once merged into real file
}

// Captures CAPTURE_SAMPLES readings from the AS7341, averages them, returns
// a JSON object with keys matching spectral_match.py's CHANNELS list exactly:
// F1..F8, CLEAR, NIR.
bool captureAveragedReading(StaticJsonDocument<512>& out) {
  long sums[10] = {0};  // F1..F8, CLEAR, NIR
  const char* keys[10] = {"F1","F2","F3","F4","F5","F6","F7","F8","CLEAR","NIR"};

  for (int i = 0; i < CAPTURE_SAMPLES; i++) {
    // TODO Claude Code: replace with the real AS7341 read call already used
    // in esp32_sensor.ino (likely as7341.readAllChannels(readings) via the
    // Adafruit_AS7341 library, matching the existing UREA_CHANNEL_IDX /
    // CREATININE_CHANNEL_IDX constants already in that file).
    // uint16_t readings[12];
    // if (!as7341.readAllChannels(readings)) return false;
    // sums[0]+=readings[0]; sums[1]+=readings[1]; ... map indices correctly,
    // the AS7341 channel order from readAllChannels is NOT the same order
    // as F1..F8,Clear,NIR -- double check against the Adafruit_AS7341
    // channel enum before assuming index order.
    delay(CAPTURE_SAMPLE_GAP_MS);
  }

  for (int i = 0; i < 10; i++) {
    out[keys[i]] = sums[i] / (float)CAPTURE_SAMPLES;
  }
  return true;
}

bool postSessionComplete(const String& sessionId, StaticJsonDocument<512>& channels) {
  // HTTPClient http;
  // http.begin(String(BACKEND_HOST) + "/api/reading-sessions/" + sessionId + "/complete");
  // http.addHeader("Content-Type", "application/json");
  // StaticJsonDocument<512> body;
  // body["raw_channels"] = channels;
  // String payload; serializeJson(body, payload);
  // int code = http.PATCH(payload);
  // http.end();
  // return code == 200;
  return false;  // TODO: implement per above
}

void postSessionFailed(const String& sessionId, const String& errorMsg) {
  // similar PATCH to /api/reading-sessions/{id}/fail with {"error": errorMsg}
  // TODO: implement
}

// ---------------------------------------------------------------------------
// Non-blocking state machine -- call this every loop() iteration.
// Deliberately non-blocking (uses millis(), not delay()) so WiFi/other
// housekeeping in the rest of loop() still runs during the 5s window.
// ---------------------------------------------------------------------------
void callReadingStateMachine() {
  unsigned long now = millis();

  switch (triggerState) {

    case TS_IDLE: {
      if (now - lastPollAt >= POLL_INTERVAL_MS) {
        lastPollAt = now;
        String sid = pollForPendingSession();
        if (sid.length() > 0) {
          currentSessionId = sid;
          ledLightBlue();
          stateEnteredAt = now;
          triggerState = TS_ACKNOWLEDGED;
        }
      }
      break;
    }

    case TS_ACKNOWLEDGED: {
      // LED is on, this is the 5-second "get ready / strip developing" window
      if (now - stateEnteredAt >= READING_WINDOW_MS) {
        triggerState = TS_CAPTURING;
      }
      break;
    }

    case TS_CAPTURING: {
      StaticJsonDocument<512> channels;
      bool ok = captureAveragedReading(channels);
      if (ok) {
        ok = postSessionComplete(currentSessionId, channels);
      } else {
        postSessionFailed(currentSessionId, "AS7341 read failed");
      }
      lastResultOk = ok;
      if (ok) ledSuccess(); else ledFailure();
      stateEnteredAt = now;
      triggerState = TS_RESULT_FLASH;
      break;
    }

    case TS_RESULT_FLASH: {
      if (now - stateEnteredAt >= LED_RESULT_FLASH_MS) {
        ledOff();
        currentSessionId = "";
        triggerState = TS_IDLE;
      }
      break;
    }
  }
}

// TODO Claude Code: in setup(), add pinMode(STATUS_LED_PIN, OUTPUT); ledOff();
// TODO Claude Code: in loop(), add a call to callReadingStateMachine();
//      alongside whatever else the existing loop() already does.
