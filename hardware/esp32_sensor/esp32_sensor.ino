/*
 * Novera ESP32 sensor node
 * -------------------------
 * Wireless, standalone: connects to WiFi and POSTs readings straight to the
 * live backend (POST /api/readings) — no laptop, USB cable, or browser
 * involved once it's flashed and on your network.
 *
 * REAL SENSORS (as of this version):
 * - Temperature: DHT11, real reading (humidity is also read but not sent —
 *   the backend's reading shape has no humidity field yet).
 * - pH / Urea / Creatinine: AS7341 spectral color sensor reading 3
 *   colorimetric reagent pads on a single test strip, one at a time. Only
 *   one AS7341 exists, so the strip is slid BY HAND under the sensor
 *   through 3 marked positions — the firmware watches the sensor and
 *   auto-captures each pad once its reading stabilizes (no button needed).
 * - MQ gas sensor: wired for power only (no signal pin connected), purely
 *   so its onboard LED lights up. Not read, not sent anywhere.
 *
 * DUMMY FALLBACK: if the AS7341 isn't responding, a pad times out (no strip
 * presented), or the DHT11 read fails, that specific value falls back to a
 * plausible random number in its reference range instead of blocking the
 * send — a reading always goes out every cycle. Serial prints which fields
 * (if any) were dummy for that cycle, e.g. "pH: using dummy value."
 *
 * IMPORTANT — NOT REAL CALIBRATION YET: turning a raw color reading into an
 * actual mg/dL or pH number requires a calibration curve built from testing
 * known-concentration reference solutions against the pads. That hasn't
 * been done yet, so mapRawToRange() below just linearly stretches a raw
 * sensor value between two guessed endpoints onto the reference band. This
 * is a placeholder for demo purposes ONLY — the numbers it produces are not
 * scientifically valid until real calibration data replaces the guessed
 * RAW_MIN/RAW_MAX endpoints. Say so out loud in any demo.
 *
 * WIRING (as connected):
 *   DHT11   VCC->3V3  GND->GND  DATA->D4 (+ pull-up resistor to 3V3)
 *   AS7341  VIN->3V3  GND->GND  SCL->D22  SDA->D21
 *   MQ gas  VCC->VIN(5V, USB power only)  GND->GND  (no signal pin wired)
 *   Status LED: the board's onboard LED (GPIO2) — no extra wiring. Lit
 *   whenever WiFi is connected, off otherwise.
 *
 * LIBRARIES NEEDED (Arduino Library Manager):
 *   - "DHT sensor library" by Adafruit (+ its dependency "Adafruit Unified Sensor")
 *   - "Adafruit AS7341" by Adafruit
 *   (WiFi.h / WiFiClientSecure.h / HTTPClient.h / Wire.h ship with the ESP32
 *   board package already.)
 *
 * BEFORE FIRST UPLOAD — VERIFY THIS ONE THING:
 *   readAllChannels() below assumes the Adafruit_AS7341 library fills its
 *   array as [F1,F2,F3,F4,F5,F6,F7,F8,Clear,NIR] (10 values, CLEAR_IDX=8).
 *   This has been the layout across recent library versions, but library
 *   updates can change it. Open File -> Examples -> Adafruit AS7341 ->
 *   as7341 in the Arduino IDE and check its channel-printing example
 *   against this file's CLEAR_IDX/NIR_IDX before trusting real readings.
 */

#include <WiFi.h>
#include <WiFiMulti.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <DHT.h>
#include <Adafruit_AS7341.h>

// ---- WiFi networks — fill in / adjust as needed ----
WiFiMulti wifiMulti;
const char *WIFI_SSID_1 = "Zuhaib";
const char *WIFI_PASSWORD_1 = "zuhaib2006";
const char *WIFI_SSID_2 = "YOUR_HOTSPOT_SSID";
const char *WIFI_PASSWORD_2 = "YOUR_HOTSPOT_PASSWORD";

const char *API_URL = "https://api.echo-nova.online/api/readings";
const char *PING_URL = "https://api.echo-nova.online/api/device/ping";

// How often to run a full test cycle on its own, with no request from the
// dashboard (assumes a strip is available to insert when it fires).
const unsigned long SEND_INTERVAL_MS = 5UL * 60UL * 1000UL;
// How often to heartbeat the backend / check for a dashboard-requested sample.
const unsigned long PING_INTERVAL_MS = 3UL * 1000UL;

// ---- Status LED — onboard LED, no extra wiring needed ----
// Lights up whenever WiFi is connected, off otherwise: a simple "device is
// alive and online" indicator, visible without opening Serial Monitor.
#define STATUS_LED_PIN 2

