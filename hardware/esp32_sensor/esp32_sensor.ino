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
 * 4. Fill in WIFI_SSID / WIFI_PASSWORD below.
 * 5. Upload. Open Serial Monitor at 115200 baud to watch it connect and
 *    POST — a new reading should appear on the Dashboard within a few
 *    seconds of boot, and again every SEND_INTERVAL_MS after that.
 *
 * No extra libraries to install — WiFi.h, WiFiClientSecure.h, and
 * HTTPClient.h all ship with the ESP32 board package from step 2.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ---- fill these in ----
const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char *API_URL = "https://api.echo-nova.online/api/readings";

// How often to push a new reading. Real sensors could read continuously
// and send on a shorter interval; 5 minutes is a sane default for a demo.
const unsigned long SEND_INTERVAL_MS = 5UL * 60UL * 1000UL;

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
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\nConnected, IP: ");
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

  char body[160];
  snprintf(body, sizeof(body),
           "{\"ph\":%.2f,\"creatinine\":%.2f,\"urea\":%.1f,\"temperature\":%.1f}",
           readPH(), readCreatinine(), readUrea(), readTemperature());

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

unsigned long lastSendAt = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  randomSeed(analogRead(0) ^ micros());
  connectWiFi();
  sendReading(); // one immediately on boot so you see it working right away
  lastSendAt = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (millis() - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = millis();
    sendReading();
  }
}
