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
 * - pH / Urea / Creatinine: AS7341 spectral color sensor reading TWO
 *   colorimetric reagent pads on a single test strip, one after another.
 *   Top pad = Creatinine (Jaffe reaction: pinkish at normal levels,
 *   shifting reddish as it rises). Bottom pad = Urea AND pH together, from
 *   the SAME capture (yellowish-green at normal, shifting blueish-green as
 *   urea rises). Only one AS7341 exists, so the strip is slid BY HAND to
 *   the second pad position between the two capture windows.
 * - MQ gas sensor: wired for power only (no signal pin connected), purely
 *   so its onboard LED lights up. Not read, not sent anywhere.
 * - TFT display (240x320 SPI, ILI9341-compatible, added 2026-08-24):
 *   patient-facing status only, landscape orientation, plain white text on
 *   black. On boot: blinks the screen white twice, then "NOVERA" /
 *   "Starting...", then "Ready", then settles into idle "NOVERA" — see
 *   runBootSequence(). After boot: idle "NOVERA", the patient's name while
 *   their requested test is running (dashboard/WhatsApp arm flow only —
 *   see WIRING below and showTestingScreen()), then "Thank you, <name>"
 *   for a few seconds after the send completes. The periodic un-requested
 *   auto-cycle (SEND_INTERVAL_MS) has no associated patient, so it
 *   deliberately does NOT touch the display — see loop().
 *
 * CALIBRATION HAPPENS ON THE BACKEND, NOT HERE: this firmware's only job is
 * to capture the two pads' raw AS7341 channels (F1..F8, Clear, NIR) as
 * accurately as it can and send both raw channel sets to
 * POST /api/readings. Turning those raw colors into an actual pH/mg-dL
 * number — converting to an RGB/hex color and matching it against a
 * calibration chart — is backend/app/core/color_calibration.py's job.
 * Keeping that math off the device matches how every other piece of
 * NOVERA's decision logic already works (scoring.py, screening_llm.py):
 * no math on the ESP32, easier to update calibration data without
 * reflashing firmware. Nothing in color_calibration.py is real lab data
 * yet either — see that file's own header comment.
 *
 * CAPTURE TIMING: a full color capture is two fixed 2.5-second windows
 * (not stability-detected like earlier versions of this file) — the
 * onboard reagent LED and the external "ready" LED (GPIO13) are both on
 * throughout each window, off briefly between them as the signal to
 * reposition the strip to the second pad. See runFullTest().
 *
 * DUMMY FALLBACK: if the AS7341 isn't responding at all, or neither
 * capture window gets a single successful read, this cycle sends
 * temperature only (no raw_channels fields) — the backend's existing
 * jitter-based fallback fills in a plausible ph/urea/creatinine, same
 * fallback path a totally sensorless reading has always used.
 *
 * WIRING (as connected):
 *   DHT11   VCC->3V3  GND->GND  DATA->D4 (+ pull-up resistor to 3V3)
 *   AS7341  VIN->3V3  GND->GND  SCL->D22  SDA->D21
 *   MQ gas  VCC->VIN(5V, USB power only)  GND->GND  (no signal pin wired)
 *   Status LED: the board's onboard LED (GPIO2) — no extra wiring. Lit
 *   whenever WiFi is connected, off otherwise.
 *   Ready LED ("blue LED"): external LED on GPIO13 -> LED anode; LED
 *   cathode -> a 220-330 ohm resistor -> GND. The resistor is required —
 *   an LED wired directly to a GPIO with nothing else in series has no
 *   current limiting and risks burning out either the LED or the pin.
 *   Steady on whenever armed (WiFi connected + AS7341 initialized); during
 *   a capture cycle it instead tracks the two capture windows (on with the
 *   reagent LED for each 2.5s window, briefly off between them), then
 *   returns to steady-on afterward.
 *   TFT display: VCC->3V3  GND->GND  CS->D5  RST->D26  DC->D27
 *   SCK->D18  MOSI->D23  MISO->D19 (VSPI's fixed hardware pins on this
 *   board — wired straight to the module, nothing to configure in code for
 *   them). LED/backlight: either straight to 3V3 if your module ties it
 *   permanently on, or D27 if your module breaks out a separate backlight
 *   pin (not switched by this firmware either way — always-on backlight).
 *   VCC: most 240x320 ILI9341 breakout modules are 3.3V-logic (check yours
 *   before assuming) — 3V3 is the safe default since the ESP32's own GPIOs
 *   are 3.3V logic regardless of what the module accepts.
 *   Current budget note: the AS7341 (+ its capture LED), DHT11, and this
 *   display's backlight all share the same 3.3V rail as everything above —
 *   fine for essentially every small SPI TFT's typical backlight draw, but
 *   if you see brownout resets during a capture (WiFi TX is already the
 *   single biggest current spike on this board), power the display from a
 *   separate 3.3V source rather than assuming the onboard regulator alone.
 *
 * LIBRARIES NEEDED (Arduino Library Manager):
 *   - "DHT sensor library" by Adafruit (+ its dependency "Adafruit Unified Sensor")
 *   - "Adafruit AS7341" by Adafruit
 *   - "Adafruit ILI9341" by Adafruit (+ its dependency "Adafruit GFX Library")
 *   (WiFi.h / WiFiClientSecure.h / HTTPClient.h / Wire.h / SPI.h ship with
 *   the ESP32 board package already.)
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
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>