// ---- DHT11 ----
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// ---- AS7341 ----
Adafruit_AS7341 as7341;
const int AS7341_CHANNEL_COUNT = 10; // F1..F8, Clear, NIR
const int CLEAR_IDX = 8;             // index of the "Clear" channel — VERIFY, see header comment
const int NIR_IDX = 9;               // index of the "NIR" channel
const uint16_t LED_CURRENT_MA = 10;  // conservative onboard-LED brightness

// Representative channel per pad — rough starting picks, not tuned yet:
//  - pH / urea pads: dyes that shift across the visible spectrum -> use the
//    Clear channel (overall reflected brightness) as a first approximation.
//  - creatinine pad: Jaffe reaction turns orange/red -> F6 (~590nm, amber)
//    channel index is 5 (F1=0 ... F6=5) — should track that color shift.
const int PH_CHANNEL_IDX = CLEAR_IDX;
const int UREA_CHANNEL_IDX = CLEAR_IDX;
const int CREATININE_CHANNEL_IDX = 5; // F6

// Reference bands the dashboard expects (same ones the old dummy code used).
const float PH_LO = 6.2f, PH_HI = 7.6f;
const float CREATININE_LO = 0.6f, CREATININE_HI = 1.3f;
const float UREA_LO = 7.0f, UREA_HI = 20.0f;
const float TEMP_LO = 36.1f, TEMP_HI = 37.2f;

// Fallback for whenever a real sensor isn't responding / a pad isn't
// captured in time — returns a plausible random value in-range instead of
// leaving that field blank, so a reading can always be sent. Printed to
// Serial each time it's used so it's obvious in the log which fields (if
// any) were real vs. dummy for that cycle.
float randomFloat(float lo, float hi) {
  return lo + (hi - lo) * ((float)random(0, 10001) / 10000.0f);
}

// ---- PLACEHOLDER calibration endpoints (raw sensor counts) ----
// No real calibration data exists yet (see header comment). These are
// guessed so the pipeline produces *some* number in-range for a demo.
// Replace with real endpoints once you've run trials against known
// reference solutions: note the raw channel value at the lowest and
// highest concentration you test, and put those numbers here instead.
const uint16_t PH_RAW_MIN = 200,          PH_RAW_MAX = 20000;
const uint16_t UREA_RAW_MIN = 200,        UREA_RAW_MAX = 20000;
const uint16_t CREATININE_RAW_MIN = 200,  CREATININE_RAW_MAX = 20000;

float mapRawToRange(uint16_t raw, uint16_t rawMin, uint16_t rawMax, float lo, float hi) {
  if (raw <= rawMin) return lo;
  if (raw >= rawMax) return hi;
  float t = (float)(raw - rawMin) / (float)(rawMax - rawMin);
  return lo + t * (hi - lo);
}

// Last captured values, sent in the next reading.
float lastPH = 0, lastUrea = 0, lastCreatinine = 0, lastTemperature = 0;

// Tracks whether the AS7341 is currently initialized. Adafruit's begin()
// does a real I2C negotiation (bank select, chip-ID register read, etc.) and
// allocates a small internal object on every call — calling it fresh on
// every single test cycle (as the old code did) is unnecessary work, leaks
// a little heap each time over a long-running deployment, and adds more I2C
// traffic than needed, which is more exposure to whatever caused a real
// incident where the sensor stopped responding until it was fully
// power-cycled. Instead: initialize once, keep using it, and only pay for
// re-initialization when a failure is actually observed.
bool as7341Ready = false;

// Ensures the AS7341 is initialized, with a few retries for a transient
// glitch (e.g. a noisy first I2C transaction after power-up). Cached in
// as7341Ready so a healthy sensor is never re-initialized on every cycle —
// see the comment above. Returns false (after retries) if the sensor
// genuinely isn't responding right now; the caller falls back to dummy
// values for that cycle, same as before.
bool ensureAS7341Ready() {
  if (as7341Ready) return true;

  const int MAX_ATTEMPTS = 3;
  const unsigned long RETRY_DELAY_MS = 400;
  for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    if (as7341.begin()) {
      as7341Ready = true;
      if (attempt > 1) {
        Serial.print("AS7341 initialized on retry attempt ");
        Serial.println(attempt);
      }
      return true;
    }
    if (attempt < MAX_ATTEMPTS) {
      Serial.print("AS7341 init attempt ");
      Serial.print(attempt);
      Serial.println(" failed, retrying...");
      delay(RETRY_DELAY_MS);
    }
  }
  Serial.println("AS7341 not responding after retries — check wiring/power (SDA=D21, SCL=D22, VIN=3V3). Using dummy pH/urea/creatinine for this cycle.");
  return false;
}

