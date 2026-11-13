#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <map>
#include <string>
#include <vector>

#include "ads1292r.h"
#include "pod_pipeline.h"
#include "wokwi-api.h"

static uint64_t g_now_ns = 0;
static std::vector<std::string> g_pin_names;
static std::vector<uint32_t> g_pin_level;
static std::map<pin_t, pin_watch_config_t> g_watch;
static spi_config_t g_spi;
static uint8_t* g_spi_buf = nullptr;
struct Timer { timer_config_t cfg; uint64_t period_ns, next_ns; bool repeat, active; };
static std::vector<Timer> g_timers;
static std::map<std::string, uint32_t> g_attr_override;
static std::vector<uint32_t> g_attr_value;
static std::vector<std::string> g_attr_name;
static bool g_drdy_fell = false;

extern "C" {
pin_t pin_init(const char* name, uint32_t mode) {
  g_pin_names.push_back(name);
  g_pin_level.push_back(mode == OUTPUT_LOW ? LOW : HIGH);
  return (pin_t)g_pin_names.size() - 1;
}
void pin_write(pin_t pin, uint32_t value) {
  if (g_pin_names[pin] == "DRDY" && g_pin_level[pin] == HIGH && value == LOW) g_drdy_fell = true;
  g_pin_level[pin] = value;
}
uint32_t pin_read(pin_t pin) { return g_pin_level[pin]; }
bool pin_watch(pin_t pin, pin_watch_config_t* config) {
  g_watch[pin] = *config;
  return true;
}
spi_dev_t spi_init(spi_config_t* config) {
  g_spi = *config;
  return 0;
}
void spi_start(spi_dev_t, uint8_t* buffer, uint32_t) { g_spi_buf = buffer; }
void spi_stop(spi_dev_t) { g_spi_buf = nullptr; }
timer_t timer_init(timer_config_t* config) {
  g_timers.push_back({*config, 0, 0, false, false});
  return (timer_t)g_timers.size() - 1;
}
void timer_start(timer_t t, uint32_t micros, bool repeat) {
  g_timers[t].period_ns = (uint64_t)micros * 1000;
  g_timers[t].next_ns = g_now_ns + g_timers[t].period_ns;
  g_timers[t].repeat = repeat;
  g_timers[t].active = true;
}
void timer_stop(timer_t t) { g_timers[t].active = false; }
uint64_t get_sim_nanos(void) { return g_now_ns; }
uint32_t attr_init(const char* name, uint32_t default_value) {
  auto it = g_attr_override.find(name);
  g_attr_value.push_back(it != g_attr_override.end() ? it->second : default_value);
  g_attr_name.push_back(name);
  return (uint32_t)g_attr_value.size() - 1;
}
uint32_t attr_read(uint32_t attr) { return g_attr_value[attr]; }
}

static pin_t pin_by_name(const char* name) {
  for (size_t i = 0; i < g_pin_names.size(); i++)
    if (g_pin_names[i] == name) return (pin_t)i;
  fprintf(stderr, "no pin %s\n", name);
  exit(1);
}

static void drive(pin_t pin, uint32_t value) {
  if (g_pin_level[pin] == value) return;
  g_pin_level[pin] = value;
  auto it = g_watch.find(pin);
  if (it != g_watch.end()) it->second.pin_change(it->second.user_data, pin, value);
}

static void advance_ns(uint64_t ns) {
  const uint64_t end = g_now_ns + ns;
  for (;;) {
    Timer* next = nullptr;
    for (auto& t : g_timers)
      if (t.active && t.next_ns <= end && (!next || t.next_ns < next->next_ns)) next = &t;
    if (!next) break;
    g_now_ns = next->next_ns;
    if (next->repeat) next->next_ns += next->period_ns;
    else next->active = false;
    next->cfg.callback(next->cfg.user_data);
  }
  g_now_ns = end;
}

class ChipBus : public Ads1292rBus {
 public:
  void select(bool active) override { drive(pin_by_name("CS"), active ? LOW : HIGH); }
  uint8_t transfer(uint8_t out) override {
    advance_ns(8000);
    if (!g_spi_buf) return 0xFF;
    const uint8_t miso = g_spi_buf[0];
    g_spi_buf[0] = out;
    g_spi.done(g_spi.user_data, g_spi_buf, 1);
    return miso;
  }
  void delayUs(uint32_t us) override { advance_ns((uint64_t)us * 1000); }
  void setReset(bool high) override { drive(pin_by_name("PWDN"), high ? HIGH : LOW); }
};

static std::string g_out;
static void capture(const char* text, size_t len) { g_out.append(text, len); }

struct Range { int32_t lo[2] = {INT32_MAX, INT32_MAX}, hi[2] = {INT32_MIN, INT32_MIN}; int invalid = 0; };
static Range collect(Ads1292r& adc, int n, int skip) {
  Range r;
  for (int got = 0; got < n + skip;) {
    advance_ns(50000);
    if (!g_drdy_fell) continue;
    g_drdy_fell = false;
    Ads1292r::Frame f;
    adc.readFrame(f);
    if (got++ < skip) continue;
    if (!f.valid) { r.invalid++; continue; }
    const int32_t v[2] = {f.resp, f.ecg};
    for (int c = 0; c < 2; c++) {
      if (v[c] < r.lo[c]) r.lo[c] = v[c];
      if (v[c] > r.hi[c]) r.hi[c] = v[c];
    }
  }
  return r;
}

