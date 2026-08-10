/*
 * Novera ESP32 sensor node
 * -------------------------
 * Wireless, standalone: connects to WiFi and POSTs readings straight to the
 * live backend (POST /api/readings) — no laptop, USB cable, or browser
 * involved once it's flashed and on your network. The endpoint already
 * accepts a partial JSON body ({ph, creatinine, urea, temperature}) and
 * falls back to its own randomized values for any field left out
 * (backend/app/routers/readings.py), so this sketch works unmodified today.
 *
 * DUMMY MODE (current): readPH()/readCreatinine()/readUrea()/
 * readTemperature() below return plausible random values inside the same
 * reference bands the dashboard uses (frontend/src/lib/format.js), purely
 * so the whole pipeline — WiFi -> HTTPS POST -> dashboard -> AI report/
 * voice/self-care — can be exercised end-to-end with a bare ESP32, no
 * sensors wired up yet.
 *
 * ON-DEMAND SAMPLES: every PING_INTERVAL_MS this also POSTs a tiny
 * heartbeat to /api/device/ping with our SSID, and gets back whether the
 * dashboard's "Take New Sample" button was clicked. If so, it takes and
 * sends a reading immediately instead of waiting for the next
 * SEND_INTERVAL_MS tick. This is also what powers the dashboard's
 * connected/offline + SSID display — the backend infers "online" purely
 * from how recently a ping landed.
 *
 * SWITCHING TO REAL SENSORS LATER: replace the body of each read*()
 * function with the real sensor read (analogRead(PIN), a sensor library
 * call, etc.) and return the same units the dashboard expects — pH
 * (unitless), creatinine (mg/dL), urea (mg/dL), temperature (°C). Nothing
 * else in this sketch, or on the website, needs to change.
 *
 * SETUP
 * 1. Arduino IDE -> Preferences -> Additional Board Manager URLs, add:
 *    https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
 * 2. Boards Manager -> install "esp32" (Espressif Systems).
 * 3. Select your board (e.g. "ESP32 Dev Module") and its port.
 * 4. Fill in WIFI_SSID_1/WIFI_PASSWORD_1 (and _2, _3, ... for any extra
 *    networks, e.g. a phone hotspot) below.
 * 5. Upload. Open Serial Monitor at 115200 baud to watch it connect and
 *    POST — a new reading should appear on the Dashboard within a few
 *    seconds of boot, and again every SEND_INTERVAL_MS after that.
 *
 * No extra libraries to install — WiFi.h, WiFiClientSecure.h, and
 * HTTPClient.h all ship with the ESP32 board package from step 2.
 */

#include <WiFi.h>
#include <WiFiMulti.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ---- fill these in ----
// Add every network you want it to try (home WiFi, phone hotspot, ...) —
// on each connect attempt it scans and joins whichever of these is in
// range, preferring the strongest signal if more than one is available.
WiFiMulti wifiMulti;
const char *WIFI_SSID_1 = "YOUR_WIFI_SSID";
const char *WIFI_PASSWORD_1 = "YOUR_WIFI_PASSWORD";
const char *WIFI_SSID_2 = "YOUR_HOTSPOT_SSID";
const char *WIFI_PASSWORD_2 = "YOUR_HOTSPOT_PASSWORD";

const char *API_URL = "https://api.echo-nova.online/api/readings";
const char *PING_URL = "https://api.echo-nova.online/api/device/ping";

// How often to push a new reading on its own, with no request from the
// dashboard. Real sensors could read continuously and send on a shorter
// interval; 5 minutes is a sane default for a demo.
const unsigned long SEND_INTERVAL_MS = 5UL * 60UL * 1000UL;

// How often to heartbeat the backend (reports our SSID, and checks whether
// the dashboard's "Take New Sample" button asked for a reading right now).
const unsigned long PING_INTERVAL_MS = 3UL * 1000UL;

// ---- dummy sensor reads — see header comment for how to swap these for
// real sensors later. Ranges match the dashboard's own reference bands. ----
float randomFloat(float lo, float hi) {
  return lo + (hi - lo) * ((float)random(0, 10001) / 10000.0f);
}
float readPH() { return randomFloat(6.2f, 7.6f); }
float readCreatinine() { return randomFloat(0.6f, 1.3f); }
float readUrea() { return randomFloat(7.0f, 20.0f); }
float readTemperature() { return randomFloat(36.1f, 37.2f); }

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("Connecting to WiFi");
  // wifiMulti.run() scans for all added APs and joins whichever is in
  // range (strongest first), so this one call covers "home WiFi or
  // hotspot, whichever is available right now".
  if (wifiMulti.run(20000) == WL_CONNECTED) {
    Serial.print("\nConnected to ");
    Serial.print(WiFi.SSID());
    Serial.print(", IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi connect timed out, will retry in loop()");
  }
}

void sendReading() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected, skipping this send");
    return;
  }

  // Read each sensor once and hold the values so what's printed to Serial
  // is exactly what gets sent — not a second, independently-drawn sample.
  float ph = readPH();
  float creatinine = readCreatinine();
  float urea = readUrea();
  float temperature = readTemperature();

  char body[160];
  snprintf(body, sizeof(body),
           "{\"ph\":%.2f,\"creatinine\":%.2f,\"urea\":%.1f,\"temperature\":%.1f}",
           ph, creatinine, urea, temperature);

  Serial.print("Reading -> ");
  Serial.println(body);

  WiFiClientSecure client;
  // Demo-only: skips TLS certificate verification. Fine for a research
  // prototype hitting a fixed, known host; if you care about pinning the
  // cert for production hardware, replace this with client.setCACert(...).
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

// Heartbeats the backend with our current SSID and asks whether the
// dashboard's "Take New Sample" button has requested a reading. Returns
// true if it has (the caller should take + send a reading right away).
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
  randomSeed(analogRead(0) ^ micros());
  WiFi.mode(WIFI_STA);
  wifiMulti.addAP(WIFI_SSID_1, WIFI_PASSWORD_1);
  wifiMulti.addAP(WIFI_SSID_2, WIFI_PASSWORD_2);
  connectWiFi();
  sendReading(); // one immediately on boot so you see it working right away
  lastSendAt = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (millis() - lastPingAt >= PING_INTERVAL_MS) {
    lastPingAt = millis();
    if (checkPendingSample()) {
      Serial.println("Dashboard requested a sample -- taking one now.");
      sendReading();
      lastSendAt = millis(); // don't also fire the periodic send right after
    }
  }

  if (millis() - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = millis();
    sendReading();
  }
}
