// The desk LED's behaviour: serial commands and button presses -> pacer -> messages to the host.
// Hardware-free. The firmware (breath_led) and the Mac's virtual LED (led_sim) only connect it
// to real inputs and outputs, so the behaviour is tested once and is the same everywhere.
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "breath_pacer.h"
#include "led_protocol.h"

class LedDevice {
 public:
  // Where messages for the host go (Serial on the board, stdout on the Mac).
  // A plain function pointer: no std::function / heap on the MCU.
  typedef void (*Writer)(const char* text, size_t len);

  static const uint16_t BUTTON_CYCLES = 6;   // a button-started session (~1 min of Relax)

  explicit LedDevice(Writer write) : write_(write) {}

  void begin();                             // announce the (idle) state
  void onChar(char c, uint32_t now_ms);     // one received serial character
  void onButton(uint32_t now_ms);           // one debounced button press
  void tick(uint32_t now_ms);               // call every few ms
  float level(uint32_t now_ms) const { return pacer_.level(now_ms); }
  const BreathPacer& pacer() const { return pacer_; }

 private:
  void handle(const LedCommand& cmd, uint32_t now_ms);
  void endSession();                        // sends D if a session is running
  void sendState();
  void send(size_t len) { write_(buf_, len); }
  void sendText(const char* text);

  Writer write_;
  BreathPacer pacer_;
  LineReader reader_;
  uint8_t next_rhythm_ = 0;                 // rhythm the button starts when idle
  char buf_[LED_MSG_MAX];
};