// ---- WiFi networks — fill in / adjust as needed ----
WiFiMulti wifiMulti;
const char *WIFI_SSID_1 = "Novera Product 1";
const char *WIFI_PASSWORD_1 = "zuhaib2006";
const char *WIFI_SSID_2 = "king hamza";
const char *WIFI_PASSWORD_2 = "12345678";

const char *API_URL = "https://api.novera.fun/api/readings";
const char *PING_URL = "https://api.novera.fun/api/device/ping";

// How often to run a full test cycle on its own, with no request from the
// dashboard (assumes a strip is available to insert when it fires).
const unsigned long SEND_INTERVAL_MS = 5UL * 60UL * 1000UL;
// How often to heartbeat the backend / check for a dashboard-requested sample.
// Tightened from 3s (2026-08-20): the "get ready" blink cue is supposed to
// land ~1s after the patient receives the WhatsApp/dashboard message telling
// them to test now, but the device can only learn about a request by polling
// (see this file's header) — so the real-world gap is [this interval,
// this interval + REQUEST_CUE_DELAY_MS]. At 3s that could be up to 4s late;
// at 1s it's bounded much closer to the intended ~1s.
const unsigned long PING_INTERVAL_MS = 1UL * 1000UL;

// ---- Status LED — onboard LED, no extra wiring needed ----
// Lights up whenever WiFi is connected, off otherwise: a simple "device is
// alive and online" indicator, visible without opening Serial Monitor.
#define STATUS_LED_PIN 2

// ---- Ready LED — external, needs a series resistor (see header comment) ----
// Steady on whenever armed (WiFi connected + AS7341 initialized). During a
// capture cycle, runFullTest() takes it over directly to track the two
// capture windows instead — see there.
#define READY_LED_PIN 13

// ---- DHT11 ----
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// ---- TFT display (240x320 SPI, ILI9341-compatible) — see header comment
// for full wiring. SCK/MOSI/MISO are VSPI's fixed hardware pins on this
// board (18/23/19) — defined here too (not just wired) so setup() can pass
// them to SPI.begin() explicitly; leaving that implicit occasionally left
// the display blank-but-backlit on some ESP32 core / Adafruit_ILI9341
// version combinations even with correct wiring.
#define TFT_CS   5
#define TFT_DC   27
#define TFT_RST  26
#define TFT_SCK  18
#define TFT_MOSI 23
#define TFT_MISO 19
Adafruit_ILI9341 tft = Adafruit_ILI9341(TFT_CS, TFT_DC, TFT_RST);
#define TFT_THANK_YOU_MS 4000UL // how long "Thank you, <name>" stays up before returning to idle