// Keeps the status LED in sync with the current WiFi state. Call after
// anything that might change connection status (a connect attempt, or a
// drop noticed in loop()).
void updateStatusLED() {
  digitalWrite(STATUS_LED_PIN, WiFi.status() == WL_CONNECTED ? HIGH : LOW);
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    updateStatusLED();
    return;
  }
  Serial.print("Connecting to WiFi");
  if (wifiMulti.run(20000) == WL_CONNECTED) {
    Serial.print("\nConnected to ");
    Serial.print(WiFi.SSID());
    Serial.print(", IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi connect timed out, will retry in loop()");
  }
  updateStatusLED();
}

// Reads all AS7341 channels once. Returns false (and leaves out[] untouched)
// if the sensor didn't respond — caller should treat that as "try again",
// never as a zero reading.
bool readAS7341Once(uint16_t out[AS7341_CHANNEL_COUNT]) {
  return as7341.readAllChannels(out);
}

// Slides through one pad position: polls the sensor until a run of readings
// on the representative channel stops changing much (the strip has stopped
// moving and a pad is sitting under the sensor) AND the Clear channel shows
// something is actually there (not just "sensor pointed at empty air").
// Returns true and fills outRaw with the stable channel array, or false on
// timeout (no strip presented in time — caller should skip this cycle).
bool captureStablePad(const char *promptLabel, uint16_t outRaw[AS7341_CHANNEL_COUNT], unsigned long timeoutMs) {
  Serial.print("Slide the strip so the ");
  Serial.print(promptLabel);
  Serial.println(" pad sits under the sensor and hold it there...");

  const int WINDOW = 5;
  const uint16_t PRESENCE_MIN_CLEAR = 300;  // "something is under the sensor"
  const uint16_t STABLE_MAX_SPREAD = 150;   // max-min allowed across the window to call it "settled"

  uint16_t history[WINDOW][AS7341_CHANNEL_COUNT];
  int filled = 0;
  unsigned long start = millis();
  unsigned long lastSample = 0;

  while (millis() - start < timeoutMs) {
    if (millis() - lastSample < 150) {
      delay(10); // yield so WiFi/system background tasks run — a tight busy-wait
                 // loop here can starve them and trigger the ESP32 watchdog reset
      continue;
    }
    lastSample = millis();

    uint16_t reading[AS7341_CHANNEL_COUNT];
    if (!readAS7341Once(reading)) {
      delay(10);
      continue; // sensor hiccup, try again next tick
    }

    for (int i = 0; i < WINDOW - 1; i++) {
      memcpy(history[i], history[i + 1], sizeof(history[i]));
    }
    memcpy(history[WINDOW - 1], reading, sizeof(reading));
    if (filled < WINDOW) filled++;

    if (filled == WINDOW) {
      uint16_t mn = 65535, mx = 0;
      for (int i = 0; i < WINDOW; i++) {
        uint16_t v = history[i][CLEAR_IDX];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      bool present = mx > PRESENCE_MIN_CLEAR;
      bool stable = (mx - mn) < STABLE_MAX_SPREAD;
      if (present && stable) {
        memcpy(outRaw, history[WINDOW - 1], sizeof(reading));
        Serial.print(promptLabel);
        Serial.println(" pad captured.");
        return true;
      }
    }
  }
  Serial.print(promptLabel);
  Serial.println(" pad timed out — no strip detected in time.");
  return false;
}

// Runs the full 3-pad sequence + DHT11 read. Always returns true — any
// sensor/pad that fails or times out falls back to a dummy random value in
// its reference range instead of blocking the send, so a reading always
// goes out. Check Serial output to see which fields (if any) were dummy
// for a given cycle.
bool runFullTest() {
  bool as7341Ok = ensureAS7341Ready();
  if (as7341Ok) {
    as7341.setLEDCurrent(LED_CURRENT_MA);
    as7341.enableLED(true);
  }

  uint16_t phRaw[AS7341_CHANNEL_COUNT];
  bool phCaptured = as7341Ok && captureStablePad("pH", phRaw, 60000);
  if (phCaptured) {
    lastPH = mapRawToRange(phRaw[PH_CHANNEL_IDX], PH_RAW_MIN, PH_RAW_MAX, PH_LO, PH_HI);
  } else {
    Serial.println("pH: using dummy value.");
    lastPH = randomFloat(PH_LO, PH_HI);
  }

  uint16_t ureaRaw[AS7341_CHANNEL_COUNT];
  bool ureaCaptured = as7341Ok && captureStablePad("Urea", ureaRaw, 60000);
  if (ureaCaptured) {
    lastUrea = mapRawToRange(ureaRaw[UREA_CHANNEL_IDX], UREA_RAW_MIN, UREA_RAW_MAX, UREA_LO, UREA_HI);
  } else {
    Serial.println("Urea: using dummy value.");
    lastUrea = randomFloat(UREA_LO, UREA_HI);
  }

  uint16_t creatinineRaw[AS7341_CHANNEL_COUNT];
  bool creatinineCaptured = as7341Ok && captureStablePad("Creatinine", creatinineRaw, 60000);
  if (creatinineCaptured) {
    lastCreatinine = mapRawToRange(creatinineRaw[CREATININE_CHANNEL_IDX], CREATININE_RAW_MIN, CREATININE_RAW_MAX, CREATININE_LO, CREATININE_HI);
  } else {
    Serial.println("Creatinine: using dummy value.");
    lastCreatinine = randomFloat(CREATININE_LO, CREATININE_HI);
  }

  if (as7341Ok) as7341.enableLED(false);

  // The sensor initialized fine this cycle but every single pad capture
  // still failed — that pattern means it most likely dropped off the bus
  // *after* init (a power blip, a jostled wire), not that a pad was simply
  // never presented in time. Clear the ready flag so the next cycle
  // re-runs ensureAS7341Ready() instead of trusting a connection that
  // isn't actually there anymore — this is the automatic-recovery path.
  if (as7341Ok && !phCaptured && !ureaCaptured && !creatinineCaptured) {
    Serial.println("AS7341 stopped responding after init — will re-initialize next cycle.");
    as7341Ready = false;
  }

  float h = dht.readHumidity();       // read but not sent (no backend field yet)
  float t = dht.readTemperature();    // Celsius
  if (isnan(t)) {
    Serial.println("Temperature: DHT11 read failed, using dummy value.");
    lastTemperature = randomFloat(TEMP_LO, TEMP_HI);
  } else {
    lastTemperature = t;
    Serial.print("DHT11 -> temp: ");
    Serial.print(t);
    Serial.print(" C, humidity: ");
    Serial.print(h);
    Serial.println(" % (humidity not sent)");
  }

  return true;
}

void sendReading() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected, skipping this send");
    return;
  }

  if (!runFullTest()) {
    Serial.println("Test cycle incomplete — not sending.");
    return;
  }

  char body[160];
  snprintf(body, sizeof(body),
           "{\"ph\":%.2f,\"creatinine\":%.2f,\"urea\":%.1f,\"temperature\":%.1f}",
           lastPH, lastCreatinine, lastUrea, lastTemperature);

  Serial.print("Reading -> ");
  Serial.println(body);

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  if (!http.begin(client, API_URL)) {
    Serial.println("HTTPClient begin() failed");
    return;
  }
  http.addHeader("Content-Type", "application/json");

  int status = http.POST((uint8_t *)body, strlen(body));
  Serial.print("POST /api/readings -> ");
  Serial.println(status);
  if (status > 0) {
    Serial.println(http.getString());
  } else {
    Serial.print("Request failed: ");
    Serial.println(http.errorToString(status));
  }
  http.end();
}

