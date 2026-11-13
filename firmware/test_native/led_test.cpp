#include <math.h>
#include <stdio.h>
#include <string.h>

#include <string>

#include "breath_pacer.h"
#include "led_device.h"
#include "led_protocol.h"

static int g_failed = 0, g_checks = 0;

#define CHECK(cond)                                                \
  do {                                                             \
    g_checks++;                                                    \
    if (!(cond)) {                                                 \
      g_failed++;                                                  \
      printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);       \
    }                                                              \
  } while (0)

enum { BOX = 0, R478 = 1, RELAX = 2 };

static void test_pacer() {
  BreathPacer p;
  CHECK(!p.start(RHYTHM_COUNT, 1, 0));
  CHECK(p.start(BOX, 0, 1000));

  CHECK(p.update(4999) == 0 && p.phase() == INHALE);
  CHECK(p.update(5000) == BreathPacer::EV_PHASE && p.phase() == HOLD_IN);

  p.update(9100);
  CHECK(p.phase() == EXHALE);
  CHECK(p.update(12999) == 0);
  CHECK(p.update(13000) == BreathPacer::EV_PHASE && p.phase() == HOLD_OUT);

  p.update(1000 + 16000 * 2 + 3000);
  CHECK(p.cyclesDone() == 2 && p.phase() == INHALE);

  p.start(RELAX, 2, 0);
  CHECK(p.update(4000) == BreathPacer::EV_PHASE && p.phase() == EXHALE);
  CHECK(p.update(10000) == (BreathPacer::EV_PHASE | BreathPacer::EV_CYCLE));
  CHECK(p.phase() == INHALE && p.cyclesDone() == 1);
  const uint8_t ev = p.update(20000);
  CHECK(ev & BreathPacer::EV_DONE);
  CHECK(!p.active() && p.cyclesDone() == 2);
  CHECK(p.level(20000) == BreathPacer::MIN_LEVEL);

  p.start(BOX, 0, 0);
  p.update(2000);
  CHECK(fabsf(p.level(2000) - (0.02f + 0.98f * 0.5f)) < 1e-6f);
  p.update(5000);
  CHECK(p.level(5000) == 1.0f);
}

static void test_parser() {
  LedCommand c = parse_led_command("G,2,6");
  CHECK(c.type == LedCommand::GUIDE && c.rhythm == 2 && c.cycles == 6);
  CHECK(parse_led_command("G,0,0").type == LedCommand::GUIDE);
  CHECK(parse_led_command("X").type == LedCommand::STOP);
  CHECK(parse_led_command("?").type == LedCommand::STATUS);
  CHECK(parse_led_command("").type == LedCommand::NONE);
  const char* bad[] = {"G,2", "G,2,", "G,,6", "G,2,6x", "G,-1,6", "G,300,1",
                       "G,1,70000", "Xy", "g,1,1", "G 1 1", "hello"};
  for (const char* s : bad) {
    if (parse_led_command(s).type != LedCommand::INVALID) printf("  not rejected: '%s'\n", s);
    CHECK(parse_led_command(s).type == LedCommand::INVALID);
  }
}

static const char* feed_all(LineReader& r, const char* s) {
  const char* line = nullptr;
  for (; *s; s++) {
    if (const char* l = r.feed(*s)) line = l;
  }
  return line;
}

static void test_line_reader() {
  LineReader r;
  CHECK(r.feed('X') == nullptr);
  const char* l = r.feed('\n');
  CHECK(l && strcmp(l, "X") == 0);
  l = feed_all(r, "G,2,6\r\n");
  CHECK(l && strcmp(l, "G,2,6") == 0);
  std::string longline(LineReader::MAX + 5, 'A');
  CHECK(feed_all(r, (longline + "\n").c_str()) == nullptr);
  l = feed_all(r, "?\n");
  CHECK(l && strcmp(l, "?") == 0);
}

static void test_messages() {
  char b[LED_MSG_MAX];
  CHECK(std::string(b, led_msg_idle(b)) == "S,IDLE\n");
  CHECK(std::string(b, led_msg_guide(b, 2, 6)) == "S,GUIDE,2,6\n");
  CHECK(std::string(b, led_msg_done(b, 0, 65535)) == "D,0,65535\n");
  CHECK(std::string(b, led_msg_button(b, 1)) == "P,1\n");
}

static std::string g_out;
static void capture(const char* text, size_t len) { g_out.append(text, len); }
static std::string take() {
  std::string kept, line;
  for (char ch : g_out) {
    line += ch;
    if (ch == '\n') {
      if (line[0] != '#') kept += line;
      line.clear();
    }
  }
  g_out.clear();
  return kept;
}
static void send_line(LedDevice& d, const char* s, uint32_t now) {
  for (; *s; s++) d.onChar(*s, now);
  d.onChar('\n', now);
}

static void test_device() {
  LedDevice d(capture);
  d.begin();
  CHECK(take() == "S,IDLE\n");

  send_line(d, "G,2,2", 0);
  CHECK(take() == "S,GUIDE,2,2\n");
  d.tick(10000);
  CHECK(take() == "");
  d.tick(20000);
  CHECK(take() == "D,2,2\nS,IDLE\n");

  send_line(d, "G,7,1", 20000);
  CHECK(take() == "!,unknown rhythm\n");
  send_line(d, "nonsense", 20000);
  CHECK(take() == "!,bad command\n");

  send_line(d, "G,0,0", 30000);
  d.tick(30000 + 16000 + 100);
  take();
  send_line(d, "G,1,3", 50000);
  CHECK(take() == "D,0,1\nS,GUIDE,1,3\n");
  send_line(d, "X", 51000);
  CHECK(take() == "D,1,0\nS,IDLE\n");

  d.onButton(60000);
  CHECK(take() == "P,1\nS,GUIDE,1,6\n");
  d.onButton(61000);
  CHECK(take() == "D,1,0\nP,2\nS,GUIDE,2,6\n");
  send_line(d, "?", 62000);
  CHECK(take() == "S,GUIDE,2,6\n");
}

int main() {
  test_pacer();
  test_parser();
  test_line_reader();
  test_messages();
  test_device();
  printf("%d/%d checks passed\n", g_checks - g_failed, g_checks);
  return g_failed ? 1 : 0;
}
