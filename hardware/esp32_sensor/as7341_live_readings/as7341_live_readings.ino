/*
 * AS7341 live raw-channel reader — standalone testing tool, separate from
 * esp32_sensor.ino and as7341_selftest.ino. Streams all 10 channels to
 * Serial in real time so you can hold different colors/reagent pads under
 * the sensor and watch how the raw numbers respond — this is the tool for
 * exploring "what does this color look like as numbers" BEFORE deciding
 * PH_RAW_MIN/PH_RAW_MAX etc. in esp32_sensor.ino. Nothing here is sent to
 * the backend; this is local Serial output only.
 *
 * IMPORTANT for calibration validity: this uses the AS7341's own onboard
 * LED at the same brightness (10mA) and leaves gain at the same default
 * esp32_sensor.ino uses (neither sketch calls setGain()) — readings
 * gathered under different LED/gain settings wouldn't transfer to the real
 * sketch's behavior. If you ever add a setGain() call here to experiment,
 * make the same change in esp32_sensor.ino before trusting any calibration
 * numbers you note down.
 *
 * WHY EVERYTHING READ "YELLOW-GREEN" BEFORE: the onboard LED is a
 * phosphor-converted white LED — a blue pump plus a broad yellow-green
 * phosphor hump, not a flat spectrum. Comparing raw channel counts (as the
 * first version of this sketch did) mostly measures that uneven light
 * source, not the object underneath it — F5/F6 read high almost no matter
 * what's presented. The fix: send 'c' over Serial with a WHITE or neutral
 * grey card (plain white paper works) under the sensor to record a
 * baseline, then every reading after that is shown as a ratio to that
 * baseline (reflectance-relative) instead of a raw count — this cancels
 * out the LED/sensor's own spectral shape. Color guesses are computed from
 * the calibrated ratios, not raw counts, once you've calibrated.
 *
 * Wiring: same as esp32_sensor.ino — SDA->D21, SCL->D22, VIN->3V3, GND->GND.
 * Requires the "Adafruit AS7341" library (Library Manager). If begin()
 * fails, run as7341_selftest.ino first for deeper wiring/power diagnostics.
 *
 * Watch Serial Monitor at 115200 baud (make sure "Newline" or "Both NL & CR"
 * line ending is selected so the 'c' calibration command is recognized).
 * One line per sample, ~3/sec. Each line calls out CLEAR and F6
 * specifically — those are the two channels esp32_sensor.ino actually uses
 * today (CLEAR for pH and Urea, F6 for Creatinine — see PH_CHANNEL_IDX /
 * UREA_CHANNEL_IDX / CREATININE_CHANNEL_IDX there).
 *
 * The color guess is still a heuristic, not real colorimetry — even
 * calibrated, it reports whichever of F1..F8's wavelength band has the
 * highest reflectance ratio, not a proper CIE XYZ/RGB reconstruction (that
 * needs AS7341-specific calibration matrices beyond a single white
 * reference). Calibrated, it should track true color far better than raw
 * counts did — good enough to sanity-check reagent-pad color shifts, not a
 * lab-grade spectrometer.
 */

#include <Wire.h>
#include <Adafruit_AS7341.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define LED_CURRENT_MA 10

Adafruit_AS7341 as7341;
const int CHANNEL_COUNT = 10;
const int CLEAR_IDX = 8;  // must match esp32_sensor.ino's CLEAR_IDX — see that file's header comment
const int F6_IDX = 5;     // must match esp32_sensor.ino's CREATININE_CHANNEL_IDX

// Must match esp32_sensor.ino's captureStablePad() PRESENCE_MIN_CLEAR — below
// this, there's nothing meaningful under the sensor to name a color for.
const uint16_t PRESENCE_MIN_CLEAR = 300;

// F1..F8 center wavelengths, in channel order — used only to label the
// guessed dominant band below, not for any actual math.
const char *CHANNEL_COLOR_NAMES[8] = {
  "Violet (415nm)", "Blue (445nm)", "Cyan (480nm)", "Green (515nm)",
  "Yellow-Green (555nm)", "Amber/Orange (590nm)", "Red (630nm)", "Deep Red (680nm)",
};