bool checkPendingSample() {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  if (!http.begin(client, PING_URL)) return false;
  http.addHeader("Content-Type", "application/json");

  char body[96];
  snprintf(body, sizeof(body), "{\"ssid\":\"%s\"}", WiFi.SSID().c_str());

  int status = http.POST((uint8_t *)body, strlen(body));
  bool pending = false;
  if (status > 0) {
    String resp = http.getString();
    pending = resp.indexOf("\"pending_sample\":true") != -1;
  }
  http.end();
  return pending;
}

unsigned long lastSendAt = 0;
unsigned long lastPingAt = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  randomSeed(analogRead(0) ^ micros()); // so dummy fallback values differ each boot

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW); // off until WiFi actually connects

  Wire.begin(21, 22); // SDA, SCL — matches the wiring notes above
  dht.begin();
  // AS7341 init is lazy (see ensureAS7341Ready() below) — it happens on the
  // first real test cycle, triggered by sendReading() a few lines down, not
  // here. Calling as7341.begin() here too would just be a second redundant
  // init on every boot for no benefit.

  WiFi.mode(WIFI_STA);
  wifiMulti.addAP(WIFI_SSID_1, WIFI_PASSWORD_1);
  wifiMulti.addAP(WIFI_SSID_2, WIFI_PASSWORD_2);
  connectWiFi();

  sendReading(); // will prompt for the strip over Serial if WiFi connected
  lastSendAt = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    updateStatusLED(); // catches a drop the instant it's noticed, not just after a reconnect attempt
    connectWiFi();
  }

  if (millis() - lastPingAt >= PING_INTERVAL_MS) {
    lastPingAt = millis();
    if (checkPendingSample()) {
      Serial.println("Dashboard requested a sample -- starting test now.");
      sendReading();
      lastSendAt = millis();
    }
  }

  if (millis() - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = millis();
    sendReading();
  }
}
