#include <Arduino.h>
#include "ads1292r.h"
#include "arduino_bus.h"
#include "pod_pipeline.h"
#include "spsc_fifo.h"

const uint32_t PIN_BEAT_LED = D7;
const uint32_t BEAT_BLINK_MS = 80;
const float RESP_UNITS_PER_CODE = 1e-5f;

ArduinoBus bus;
Ads1292r adc(bus);
SpscFifo<Ads1292r::Frame, 64> fifo;

uint32_t beatLedOn = 0;

void serialWrite(const char* text, size_t len) { Serial.write(text, len); }
void onBeat() {
  digitalWrite(PIN_BEAT_LED, HIGH);
  beatLedOn = millis() | 1;
}
PodPipeline pipeline(serialWrite, onBeat);

void onDrdy() {
  Ads1292r::Frame f;
  adc.readFrame(f);
  fifo.push(f);
}

void setup() {
  Serial.begin(115200);
  setupAdsPins();
  pinMode(PIN_BEAT_LED, OUTPUT);

  const Ads1292r::Error err = adc.begin();
  if (err != Ads1292r::OK) {
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
    if (settle > 0) {
      settle--;
      continue;
    }
    if (!f.valid) {
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
