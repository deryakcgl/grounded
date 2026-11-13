#pragma once
#include <Arduino.h>
#include <SPI.h>

#include "ads1292r.h"

const uint32_t PIN_CS = D10;
const uint32_t PIN_DRDY = D9;
const uint32_t PIN_RESET = D8;

const SPISettings ADS_SPI(1000000, MSBFIRST, SPI_MODE1);

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

inline void setupAdsPins() {
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_RESET, OUTPUT);
  digitalWrite(PIN_RESET, HIGH);
  pinMode(PIN_DRDY, INPUT);
  SPI.begin();
}
