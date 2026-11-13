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
  CHECK(chip.violations.empty());
  for (uint8_t i = 0; i < Ads1292r::CONFIG_COUNT; i++) {
    const auto& s = Ads1292r::CONFIG[i];
    CHECK((chip.regs[s.reg] & s.mask) == (s.value & s.mask));
  }
  CHECK(chip.rdatac && chip.converting);

  chip.convert(123456, -654321, ads::IN2P_OFF);
  Ads1292r::Frame f;
  ads.readFrame(f);
  CHECK(f.valid && f.resp == 123456 && f.ecg == -654321 && f.lead_off == ads::IN2P_OFF);
  chip.convert(-1, ads::FULL_SCALE);
  ads.readFrame(f);
  CHECK(f.valid && f.resp == -1 && f.ecg == ads::FULL_SCALE && f.lead_off == 0);
  CHECK(chip.violations.empty());
  ads.readFrame(f);
  CHECK(chip.violations.size() == 1);
}

static void test_begin_errors() {
  {
    FakeAds1292r chip;
    chip.id = 0x53;
    Ads1292r ads(chip);
    CHECK(ads.begin() == Ads1292r::WRONG_DEVICE);
  }
  {
    FakeAds1292r chip;
    chip.id = 0x00;
    Ads1292r ads(chip);
    CHECK(ads.begin() == Ads1292r::NO_DEVICE);
  }
  {
    FakeAds1292r chip;
    chip.stuck_low = 0x20;
    Ads1292r ads(chip);
    CHECK(ads.begin() == Ads1292r::WRONG_DEVICE);
  }
  {
    FakeAds1292r chip;
    chip.stuck_low = 0x04;
    Ads1292r ads(chip);
    CHECK(ads.begin() == Ads1292r::VERIFY_FAILED);
    CHECK(ads.failedRegister() == ads::RLD_SENS);
  }
}

static void test_bringup_helpers() {
  FakeAds1292r chip;
  Ads1292r ads(chip);
  CHECK(ads.begin() == Ads1292r::OK);
  uint8_t regs[ads::REG_COUNT];
  ads.readRegisters(regs);
  CHECK(regs[ads::ID] == 0x73 && regs[ads::CONFIG2] == 0xE0 && regs[ads::RESP1] == 0xEA);
  CHECK(!chip.converting && !chip.rdatac);
  CHECK(ads.startTestSignal() == Ads1292r::OK);
  CHECK(chip.regs[ads::CONFIG2] == 0xE3 && chip.regs[ads::CH1SET] == 0x05 && chip.regs[ads::CH2SET] == 0x05);
  CHECK(chip.rdatac && chip.converting);
  CHECK(ads.startNormal() == Ads1292r::OK);
  CHECK(chip.regs[ads::CONFIG2] == 0xE0 && chip.regs[ads::CH1SET] == 0x00 && chip.regs[ads::CH2SET] == 0x00);
  print_violations(chip);
  CHECK(chip.violations.empty());
  CHECK(Ads1292r::testSignalCodes(6) == 20971);
  CHECK(Ads1292r::testSignalOk(41942, 6) && Ads1292r::testSignalOk(38000, 6));
  CHECK(!Ads1292r::testSignalOk(0, 6) && !Ads1292r::testSignalOk(20971, 6));
}

static void test_parse() {
  const uint8_t p1[3] = {0x7F, 0xFF, 0xFF}, p2[3] = {0x80, 0x00, 0x00}, p3[3] = {0xFF, 0xFF, 0xFF};
  CHECK(Ads1292r::signExtend24(p1) == 8388607);
  CHECK(Ads1292r::signExtend24(p2) == -8388608);
  CHECK(Ads1292r::signExtend24(p3) == -1);
  const uint8_t raw[9] = {0xCF, 0x80, 0x00, 0, 0, 1, 0xFF, 0xFF, 0xFE};
  Ads1292r::Frame f = Ads1292r::parseFrame(raw);
  CHECK(f.valid && f.lead_off == 0x1F && f.resp == 1 && f.ecg == -2);
  const uint8_t garbage[9] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  CHECK(!Ads1292r::parseFrame(garbage).valid);
  CHECK(Ads1292r::ecgMillivoltsPerCode() > 4.80e-5f && Ads1292r::ecgMillivoltsPerCode() < 4.81e-5f);
}

static void test_fifo() {
  SpscFifo<int, 8> q;
  int v;
  CHECK(!q.pop(v));
  for (int i = 0; i < 8; i++) CHECK(q.push(i));
  CHECK(!q.push(99) && q.dropped() == 1);
  CHECK(q.size() == 8);
  for (int i = 0; i < 8; i++) CHECK(q.pop(v) && v == i);
  CHECK(!q.pop(v));
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
  test_bringup_helpers();
  test_parse();
  test_fifo();
  printf("%d/%d checks passed\n", g_checks - g_failed, g_checks);
  return g_failed ? 1 : 0;
}
