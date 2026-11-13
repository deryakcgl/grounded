#pragma once
#include <stddef.h>
#include <stdint.h>

struct LedCommand {
  enum Type : uint8_t { NONE, GUIDE, STOP, STATUS, INVALID };
  Type type;
  uint8_t rhythm;
  uint16_t cycles;
};

class LineReader {
 public:
  static const int MAX = 31;
  const char* feed(char c);

 private:
  char buf_[MAX + 1];
  int len_ = 0;
  bool overflow_ = false;
};

LedCommand parse_led_command(const char* line);

static const size_t LED_MSG_MAX = 24;
size_t led_msg_idle(char* buf);
size_t led_msg_guide(char* buf, uint8_t rhythm, uint16_t cycles);
size_t led_msg_done(char* buf, uint8_t rhythm, uint16_t cycles_done);
size_t led_msg_button(char* buf, uint8_t rhythm);