static int selftest() {
  chip_init();
  ChipBus bus;
  Ads1292r adc(bus);
  if (adc.begin() != Ads1292r::OK) { printf("begin failed\n"); return 1; }
  uint8_t regs[ads::REG_COUNT];
  adc.readRegisters(regs);
  printf("registers:");
  for (int i = 0; i < ads::REG_COUNT; i++) printf(" %02X", regs[i]);
  printf("\n");
  if (adc.startTestSignal() != Ads1292r::OK) { printf("test signal setup failed\n"); return 1; }
  g_drdy_fell = false;
  const Range r = collect(adc, 750, ads::SETTLE_FRAMES);
  bool ok = r.invalid == 0;
  const char* names[2] = {"CH1 (resp)", "CH2 (ECG) "};
  for (int c = 0; c < 2; c++) {
    const int32_t pp = r.hi[c] - r.lo[c];
    const bool pass = Ads1292r::testSignalOk(pp, 6);
    ok &= pass;
    printf("test signal %s: min %d max %d, peak-to-peak %d (expected %d) %s\n", names[c], r.lo[c],
           r.hi[c], pp, 2 * Ads1292r::testSignalCodes(6), pass ? "PASS" : "FAIL");
  }
  if (adc.startNormal() != Ads1292r::OK) { printf("back to normal failed\n"); return 1; }
  const Range n = collect(adc, 500, ads::SETTLE_FRAMES);
  printf("electrodes again: ECG peak-to-peak %d codes (a real ECG, not the test square)\n", n.hi[1] - n.lo[1]);
  return ok ? 0 : 1;
}

int main(int argc, char** argv) {
  if (argc > 1 && strcmp(argv[1], "selftest") == 0) return selftest();
  const double seconds = argc > 1 ? atof(argv[1]) : 180;
  if (argc > 2) g_attr_override["heartRate"] = (uint32_t)atoi(argv[2]);
  if (argc > 3) g_attr_override["breathRate"] = (uint32_t)atoi(argv[3]);
  if (argc > 4) g_attr_override["hrvDepth"] = (uint32_t)atoi(argv[4]);
  double hold_from = -1, hold_to = -1;
  if (argc > 5) sscanf(argv[5], "%lf-%lf", &hold_from, &hold_to);
  if (argc > 6) g_attr_override["electrodeContact"] = (uint32_t)atoi(argv[6]);

  chip_init();
  ChipBus bus;
  Ads1292r adc(bus);
  const Ads1292r::Error err = adc.begin();
  printf("driver begin(): %s, id 0x%02X\n", err == Ads1292r::OK ? "OK" : "FAILED", adc.id());
  if (err != Ads1292r::OK) return 1;

  PodPipeline pipeline(capture);
  int settle = ads::SETTLE_FRAMES, frames = 0, invalid = 0;
  g_drdy_fell = false;
  size_t hold_attr = 0;
  while (hold_attr < g_attr_name.size() && g_attr_name[hold_attr] != "holdBreath") hold_attr++;
  while (g_now_ns < (uint64_t)(seconds * 1e9)) {
    const double t = g_now_ns / 1e9;
    g_attr_value[hold_attr] = (t >= hold_from && t < hold_to) ? 1 : 0;
    advance_ns(50000);
    if (!g_drdy_fell) continue;
    g_drdy_fell = false;
    Ads1292r::Frame f;
    adc.readFrame(f);
    frames++;
    if (settle > 0) { settle--; continue; }
    if (!f.valid) { invalid++; continue; }
    pipeline.push(f.resp * 1e-5f, f.ecg * Ads1292r::ecgMillivoltsPerCode(), f.lead_off);
  }

  int breaths = 0, holds = 0;
  std::string lead_off;
  double hr_sum = 0, rmssd_sum = 0;
  int hrv_n = 0;
  for (size_t pos = 0; pos < g_out.size();) {
    const size_t nl = g_out.find('\n', pos);
    const std::string line = g_out.substr(pos, nl - pos);
    pos = nl + 1;
    unsigned long t, a, b;
    if (line[0] == 'B') breaths++;
    if (line[0] == 'H') holds++;
    if (line[0] == 'L') lead_off += line + " ";
    if (sscanf(line.c_str(), "V,%lu,%lu,%lu", &t, &a, &b) == 3) {
      rmssd_sum += a / 10.0;
      hr_sum += b / 10.0;
      hrv_n++;
    }
  }
  printf("%d frames in %.0f s (%d invalid)\n", frames, seconds, invalid);
  printf("breaths: %d = %.1f /min, breath holds: %d, lead-off lines: %s\n", breaths,
         breaths * 60.0 / seconds, holds, lead_off.c_str());
  if (hrv_n) printf("HRV windows: %d, mean heart rate %.1f bpm, mean RMSSD %.1f ms\n",
                    hrv_n, hr_sum / hrv_n, rmssd_sum / hrv_n);
  return invalid == 0 ? 0 : 1;
}