// ---- Buzzer (added 2026-08-25) — either leg of a bare 2-pin piezo, or the
// I/O pin of a 3-pin buzzer module (VCC->3V3, GND->GND, I/O->this pin).
// Beeps once when an on-demand (dashboard/WhatsApp-requested) test finishes
// — see buzzTestComplete() (defined further down, after AS7341_CHANNEL_
// COUNT below — a function defined THIS early in the file shifts where
// Arduino's auto-generated prototypes land, which broke every later
// function using AS7341_CHANNEL_COUNT in its own signature; found by
// actually hitting that build error) and its call site in loop().
// Deliberately does NOT beep for the periodic un-requested auto-cycle, same
// scoping as the TFT testing/thank-you screens.
#define BUZZER_PIN 14
#define BUZZER_FREQ_HZ 2000
#define BUZZER_DURATION_MS 200

// ---- AS7341 ----
Adafruit_AS7341 as7341;
const int AS7341_CHANNEL_COUNT = 10; // F1..F8, Clear, NIR
const int CLEAR_IDX = 8;             // index of the "Clear" channel — VERIFY, see header comment
const int NIR_IDX = 9;               // index of the "NIR" channel
const uint16_t LED_CURRENT_MA = 10;  // conservative onboard-LED brightness

// "Is anything under the sensor" threshold — informational only (see
// captureAveragedWindow()). The backend's calibration-chart distance check
// is the real "don't trust this reading" backstop, not this firmware.
const uint16_t PRESENCE_MIN_CLEAR = 300;

// Each color capture is a FIXED window, not stability-detected — the user
// repositions the strip during the brief gap between the two windows (see
// runFullTest()). Samples are taken every CAPTURE_SAMPLE_GAP_MS and
// averaged across the window to reduce noise (~25 samples per window at
// these defaults).
const unsigned long CAPTURE_WINDOW_MS = 2500;
const unsigned long CAPTURE_SAMPLE_GAP_MS = 100;
// Brief LED-off gap between the two capture windows — the visible signal
// to reposition the strip to the second pad. Short on purpose: the two
// 2.5s windows are the part that must add up to 5s per spec; this gap is
// on top of that, not carved out of it.
const unsigned long TRANSITION_GAP_MS = 600;

// Fallback for the DHT11 only — color-derived values (pH/urea/creatinine)
// have no on-device fallback anymore; see header comment ("DUMMY FALLBACK").
const float TEMP_LO = 36.1f, TEMP_HI = 37.2f;

float randomFloat(float lo, float hi) {
  return lo + (hi - lo) * ((float)random(0, 10001) / 10000.0f);
}

// Last captured raw channels for each pad, and whether both captures
// succeeded this cycle. Sent as-is to the backend for color calibration —
// see header comment.
uint16_t lastTopRaw[AS7341_CHANNEL_COUNT];    // Creatinine pad
uint16_t lastBottomRaw[AS7341_CHANNEL_COUNT]; // Urea/pH pad
bool haveColorReading = false;
float lastTemperature = 0;

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
      updateReadyLED();
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
  Serial.println("AS7341 not responding after retries — check wiring/power (SDA=D21, SCL=D22, VIN=3V3). Skipping color capture this cycle.");
  return false;
}

// ---- TFT screens (2026-08-24) — patient-facing status only, entirely
// separate from the Serial-only diagnostic prints throughout this file.
// Centered text is the only layout need here, so this is a small local
// helper rather than pulling in a text-layout library for one function.
void tftCenterText(const char *text, int y, uint8_t size, uint16_t color) {
  tft.setTextSize(size);
  tft.setTextColor(color, ILI9341_BLACK);
  int16_t x1, y1;
  uint16_t w, h;
  tft.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  tft.setCursor((tft.width() - (int)w) / 2, y);
  tft.print(text);
}