float baseline[8] = {1, 1, 1, 1, 1, 1, 1, 1};  // F1..F8 white-reference counts; 1s until calibrated
bool calibrated = false;

void printPadded(uint16_t v) {
  if (v < 1000) Serial.print(' ');
  if (v < 100) Serial.print(' ');
  if (v < 10) Serial.print(' ');
  Serial.print(v);
}

// Reads several samples with a white/neutral card under the sensor and
// stores the F1..F8 averages as the reflectance baseline. Blocking — takes
// about 1.5s.
void calibrateWhiteReference() {
  Serial.println();
  Serial.println("Calibrating -- hold a white/neutral card steady under the sensor...");
  const int SAMPLES = 8;
  double sums[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  int good = 0;
  for (int s = 0; s < SAMPLES; s++) {
    uint16_t readings[CHANNEL_COUNT];
    if (as7341.readAllChannels(readings)) {
      for (int i = 0; i < 8; i++) sums[i] += readings[i];
      good++;
    }
    delay(150);
  }
  if (good == 0) {
    Serial.println("Calibration failed -- no successful reads. Try again ('c').");
    return;
  }
  for (int i = 0; i < 8; i++) {
    baseline[i] = (float)(sums[i] / good);
    if (baseline[i] < 1) baseline[i] = 1;  // avoid divide-by-zero on a near-dark read
  }
  calibrated = true;
  Serial.println("Calibration done. Readings below are now relative to this white reference.");
  Serial.println();
}

// Dominant-band guess from CALIBRATED (reflectance-relative) values —
// see header comment for what this is and isn't.
const char *guessColor(float normalized[8]) {
  int peakIdx = 0;
  for (int i = 1; i < 8; i++) {
    if (normalized[i] > normalized[peakIdx]) peakIdx = i;
  }
  return CHANNEL_COLOR_NAMES[peakIdx];
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println();
  Serial.println("AS7341 live reader starting...");
  if (!as7341.begin()) {
    Serial.println("begin() FAILED -- check wiring/power (see as7341_selftest.ino for deeper diagnostics). Halting.");
    while (true) delay(1000);
  }
  Serial.println("begin() OK. Enabling onboard LED (10mA, same as real captures)...");
  as7341.setLEDCurrent(LED_CURRENT_MA);
  as7341.enableLED(true);
  delay(200); // let the LED stabilize before the first reading

  Serial.println();
  Serial.println("Place a WHITE or neutral card under the sensor, then send 'c' to calibrate.");
  Serial.println("Color guesses are unreliable (biased toward the LED's own yellow-green hump) until you do.");
  Serial.println();
  Serial.println(" F1(415) F2(445) F3(480) F4(515) F5(555) F6(590) F7(630) F8(680)  Clear   NIR   | CLEAR(pH/Urea)  F6(Creatinine)  ~Color");
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'c' || c == 'C') calibrateWhiteReference();
  }

  uint16_t readings[CHANNEL_COUNT];
  if (!as7341.readAllChannels(readings)) {
    Serial.println("Read failed -- sensor may have dropped off the bus.");
    delay(500);
    return;
  }

  for (int i = 0; i < CHANNEL_COUNT; i++) {
    printPadded(readings[i]);
    Serial.print("  ");
  }
  Serial.print(" | CLEAR=");
  Serial.print(readings[CLEAR_IDX]);
  Serial.print("   F6=");
  Serial.print(readings[F6_IDX]);
  Serial.print("   ~Color: ");

  if (readings[CLEAR_IDX] < PRESENCE_MIN_CLEAR) {
    Serial.println("(nothing under sensor)");
  } else if (!calibrated) {
    Serial.println("(uncalibrated -- send 'c' with a white card under the sensor first)");
  } else {
    float normalized[8];
    for (int i = 0; i < 8; i++) normalized[i] = readings[i] / baseline[i];
    Serial.println(guessColor(normalized));
  }

  delay(300);
}
