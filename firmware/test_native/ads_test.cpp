// Unit tests for lib/ads1292r: the driver against the simulated chip, frame parsing, the FIFO.
// Usage: ./ads_test   (exit code 0 = all passed)
#include <stdio.h>

#include "ads1292r.h"
#include "fake_ads1292r.h"
#include "spsc_fifo.h"

constexpr uint8_t FakeAds1292r::RESET_VALUES[];

static int g_failed = 0, g_checks = 0;
#define CHECK(cond)                                                \
  do {                                                             \
    g_checks++;                                                    \
    if (!(cond)) {                                                 \
      g_failed++;                                                  \
      printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);       \
    }                                                              \
  } while (0)

static void print_violations(const FakeAds1292r& chip) {
  for (const auto& v : chip.violations) printf("  datasheet rule broken: %s\n", v.c_str());
}

static void test_begin() {
  FakeAds1292r chip;
  Ads1292r ads(chip);
  CHECK(ads.begin() == Ads1292r::OK);
  CHECK(ads.id() == 0x73);
  print_violations(chip);
  CHECK(chip.violations.empty());                    // every timing / mode / must-bit rule kept
  for (uint8_t i = 0; i < Ads1292r::CONFIG_COUNT; i++) {
    const auto& s = Ads1292r::CONFIG[i];
    CHECK((chip.regs[s.reg] & s.mask) == (s.value & s.mask));
  }
  CHECK(chip.rdatac && chip.converting);             // ready to stream

  // Stream a few frames as the DRDY interrupt would
  chip.convert(123456, -654321, ads::IN2P_OFF);
  Ads1292r::Frame f;
  ads.readFrame(f);
  CHECK(f.valid && f.resp == 123456 && f.ecg == -654321 && f.lead_off == ads::IN2P_OFF);
  chip.convert(-1, ads::FULL_SCALE);
  ads.readFrame(f);
  CHECK(f.valid && f.resp == -1 && f.ecg == ads::FULL_SCALE && f.lead_off == 0);
  CHECK(chip.violations.empty());
  ads.readFrame(f);                                  // read again without a new DRDY
  CHECK(chip.violations.size() == 1);                // the fake notices
}

static void test_begin_errors() {
  {
    FakeAds1292r chip;
    chip.id = 0x53;                                  // ADS1292: same family, no respiration
    Ads1292r ads(chip);
    CHECK(ads.begin() == Ads1292r::WRONG_DEVICE);
  }
  {
    FakeAds1292r chip;
    chip.id = 0x00;                                  // nothing answers: MISO pulled low
    Ads1292r ads(chip);
    CHECK(ads.begin() == Ads1292r::NO_DEVICE);
  }
  {
    FakeAds1292r chip;
    chip.stuck_low = 0x20;                           // one data line bit broken... but the ID
    Ads1292r ads(chip);                              // 0x73 has bit 5 set, so it fails earlier
    CHECK(ads.begin() == Ads1292r::WRONG_DEVICE);
  }
  {
    FakeAds1292r chip;
    chip.stuck_low = 0x04;                           // bit 2: ID 0x73 doesn't use it, but
    Ads1292r ads(chip);                              // RLD_SENS = 0x2C does
    CHECK(ads.begin() == Ads1292r::VERIFY_FAILED);
    CHECK(ads.failedRegister() == ads::RLD_SENS);
  }
}

static void test_parse() {
  const uint8_t p1[3] = {0x7F, 0xFF, 0xFF}, p2[3] = {0x80, 0x00, 0x00}, p3[3] = {0xFF, 0xFF, 0xFF};
  CHECK(Ads1292r::signExtend24(p1) == 8388607);     // positive full scale
  CHECK(Ads1292r::signExtend24(p2) == -8388608);    // negative full scale
  CHECK(Ads1292r::signExtend24(p3) == -1);
  // status 1100 1111 1100 0000 ... -> all five lead-off bits set
  const uint8_t raw[9] = {0xCF, 0x80, 0x00, 0, 0, 1, 0xFF, 0xFF, 0xFE};
  Ads1292r::Frame f = Ads1292r::parseFrame(raw);
  CHECK(f.valid && f.lead_off == 0x1F && f.resp == 1 && f.ecg == -2);
  const uint8_t garbage[9] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  CHECK(!Ads1292r::parseFrame(garbage).valid);      // MISO stuck high: rejected
  // 1 code at gain 6 = 2.42 V / 6 / (2^23 - 1) = 0.048 uV
  CHECK(Ads1292r::ecgMillivoltsPerCode() > 4.80e-5f && Ads1292r::ecgMillivoltsPerCode() < 4.81e-5f);
}

static void test_fifo() {
  SpscFifo<int, 8> q;
  int v;
  CHECK(!q.pop(v));
  for (int i = 0; i < 8; i++) CHECK(q.push(i));
  CHECK(!q.push(99) && q.dropped() == 1);           // full: dropped and counted
  CHECK(q.size() == 8);
  for (int i = 0; i < 8; i++) CHECK(q.pop(v) && v == i);   // first in, first out
  CHECK(!q.pop(v));
  // Run long enough for the 16-bit counters to wrap around several times
  bool ok = true;
  int next_in = 0, next_out = 0;
  for (int round = 0; round < 150000; round++) {
    for (int k = 0; k < 1 + round % 3; k++) ok &= q.push(next_in++);
    while (q.pop(v)) ok &= (v == next_out++);
  }
  CHECK(ok && next_in == next_out && next_in > 3 * 65536);
}

int main() {
  test_begin();
  test_begin_errors();
  test_parse();
  test_fifo();
  printf("%d/%d checks passed\n", g_checks - g_failed, g_checks);
  return g_failed ? 1 : 0;
}