// All screen text is plain white on black (2026-08-25, Hassan's call) — no
// more cyan accent. Y positions below are tuned for LANDSCAPE (240 tall,
// see tft.setRotation(1) in setup()), not portrait.
void showIdleScreen() {
  tft.fillScreen(ILI9341_BLACK);
  tftCenterText("NOVERA", 100, 4, ILI9341_WHITE);
}

void showReadyScreen() {
  tft.fillScreen(ILI9341_BLACK);
  tftCenterText("Ready", 100, 4, ILI9341_WHITE);
}

// Shown while a dashboard/WhatsApp-requested capture is actually running —
// `name` is whatever /device/ping's patient_name returned this cycle; the
// periodic un-requested auto-cycle never calls this (see loop()), so it's
// always non-empty here in practice, but this still degrades sanely to a
// nameless "Testing..." if it's ever missing.
void showTestingScreen(const char *name) {
  tft.fillScreen(ILI9341_BLACK);
  tftCenterText("Testing...", 70, 2, ILI9341_WHITE);
  if (name && name[0]) {
    tftCenterText(name, 140, 3, ILI9341_WHITE);
  }
}

// Shown for TFT_THANK_YOU_MS right after that same capture's send completes,
// then loop() returns the display to showIdleScreen().
void showThankYouScreen(const char *name) {
  tft.fillScreen(ILI9341_BLACK);
  tftCenterText("Thank you", 70, 3, ILI9341_WHITE);
  if (name && name[0]) {
    tftCenterText(name, 140, 3, ILI9341_WHITE);
  }
  tftCenterText("This is a Research Based Screening Device", 190, 1, ILI9341_WHITE);
}

// ---- Boot sequence (2026-08-25): blink white x2, "NOVERA / Starting...",
// "Ready", then settles into the normal showIdleScreen(). Runs once from
// setup(), after tft.begin()/setRotation().
#define TFT_BLINK_ON_MS   200
#define TFT_BLINK_OFF_MS  200
#define TFT_SPLASH_MS     1500
#define TFT_READY_MS      1000

void runBootSequence() {
  for (int i = 0; i < 2; i++) {
    tft.fillScreen(ILI9341_WHITE);
    delay(TFT_BLINK_ON_MS);
    tft.fillScreen(ILI9341_BLACK);
    delay(TFT_BLINK_OFF_MS);
  }

  tft.fillScreen(ILI9341_BLACK);
  tftCenterText("NOVERA", 70, 4, ILI9341_WHITE);
  tftCenterText("Starting...", 140, 2, ILI9341_WHITE);
  delay(TFT_SPLASH_MS);

  showReadyScreen();
  delay(TFT_READY_MS);

  showIdleScreen();
}

// Keeps the status LED in sync with the current WiFi state. Call after
// anything that might change connection status (a connect attempt, or a
// drop noticed in loop()).
void updateStatusLED() {
  digitalWrite(STATUS_LED_PIN, WiFi.status() == WL_CONNECTED ? HIGH : LOW);
}

// Keeps the ready LED in sync with "armed" state (WiFi connected AND the
// AS7341 initialized). Call after anything that might change either half of
// that condition — a WiFi connect/drop, or an as7341Ready transition.
// During a capture cycle, runFullTest() drives the LED directly instead
// (to track the two capture windows) and calls this again afterward to
// restore steady-on.
void updateReadyLED() {
  digitalWrite(READY_LED_PIN, (WiFi.status() == WL_CONNECTED && as7341Ready) ? HIGH : LOW);
}

// "Get ready" cue for an on-demand request (dashboard button or the
// WhatsApp Agent's request_sensor_reading tool) — two quick blinks after a
// brief pause, distinct from the ready LED's normal steady-on "armed" state
// and from the capture-window on/off pattern runFullTest() drives directly.
// Blocking delay()s, same as the existing TRANSITION_GAP_MS pause between
// capture windows below — a single bounded pause here, not a tight
// busy-wait loop, so this doesn't risk starving WiFi/watchdog housekeeping
// the way a polling loop would.
#define REQUEST_CUE_DELAY_MS 1000
#define REQUEST_CUE_BLINK_MS 150

