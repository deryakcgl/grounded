// Chest pod firmware: reads the ADS1292R, runs the detectors, sends protocol lines over serial.
//
//   DRDY interrupt (250 Hz): read one frame over SPI, push it into the FIFO   (~80 us)
//   loop():                  pop frames, run PodPipeline, print protocol lines
//
// Reading in the interrupt means a slow loop() (a beat search, later a Bluetooth burst) can't
// make us miss a frame: the chip overwrites its output at the next conversion.
// Everything here except the pins and SPI is shared with the Mac simulation (test_native/pod_sim).
#include <Arduino.h>
#include <SPI.h>

#include "ads1292r.h"
#include "pod_pipeline.h"
#include "spsc_fifo.h"

const uint32_t PIN_CS = D10;
const uint32_t PIN_DRDY = D9;
const uint32_t PIN_RESET = D8;
const uint32_t PIN_BEAT_LED = D7;     // blinks on every detected heartbeat
const uint32_t BEAT_BLINK_MS = 80;

// Mode 1 (8.5.1.3/8.5.1.4: DIN latched on the falling edge, DOUT changes on the rising edge).
// 1 MHz: below the 2 x fCLK limit for register access, and one byte (8 us) already lasts the
// 4 tCLK the chip needs between bytes.
const SPISettings ADS_SPI(1000000, MSBFIRST, SPI_MODE1);

// Respiration: arbitrary units (only changes matter; the detectors adapt to the level)
const float RESP_UNITS_PER_CODE = 1e-5f;

class ArduinoBus : public Ads1292rBus {
 public:
  void select(bool active) override {
    if (active) {
      SPI.beginTransaction(ADS_SPI);
      digitalWrite(PIN_CS, LOW);
    } else {
      digitalWrite(PIN_CS, HIGH);
      SPI.endTransaction();
    }
  }
  uint8_t transfer(uint8_t out) override { return SPI.transfer(out); }
  void delayUs(uint32_t us) override { delayMicroseconds(us); }
  void setReset(bool high) override { digitalWrite(PIN_RESET, high ? HIGH : LOW); }
};

ArduinoBus bus;
Ads1292r adc(bus);
SpscFifo<Ads1292r::Frame, 64> fifo;   // 64 frames = 256 ms of slack for loop()

uint32_t beatLedOn = 0;   // millis() when the LED was switched on, 0 = off

void serialWrite(const char* text, size_t len) { Serial.write(text, len); }
void onBeat() {
  digitalWrite(PIN_BEAT_LED, HIGH);
  beatLedOn = millis() | 1;   // | 1: never 0, which means "off"
}
PodPipeline pipeline(serialWrite, onBeat);

void onDrdy() {
  Ads1292r::Frame f;
  adc.readFrame(f);
  fifo.push(f);   // if full, the frame is dropped and counted
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_RESET, OUTPUT);
  digitalWrite(PIN_RESET, HIGH);
  pinMode(PIN_DRDY, INPUT);
  pinMode(PIN_BEAT_LED, OUTPUT);
  SPI.begin();

  const Ads1292r::Error err = adc.begin();
  if (err != Ads1292r::OK) {
    // Debug lines start with '#': the host ignores them
    static const char* const NAMES[] = {"ok", "no device (check wiring/power)",
                                        "wrong device (not an ADS1292R)", "register verify failed"};
    for (;;) {
      Serial.print("#ADS1292R error: ");
      Serial.print(NAMES[err]);
      Serial.print(", id 0x");
      Serial.print(adc.id(), HEX);
      if (err == Ads1292r::VERIFY_FAILED) {
        Serial.print(", register 0x");
        Serial.print(adc.failedRegister(), HEX);
      }
      Serial.println();
      delay(1000);
    }
  }
  Serial.println("#Grounded pod ready");
  attachInterrupt(digitalPinToInterrupt(PIN_DRDY), onDrdy, FALLING);
}

void loop() {
  static uint8_t settle = ads::SETTLE_FRAMES;
  static uint32_t reported_drops = 0, bad_frames = 0;
  Ads1292r::Frame f;
  while (fifo.pop(f)) {
    if (settle > 0) {   // first frames after START are not settled (8.5.1.10)
      settle--;
      continue;
    }
    if (!f.valid) {     // status word wasn't 1100...: SPI glitch, skip this frame
      bad_frames++;
      continue;
    }
    pipeline.push(f.resp * RESP_UNITS_PER_CODE, f.ecg * Ads1292r::ecgMillivoltsPerCode(), f.lead_off);
  }
  if (beatLedOn && millis() - beatLedOn >= BEAT_BLINK_MS) {
    digitalWrite(PIN_BEAT_LED, LOW);
    beatLedOn = 0;
  }
  if (fifo.dropped() != reported_drops) {
    reported_drops = fifo.dropped();
    Serial.print("#FIFO overflow, frames dropped: ");
    Serial.println(reported_drops);
  }
}
