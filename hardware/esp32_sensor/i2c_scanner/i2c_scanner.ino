/*
 * I2C bus scanner — standalone diagnostic, separate from the main
 * esp32_sensor.ino sketch. Bypasses the Adafruit_AS7341 library entirely
 * and just asks every possible I2C address "is anyone there?" at the raw
 * Wire level. Use this to answer one question: is the AS7341 chip
 * electrically alive and responding at all, independent of any
 * library-level init logic that might be failing for other reasons.
 *
 * Wiring must match esp32_sensor.ino: AS7341 SDA->D21, SCL->D22, VIN->3V3,
 * GND->GND. If VIN is coming from a separate 3.3V supply (not the ESP32's
 * own 3V3 pin), that supply's GND MUST also be tied to the ESP32's GND —
 * I2C needs a shared ground reference between every device on the bus, or
 * nothing responds even if everything else is wired correctly.
 *
 * The AS7341's default I2C address is 0x39.
 *
 * Upload this, open Serial Monitor at 115200 baud, and read the result:
 *   - "Found device at 0x39" (or any address)  -> chip is alive, the
 *     problem is elsewhere (library state, wrong current settings, etc.)
 *     — NOT a burned chip.
 *   - "No I2C devices found"                    -> either a wiring/power/
 *     ground problem, or the chip really is dead. Recheck wiring (especially
 *     a shared ground if using a separate supply) before assuming the worst.
 */

#include <Wire.h>

#define SDA_PIN 21
#define SCL_PIN 22

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println();
  Serial.println("I2C scanner starting...");
  Serial.print("SDA=D");
  Serial.print(SDA_PIN);
  Serial.print("  SCL=D");
  Serial.println(SCL_PIN);
}

void loop() {
  int found = 0;
  Serial.println("Scanning...");

  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    uint8_t error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Found device at 0x");
      if (addr < 16) Serial.print("0");
      Serial.print(addr, HEX);
      if (addr == 0x39) Serial.print("  <-- this is the AS7341's expected address");
      Serial.println();
      found++;
    } else if (error == 4) {
      Serial.print("Unknown error at address 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
    }
  }

  if (found == 0) {
    Serial.println("No I2C devices found.");
    Serial.println("Before assuming the chip is dead, check:");
    Serial.println("  1. GND is shared between the AS7341's power source and the ESP32's GND");
    Serial.println("     (critical if VIN comes from a separate 3.3V supply, not the ESP32's own 3V3 pin)");
    Serial.println("  2. SDA/SCL are on D21/D22 and not swapped");
    Serial.println("  3. VIN actually measures ~3.3V with a multimeter (probe at the AS7341 pin itself)");
    Serial.println("  4. Every wire is fully seated, no loose header pins");
  } else {
    Serial.print(found);
    Serial.println(" device(s) found.");
  }

  Serial.println();
  delay(3000);
}