void signalRequestReceived() {
  delay(REQUEST_CUE_DELAY_MS);
  for (int i = 0; i < 2; i++) {
    digitalWrite(READY_LED_PIN, LOW);
    delay(REQUEST_CUE_BLINK_MS);
    digitalWrite(READY_LED_PIN, HIGH);
    delay(REQUEST_CUE_BLINK_MS);
  }
}

void buzzTestComplete() {
  tone(BUZZER_PIN, BUZZER_FREQ_HZ, BUZZER_DURATION_MS);
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    updateStatusLED();
    updateReadyLED();
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
  updateReadyLED();
}

// Reads all AS7341 channels once. Returns false (and leaves out[] untouched)
// if the sensor didn't respond — caller should treat that as "try again",
// never as a zero reading.
//
// BUG FIX (found 2026-08-19): Adafruit_AS7341::readAllChannels() actually
// fills a 12-value buffer, not 10 — [F1,F2,F3,F4,CLEAR,NIR, F5,F6,F7,F8,
// CLEAR,NIR] (it reads the low SMUX config, then the high SMUX config into
// the second half). Passing our 10-element `out` straight to it, as this
// function used to, overflowed the stack array by 4 bytes AND scrambled the
// labels: what got called "F5"/"F6" downstream was really the low-pass
// CLEAR/NIR, "CLEAR"/"NIR" was really the true F7/F8, and the true final
// CLEAR/NIR were dropped entirely. Read into a real 12-wide buffer here and
// remap explicitly so `out` matches its documented [F1..F8,CLEAR,NIR] order.
bool readAS7341Once(uint16_t out[AS7341_CHANNEL_COUNT]) {
  uint16_t raw12[12];
  if (!as7341.readAllChannels(raw12)) return false;
  out[0] = raw12[0];  // F1
  out[1] = raw12[1];  // F2
  out[2] = raw12[2];  // F3
  out[3] = raw12[3];  // F4
  out[4] = raw12[6];  // F5
  out[5] = raw12[7];  // F6
  out[6] = raw12[8];  // F7
  out[7] = raw12[9];  // F8
  out[CLEAR_IDX] = raw12[10]; // CLEAR (high-pass read; low-pass raw12[4] is the same channel, near-identical value)
  out[NIR_IDX] = raw12[11];   // NIR
  return true;
}

// Averages AS7341 readings across a FIXED window — not stability-detected
// like earlier versions of this file, since the physical pad position is
// fixed by the user for the duration of this window, not searched for.
// Returns false only if the AS7341 never responded to a single sample the
// whole window; a low average Clear value (below PRESENCE_MIN_CLEAR) just
// prints a warning and still returns the average — the backend's
// calibration-chart distance check is the authoritative "don't trust this"
// backstop, not this firmware.
bool captureAveragedWindow(const char *label, uint16_t outRaw[AS7341_CHANNEL_COUNT], unsigned long windowMs) {
  uint32_t sums[AS7341_CHANNEL_COUNT] = {0};
  int samples = 0;
  unsigned long start = millis();
  unsigned long lastSample = 0;

  while (millis() - start < windowMs) {
    if (millis() - lastSample < CAPTURE_SAMPLE_GAP_MS) {
      delay(10); // yield so WiFi/system background tasks run — a tight busy-wait
                 // loop here can starve them and trigger the ESP32 watchdog reset
      continue;
    }
    lastSample = millis();

    uint16_t reading[AS7341_CHANNEL_COUNT];
    if (!readAS7341Once(reading)) continue; // sensor hiccup, try again next tick

    for (int i = 0; i < AS7341_CHANNEL_COUNT; i++) sums[i] += reading[i];
    samples++;
  }

  if (samples == 0) {
    Serial.print(label);
    Serial.println(": AS7341 never responded during this window.");
    return false;
  }

  for (int i = 0; i < AS7341_CHANNEL_COUNT; i++) outRaw[i] = sums[i] / samples;

  if (outRaw[CLEAR_IDX] < PRESENCE_MIN_CLEAR) {
    Serial.print(label);
    Serial.println(": low signal — was the strip actually under the sensor?");
  }
  Serial.print(label);
  Serial.print(" captured (");
  Serial.print(samples);
  Serial.println(" samples averaged).");
  return true;
}

