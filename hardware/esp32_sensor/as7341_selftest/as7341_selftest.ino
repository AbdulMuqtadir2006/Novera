/*
 * AS7341 library-level self-test — standalone, separate from esp32_sensor.ino
 * and from i2c_scanner.ino. The raw I2C scanner already confirmed the chip
 * ACKs at 0x39, so this step checks the next layer up: does the Adafruit
 * library's begin() (which reads and validates a chip-ID register, not just
 * an address ACK) succeed, and does the onboard LED actually respond to
 * library-level control.
 *
 * Before running this: fully power-cycle the AS7341 (disconnect VIN, and
 * ideally GND, for ~10s) — this clears any stuck internal state left over
 * from an earlier partial brownout, which begin() alone can't fix.
 *
 * Wiring: same as esp32_sensor.ino — SDA->D21, SCL->D22, VIN->3V3, GND->GND.
 * Requires the "Adafruit AS7341" library (Library Manager).
 *
 * Watch Serial Monitor (115200 baud) alongside the physical LED. Every 5s it
 * will: call begin(), print whether it succeeded, and if so enable the LED
 * for 3s (watch for it lighting) then disable it.
 */

#include <Wire.h>
#include <Adafruit_AS7341.h>

#define SDA_PIN 21
#define SCL_PIN 22

Adafruit_AS7341 as7341;

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println();
  Serial.println("AS7341 self-test starting...");
}

void loop() {
  Serial.println("Calling as7341.begin()...");
  bool ok = as7341.begin();
  Serial.print("begin() returned: ");
  Serial.println(ok ? "true (success)" : "false (FAILED)");

  if (ok) {
    Serial.println("Enabling LED at low current (10mA) for 3 seconds -- watch the sensor now.");
    as7341.setLEDCurrent(10);
    as7341.enableLED(true);
    delay(3000);
    as7341.enableLED(false);
    Serial.println("LED disabled.");
  } else {
    Serial.println("begin() failed even though the chip ACKs on the bus (per the scanner).");
    Serial.println("This usually means either:");
    Serial.println("  - the chip is still in a bad internal state -> power-cycle it fully again (VIN AND GND disconnected, not just reset)");
    Serial.println("  - a marginal power supply that sags under the real init sequence -> try powering VIN directly from the ESP32's own 3V3 pin instead of a separate/external 3.3V source, if you aren't already");
  }

  Serial.println();
  delay(5000);
}
