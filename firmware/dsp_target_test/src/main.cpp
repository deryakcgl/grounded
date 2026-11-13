#include <Arduino.h>

#include "beat_detector.h"
#include "breath_detector.h"
#include "test_vectors.h"

#define COUNT(a) (int)(sizeof(a) / sizeof((a)[0]))

static const uint32_t RESP_BUDGET_US = 1000000 / RESP_FS;
static const uint32_t ECG_BUDGET_US = 1000000 / ECG_FS;

static uint32_t g_cyc_per_us_x100 = 4800;

static void calibrate() {
  const uint32_t iters = 480000;
  uint32_t n = iters;
  const uint32_t t0 = micros();
  __asm volatile(".syntax unified \n 1: subs %0, %0, #1 \n bne 1b \n .syntax divided"
                 : "+l"(n));
  const uint32_t us = micros() - t0;
  Serial.print("Core clock (configured): ");
  Serial.print(SystemCoreClock / 1000000);
  Serial.print(" MHz, measured: ~");
  g_cyc_per_us_x100 = iters * 300u / us;
  Serial.print(g_cyc_per_us_x100 / 100);
  Serial.print('.');
  Serial.print(g_cyc_per_us_x100 / 10 % 10);
  Serial.println(" MHz (3-cycle loop)");
}

static uint32_t to_cycles(uint32_t us) { return (uint32_t)((uint64_t)us * g_cyc_per_us_x100 / 100); }

static volatile float vf_a = 1.2345f, vf_b = 0.9876f, vf_r;
static volatile int32_t vi_a = 123457, vi_b = 37, vi_r;
static const int OPS_N = 2000;

#define TIME_LOOP(stmt)                              \
  ({                                                 \
    const uint32_t t0_ = micros();                   \
    for (int i_ = 0; i_ < OPS_N; i_++) { stmt; }     \
    micros() - t0_;                                  \
  })

static void report_op(const char* name, uint32_t us, uint32_t base_us) {
  Serial.print("  ");
  Serial.print(name);
  Serial.print(": ");
  const uint32_t dt = us > base_us ? us - base_us : 0;
  Serial.print(to_cycles(dt) / OPS_N);
  Serial.println(" cycles");
}

static void op_costs() {
  Serial.println("Cost per operation (loop overhead subtracted):");
  const uint32_t base = TIME_LOOP(vf_r = vf_a);
  report_op("float add   a + b", TIME_LOOP(vf_r = vf_a + vf_b), base);
  report_op("float mul   a * b", TIME_LOOP(vf_r = vf_a * vf_b), base);
  report_op("float div   a / b", TIME_LOOP(vf_r = vf_a / vf_b), base);
  report_op("float cmp   a > b", TIME_LOOP(vi_r = vf_a > vf_b), base);
  report_op("int32 mul   a * b", TIME_LOOP(vi_r = vi_a * vi_b), base);
  report_op("int32 div   a / b", TIME_LOOP(vi_r = vi_a / vi_b), base);
  report_op("int32 mod   a % b", TIME_LOOP(vi_r = vi_a % vi_b), base);
  report_op("micros()         ", TIME_LOOP(vi_r = (int32_t)micros()), base);
}

static bool check(const char* name, const int32_t* found, int n_found,
                  const int32_t* expected, int n_expected) {
  int same = 0;
  for (int i = 0; i < n_found && i < n_expected; i++) {
    if (found[i] == expected[i]) same++;
  }
  const bool ok = (n_found == n_expected) && (same == n_expected);
  Serial.print(name);
  Serial.print(": found ");
  Serial.print(n_found);
  Serial.print(", expected ");
  Serial.print(n_expected);
  Serial.print(", identical ");
  Serial.print(same);
  Serial.println(ok ? "  -> PASS" : "  -> FAIL");
  return ok;
}

struct Timing {
  uint32_t budget_us;
  uint32_t total = 0, worst = 0;
  uint32_t finish = 0;
  uint32_t max_queue = 0;
  int n = 0;

  explicit Timing(uint32_t b) : budget_us(b) {}

  void add(uint32_t dt) {
    total += dt;
    if (dt > worst) worst = dt;
    const uint32_t arrive = (uint32_t)n * budget_us;
    const uint32_t start = finish > arrive ? finish : arrive;
    const uint32_t queue = (start - arrive) / budget_us + 1;
    if (queue > max_queue) max_queue = queue;
    finish = start + dt;
    n++;
  }

  void report(const char* name) const {
    Serial.print(name);
    Serial.print(": avg ");
    Serial.print(total / (uint32_t)n);
    Serial.print(" us, worst ");
    Serial.print(worst);
    Serial.print(" us (budget ");
    Serial.print(budget_us);
    const uint32_t permille = (uint32_t)((uint64_t)total * 1000u / ((uint64_t)n * budget_us));
    Serial.print(" us, avg load ");
    Serial.print(permille / 10);
    Serial.print('.');
    Serial.print(permille % 10);
    Serial.print("%), FIFO depth needed: ");
    Serial.println(max_queue);
    const uint32_t avg_cyc = to_cycles(total) / (uint32_t)n, worst_cyc = to_cycles(worst);
    Serial.print("  ~ avg ");
    Serial.print(avg_cyc);
    Serial.print(" cycles (");
    Serial.print(avg_cyc / 48);
    Serial.print(" us at 48 MHz), worst ");
    Serial.print(worst_cyc);
    Serial.print(" cycles (");
    Serial.print(worst_cyc / 48);
    Serial.println(" us at 48 MHz)");
  }
};

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("=== grounded_dsp STM32 test ===");
  calibrate();
  op_costs();
  Serial.println();

  static int32_t breaths[COUNT(EXP_BREATHS) + 8];
  int n_breaths = 0;
  Timing resp_t(RESP_BUDGET_US);
  BreathDetector bd;
  for (int i = 0; i < COUNT(RESP_DATA); i++) {
    const float x = (float)RESP_DATA[i] * RESP_SCALE;
    const uint32_t t0 = micros();
    const uint8_t ev = bd.update(x);
    resp_t.add(micros() - t0);
    if ((ev & BreathDetector::EV_BREATH) && n_breaths < COUNT(breaths)) {
      breaths[n_breaths++] = bd.lastBreathSample();
    }
  }
  const bool ok_resp = check("Breath", breaths, n_breaths, EXP_BREATHS, COUNT(EXP_BREATHS));
  resp_t.report("Breath");

  static int32_t beats[COUNT(EXP_BEATS) + 8];
  int n_beats = 0;
  Timing ecg_t(ECG_BUDGET_US);
  BeatDetector bt;
  for (int i = 0; i < COUNT(ECG_DATA); i++) {
    const float x = (float)ECG_DATA[i] * ECG_SCALE;
    const uint32_t t0 = micros();
    const int32_t r = bt.update(x);
    ecg_t.add(micros() - t0);
    if (r >= 0 && n_beats < COUNT(beats)) beats[n_beats++] = r;
  }
  const bool ok_ecg = check("Beat", beats, n_beats, EXP_BEATS, COUNT(EXP_BEATS));
  ecg_t.report("Beat");

  Serial.println(ok_resp && ok_ecg ? "=== RESULT: PASS ===" : "=== RESULT: FAIL ===");
}

void loop() {}