// Runs the two-pad color capture (Creatinine top, Urea/pH bottom) + DHT11
// read. Always returns true — a totally failed color capture just means
// this cycle's send omits the raw_channels fields (backend fallback takes
// over, see header comment); it never blocks the send outright.
bool runFullTest() {
  bool as7341Ok = ensureAS7341Ready();
  // ensureAS7341Ready() only calls updateReadyLED() on a fresh init — once
  // as7341Ready is already true it short-circuits without touching the LED,
  // so this re-asserts "armed" explicitly at the start of every cycle.
  updateReadyLED();

  bool topOk = false, bottomOk = false;

  if (as7341Ok) {
    as7341.setLEDCurrent(LED_CURRENT_MA);
    delay(1000);
    // --- Window 1: Creatinine (top pad) ---
    as7341.enableLED(true);
    digitalWrite(READY_LED_PIN, HIGH);
    Serial.println("Position the CREATININE (top) pad under the sensor now...");
    topOk = captureAveragedWindow("Creatinine (top)", lastTopRaw, CAPTURE_WINDOW_MS);

    // --- Brief gap: signal to reposition the strip ---
    as7341.enableLED(false);
    digitalWrite(READY_LED_PIN, LOW);
    Serial.println("Reposition the strip to the UREA/pH (bottom) pad now...");
    delay(TRANSITION_GAP_MS);

    // --- Window 2: Urea + pH (bottom pad, same capture for both) ---
    as7341.enableLED(true);
    digitalWrite(READY_LED_PIN, HIGH);
    bottomOk = captureAveragedWindow("Urea/pH (bottom)", lastBottomRaw, CAPTURE_WINDOW_MS);

    as7341.enableLED(false);
    updateReadyLED(); // back to steady "armed" rather than fully off
  } else {
    Serial.println("AS7341 not ready — skipping color capture this cycle, sending temperature only.");
  }

  haveColorReading = topOk && bottomOk;
  if (as7341Ok && !haveColorReading) {
    Serial.println("One or both pad captures failed — sending without raw color channels this cycle.");
  }

  // The sensor initialized fine this cycle but neither window got a single
  // sample — that pattern means it most likely dropped off the bus *after*
  // init (a power blip, a jostled wire), not that a pad was simply
  // presented wrong. Clear the ready flag so the next cycle re-runs
  // ensureAS7341Ready() instead of trusting a connection that isn't
  // actually there anymore — this is the automatic-recovery path.
  if (as7341Ok && !topOk && !bottomOk) {
    Serial.println("AS7341 stopped responding after init — will re-initialize next cycle.");
    as7341Ready = false;
    updateReadyLED();
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

// Appends a raw-channels JSON object (e.g. {"F1":420,...,"NIR":200}) onto
// the end of buf, using strlen(buf) as the write offset each time so
// sequential calls compose cleanly without separately tracked length
// bookkeeping. buf must already be null-terminated (snprintf guarantees
// this at every step).
void appendRawChannelsJson(char *buf, size_t bufSize, const uint16_t raw[AS7341_CHANNEL_COUNT]) {
  const char *keys[AS7341_CHANNEL_COUNT] = {"F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "CLEAR", "NIR"};
  size_t len = strlen(buf);
  len += snprintf(buf + len, bufSize - len, "{");
  for (int i = 0; i < AS7341_CHANNEL_COUNT; i++) {
    len += snprintf(buf + len, bufSize - len, "\"%s\":%u%s", keys[i], raw[i], i < AS7341_CHANNEL_COUNT - 1 ? "," : "");
  }
  snprintf(buf + len, bufSize - len, "}");
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

  char body[900];
  snprintf(body, sizeof(body), "{\"temperature\":%.1f", lastTemperature);
  if (haveColorReading) {
    size_t len = strlen(body);
    snprintf(body + len, sizeof(body) - len, ",\"top_raw_channels\":");
    appendRawChannelsJson(body, sizeof(body), lastTopRaw);
    len = strlen(body);
    snprintf(body + len, sizeof(body) - len, ",\"bottom_raw_channels\":");
    appendRawChannelsJson(body, sizeof(body), lastBottomRaw);
  }
  size_t len = strlen(body);
  snprintf(body + len, sizeof(body) - len, "}");

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

// Minimal manual extraction of a `"key":"value"` string field from a JSON
// response body — same lightweight indexOf-based parsing already used below
// for pending_sample, rather than pulling in ArduinoJson for one optional
// field. Leaves out[0]='\0' (and returns false) if the key isn't present at
// all — the un-requested auto-cycle's /device/ping response has no
// patient_name field, which is the expected, non-error case for that path.
bool extractJsonStringField(const String &json, const char *key, char *out, size_t outSize) {
  out[0] = '\0';
  String needle = "\"" + String(key) + "\":\"";
  int start = json.indexOf(needle);
  if (start == -1) return false;
  start += needle.length();
  int end = json.indexOf('"', start);
  if (end == -1) return false;
  size_t len = (size_t)(end - start);
  if (len >= outSize) len = outSize - 1;
  json.substring(start, start + len).toCharArray(out, len + 1);
  return true;
}

// `nameOut` is filled with the armed patient's name when the backend's
// /device/ping response includes one (a dashboard/WhatsApp arm request for
// a specific patient — see routers/device.py's ping()) — left as an empty
// string for the periodic un-requested auto-cycle, which has no associated
// patient. `nameOutSize` must be > 0.
bool checkPendingSample(char *nameOut, size_t nameOutSize) {
  nameOut[0] = '\0';
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
    if (pending) {
      extractJsonStringField(resp, "patient_name", nameOut, nameOutSize);
    }
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

  pinMode(READY_LED_PIN, OUTPUT);
  digitalWrite(READY_LED_PIN, LOW); // off until WiFi connects AND the AS7341 initializes

  pinMode(BUZZER_PIN, OUTPUT);

  Wire.begin(21, 22); // SDA, SCL — matches the wiring notes above
  dht.begin();
  // AS7341 init is lazy (see ensureAS7341Ready() below) — it happens on the
  // first real test cycle, triggered by sendReading() a few lines down, not
  // here. Calling as7341.begin() here too would just be a second redundant
  // init on every boot for no benefit.

  // Explicit SPI.begin() with the actual wired pins, before tft.begin() —
  // see the TFT_SCK/TFT_MOSI/TFT_MISO comment above.
  SPI.begin(TFT_SCK, TFT_MISO, TFT_MOSI, TFT_CS);
  tft.begin();
  tft.setRotation(1); // landscape, 320 wide x 240 tall — use 3 instead if it's mounted upside down
  runBootSequence();  // blink x2 -> "NOVERA / Starting..." -> "Ready" -> idle "NOVERA"

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
    updateReadyLED();
    connectWiFi();
  }

  if (millis() - lastPingAt >= PING_INTERVAL_MS) {
    lastPingAt = millis();
    char patientName[32];
    if (checkPendingSample(patientName, sizeof(patientName))) {
      Serial.println("Sample requested (dashboard or WhatsApp) -- get ready...");
      signalRequestReceived();
      showTestingScreen(patientName);
      Serial.println("Starting test now.");
      sendReading();
      buzzTestComplete();
      showThankYouScreen(patientName);
      delay(TFT_THANK_YOU_MS);
      showIdleScreen();
      lastSendAt = millis();
    }
  }

  if (millis() - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = millis();
    sendReading();
  }
}
