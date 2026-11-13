// Host <-> desk LED protocol: one text line per message (same style as grounded_dsp/protocol.h).
// Host counterpart: host/led.py (change both together).
//
//   Host -> LED
//     G,<rhythm>,<cycles>           start guiding (cycles 0 = until X); replaces a running session
//     X                             stop, back to idle
//     ?                             report the current state
//   LED -> host
//     S,IDLE                        state: idle (after every change, and in reply to ?)
//     S,GUIDE,<rhythm>,<cycles>     state: guiding
//     D,<rhythm>,<cycles_done>      a session ended (finished, stopped or replaced)
//     P,<rhythm>                    the user started a session with the button
//     !,<message>                   the last command was rejected
//     #<text>                       human-readable debug text; the host ignores it
//
// No sscanf/printf here: on a 32 KB MCU they pull in several KB of library code.
#pragma once
#include <stddef.h>
#include <stdint.h>

struct LedCommand {
  enum Type : uint8_t { NONE, GUIDE, STOP, STATUS, INVALID };
  Type type;
  uint8_t rhythm;
  uint16_t cycles;
};

// Collects received characters into lines. Fixed buffer, no dynamic memory.
// A line longer than MAX is dropped whole (a corrupted line must not become a valid command).
class LineReader {
 public:
  static const int MAX = 31;
  // Feed one character. Returns the finished line (without \r\n) or nullptr.
  // The returned pointer is valid until the next call.
  const char* feed(char c);

 private:
  char buf_[MAX + 1];
  int len_ = 0;
  bool overflow_ = false;
};

LedCommand parse_led_command(const char* line);

// Message builders: write a full line ending in '\n' into buf, return its length.
// buf must hold at least LED_MSG_MAX bytes.
static const size_t LED_MSG_MAX = 24;
size_t led_msg_idle(char* buf);
size_t led_msg_guide(char* buf, uint8_t rhythm, uint16_t cycles);
size_t led_msg_done(char* buf, uint8_t rhythm, uint16_t cycles_done);
size_t led_msg_button(char* buf, uint8_t rhythm);
