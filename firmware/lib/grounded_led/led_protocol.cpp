#include "led_protocol.h"

const char* LineReader::feed(char c) {
  if (c == '\r') return nullptr;               // accept both \n and \r\n line endings
  if (c == '\n') {
    const bool ok = !overflow_ && len_ > 0;
    buf_[len_] = '\0';
    len_ = 0;
    overflow_ = false;
    return ok ? buf_ : nullptr;
  }
  if (len_ < MAX) {
    buf_[len_++] = c;
  } else {
    overflow_ = true;                          // keep reading until '\n', then drop the line
  }
  return nullptr;
}

// Reads an unsigned decimal number at *p, moves p past it. False if there are no digits
// or the number is larger than max.
static bool parse_uint(const char*& p, uint32_t max, uint32_t& out) {
  if (*p < '0' || *p > '9') return false;
  uint32_t v = 0;
  while (*p >= '0' && *p <= '9') {
    v = v * 10 + (uint32_t)(*p++ - '0');       // multiply by 10: cheap (hardware multiplier)
    if (v > max) return false;
  }
  out = v;
  return true;
}

LedCommand parse_led_command(const char* line) {
  LedCommand cmd = {LedCommand::INVALID, 0, 0};
  if (line[0] == '\0') {
    cmd.type = LedCommand::NONE;
  } else if (line[0] == 'X' && line[1] == '\0') {
    cmd.type = LedCommand::STOP;
  } else if (line[0] == '?' && line[1] == '\0') {
    cmd.type = LedCommand::STATUS;
  } else if (line[0] == 'G' && line[1] == ',') {
    const char* p = line + 2;
    uint32_t rhythm, cycles;
    if (parse_uint(p, 255, rhythm) && *p++ == ',' && parse_uint(p, 65535, cycles) && *p == '\0') {
      cmd = {LedCommand::GUIDE, (uint8_t)rhythm, (uint16_t)cycles};
    }
  }
  return cmd;
}

// --- Message builders ---

// Writes v in decimal at buf, returns the number of characters.
static size_t put_uint(char* buf, uint32_t v) {
  char tmp[10];
  size_t n = 0;
  do {
    tmp[n++] = (char)('0' + v % 10);           // runs only when a message is sent: fine
    v /= 10;
  } while (v);
  for (size_t i = 0; i < n; i++) buf[i] = tmp[n - 1 - i];
  return n;
}

static size_t put_str(char* buf, const char* s) {
  size_t n = 0;
  while (s[n]) {
    buf[n] = s[n];
    n++;
  }
  return n;
}

size_t led_msg_idle(char* buf) { return put_str(buf, "S,IDLE\n"); }

size_t led_msg_guide(char* buf, uint8_t rhythm, uint16_t cycles) {
  size_t n = put_str(buf, "S,GUIDE,");
  n += put_uint(buf + n, rhythm);
  buf[n++] = ',';
  n += put_uint(buf + n, cycles);
  buf[n++] = '\n';
  return n;
}

size_t led_msg_done(char* buf, uint8_t rhythm, uint16_t cycles_done) {
  size_t n = put_str(buf, "D,");
  n += put_uint(buf + n, rhythm);
  buf[n++] = ',';
  n += put_uint(buf + n, cycles_done);
  buf[n++] = '\n';
  return n;
}

size_t led_msg_button(char* buf, uint8_t rhythm) {
  size_t n = put_str(buf, "P,");
  n += put_uint(buf + n, rhythm);
  buf[n++] = '\n';
  return n;
}
