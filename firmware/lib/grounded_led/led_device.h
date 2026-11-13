#pragma once
#include <stddef.h>
#include <stdint.h>

#include "breath_pacer.h"
#include "led_protocol.h"

class LedDevice {
 public:
  typedef void (*Writer)(const char* text, size_t len);

  static const uint16_t BUTTON_CYCLES = 6;

  explicit LedDevice(Writer write) : write_(write) {}

  void begin();
  void onChar(char c, uint32_t now_ms);
  void onButton(uint32_t now_ms);
  void tick(uint32_t now_ms);
  float level(uint32_t now_ms) const { return pacer_.level(now_ms); }
  const BreathPacer& pacer() const { return pacer_; }

 private:
  void handle(const LedCommand& cmd, uint32_t now_ms);
  void endSession();
  void sendState();
  void send(size_t len) { write_(buf_, len); }
  void sendText(const char* text);

  Writer write_;
  BreathPacer pacer_;
  LineReader reader_;
  uint8_t next_rhythm_ = 0;
  char buf_[LED_MSG_MAX];
};
