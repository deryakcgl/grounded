#include <Arduino.h>

#include "ads1292r.h"
#include "arduino_bus.h"

ArduinoBus bus;
Ads1292r adc(bus);

static const char* const REG_NAMES[ads::REG_COUNT] = {
    "ID", "CONFIG1", "CONFIG2", "LOFF", "CH1SET", "CH2SET", "RLD_SENS", "LOFF_SENS",
    "LOFF_STAT", "RESP1", "RESP2", "GPIO"};

static void hex2(uint8_t v) {
  if (v < 0x10) Serial.print('0');
  Serial.print(v, HEX);
}

static bool waitDrdy(uint32_t timeout_ms) {
  const uint32_t t0 = millis();
  while (digitalRead(PIN_DRDY) == HIGH) {
    if (millis() - t0 > timeout_ms) return false;
  }
  return true;
}

static void halt(const char* why) {
  Serial.print("STOP: ");
  Serial.println(why);
  for (;;) delay(1000);
}

static void step1_id() {
  Serial.println("\n== 1. SPI and chip ID ==");
  const Ads1292r::Error err = adc.begin();
  Serial.print("ID register: 0x");
  hex2(adc.id());
  Serial.println(adc.id() == ads::ID_ADS1292R ? " (ADS1292R) PASS" : " FAIL (expected 0x73)");
  if (err == Ads1292r::NO_DEVICE) {
    halt("nothing answers. Check power (VCC/5V and GND), CS->D10, SCK->D13, MISO->D12, MOSI->D11, PWDN/RST->D8");
  }
  if (err == Ads1292r::WRONG_DEVICE) halt("a chip answers but it is not an ADS1292R (or a data line is bad)");
  if (err == Ads1292r::VERIFY_FAILED) {
    Serial.print("register 0x");
    hex2(adc.failedRegister());
    Serial.print(" (");
    Serial.print(REG_NAMES[adc.failedRegister()]);
    Serial.println(") did not read back as written");
    halt("check MOSI->D11 and the ground connection");
  }
}

static void step2_registers() {
  Serial.println("\n== 2. Registers ==");
  uint8_t regs[ads::REG_COUNT];
  adc.readRegisters(regs);
  bool ok = true;
  for (uint8_t r = 0; r < ads::REG_COUNT; r++) {
    Serial.print(REG_NAMES[r]);
    Serial.print(" = 0x");
    hex2(regs[r]);
    for (uint8_t i = 0; i < Ads1292r::CONFIG_COUNT; i++) {
      const Ads1292r::Setting& s = Ads1292r::CONFIG[i];
      if (s.reg != r) continue;
      const bool match = (regs[r] & s.mask) == (s.value & s.mask);
      ok &= match;
      Serial.print(match ? "  ok" : "  DIFFERENT, expected 0x");
      if (!match) hex2(s.value);
    }
    Serial.println();
  }
  Serial.println(ok ? "registers PASS" : "registers FAIL");
}

static bool step3_test_signal() {
  Serial.println("\n== 3. Internal test signal (1 Hz square, nothing attached needed) ==");
  if (adc.startTestSignal() != Ads1292r::OK) halt("could not switch to the test signal");
  int32_t lo[2] = {INT32_MAX, INT32_MAX}, hi[2] = {INT32_MIN, INT32_MIN};
  int frames = 0, invalid = 0;
  const uint32_t t0 = millis();
  while (frames < 750 + ads::SETTLE_FRAMES) {
    if (!waitDrdy(100)) halt("DRDY never went low: check DRDY->D9, and START->GND");
    Ads1292r::Frame f;
    adc.readFrame(f);
    if (frames++ < ads::SETTLE_FRAMES) continue;
    if (!f.valid) { invalid++; continue; }
    const int32_t v[2] = {f.resp, f.ecg};
    for (int c = 0; c < 2; c++) {
      if (v[c] < lo[c]) lo[c] = v[c];
      if (v[c] > hi[c]) hi[c] = v[c];
    }
  }
  const uint32_t ms = millis() - t0;
  Serial.print("frames: ");
  Serial.print(frames);
  Serial.print(" in ");
  Serial.print(ms);
  Serial.print(" ms (expected ~");
  Serial.print((750 + ads::SETTLE_FRAMES) * 4);
  Serial.print(" ms at 250 SPS), invalid status words: ");
  Serial.println(invalid);

  bool ok = invalid == 0;
  const char* names[2] = {"CH1 (respiration)", "CH2 (ECG)        "};
  for (int c = 0; c < 2; c++) {
    const int32_t pp = hi[c] - lo[c];
    const bool pass = Ads1292r::testSignalOk(pp, Ads1292r::ECG_GAIN);
    ok &= pass;
    Serial.print(names[c]);
    Serial.print(": min ");
    Serial.print(lo[c]);
    Serial.print(", max ");
    Serial.print(hi[c]);
    Serial.print(", peak-to-peak ");
    Serial.print(pp);
    Serial.print(" (expected ~");
    Serial.print(2 * Ads1292r::testSignalCodes(Ads1292r::ECG_GAIN));
    Serial.println(pass ? ") PASS" : ") FAIL");
  }
  Serial.println(ok ? "data path PASS: the board works. Now attach the electrodes."
                    : "data path FAIL: the problem is on the board/wiring side, not the electrodes");
  return ok;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("#Grounded pod bring-up");
  setupAdsPins();
  step1_id();
  step2_registers();
  step3_test_signal();

  Serial.println("\n== 4. Electrodes ==");
  if (adc.startNormal() != Ads1292r::OK) halt("could not switch back to the electrodes");
  Serial.println("Lead-off bits: IN2P/IN2N = ECG electrodes (0 = on the skin). Raw stream follows:");
  Serial.println("#raw: R,<respiration code>,<ECG code>,<lead-off bits>  (view: python host/scope.py)");
}

void loop() {
  if (!waitDrdy(100)) {
    Serial.println("#DRDY stopped");
    return;
  }
  Ads1292r::Frame f;
  adc.readFrame(f);
  if (!f.valid) return;
  Serial.print("R,");
  Serial.print(f.resp);
  Serial.print(',');
  Serial.print(f.ecg);
  Serial.print(',');
  Serial.println(f.lead_off);
}
