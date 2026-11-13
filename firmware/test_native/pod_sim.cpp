// The whole chest pod on the Mac, with a simulated ADS1292R instead of the real chip:
//   WESAD samples -> ADC codes in the fake chip -> driver reads frames in a simulated DRDY
//   interrupt -> FIFO -> "main loop" -> PodPipeline -> protocol lines on stdout
// The output should match "dsp_test device" (same data without the chip, driver and FIFO);
// research/compare_pod.py checks that.
//
// Usage: ./pod_sim <resp25.txt> <ecg250.txt>
#include <math.h>
#include <stdio.h>

#include "ads1292r.h"
#include "fake_ads1292r.h"
#include "pod_pipeline.h"
#include "spsc_fifo.h"

constexpr uint8_t FakeAds1292r::RESET_VALUES[];

// Respiration has no physical unit here (impedance change in arbitrary ADC units); the
// detectors adapt to the signal level. 1e5 codes per WESAD unit uses ~60% of the ADC range.
static const double RESP_CODES_PER_UNIT = 1e5;
static const float RESP_UNITS_PER_CODE = 1e-5f;
static const int DRAIN_EVERY = 7;   // the main loop runs only every 7th frame: the FIFO must buffer

static FakeAds1292r chip;
static Ads1292r adc(chip);
static SpscFifo<Ads1292r::Frame, 32> fifo;
static uint16_t max_fill = 0;

static void write_stdout(const char* text, size_t len) { fwrite(text, 1, len, stdout); }
static PodPipeline pipeline(write_stdout);

static int32_t to_code(double v) {
  const double c = round(v);
  return (int32_t)(c > ads::FULL_SCALE ? ads::FULL_SCALE : c < -ads::FULL_SCALE - 1 ? -ads::FULL_SCALE - 1 : c);
}

// What the DRDY interrupt does on the board
static void on_drdy() {
  Ads1292r::Frame f;
  adc.readFrame(f);
  fifo.push(f);
  if (fifo.size() > max_fill) max_fill = fifo.size();
}

// What loop() does on the board
static int settle = ads::SETTLE_FRAMES;
static void main_loop() {
  Ads1292r::Frame f;
  while (fifo.pop(f)) {
    if (settle > 0) {   // first frames after START are not settled yet: drop them
      settle--;
      continue;
    }
    if (!f.valid) continue;
    pipeline.push(f.resp * RESP_UNITS_PER_CODE, f.ecg * Ads1292r::ecgMillivoltsPerCode(), f.lead_off);
  }
}

int main(int argc, char** argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s <resp25.txt> <ecg250.txt>\n", argv[0]);
    return 2;
  }
  FILE* fr = fopen(argv[1], "r");
  FILE* fe = fopen(argv[2], "r");
  if (!fr || !fe) {
    perror("file");
    return 1;
  }

  const Ads1292r::Error err = adc.begin();
  if (err != Ads1292r::OK || !chip.violations.empty()) {
    fprintf(stderr, "begin() failed: error %d, %zu datasheet violations\n", err, chip.violations.size());
    return 1;
  }

  // The settling frames (garbage on a real chip), then the data
  long frames = 0;
  for (int i = 0; i < ads::SETTLE_FRAMES; i++, frames++) {
    chip.convert(0, 0);
    on_drdy();
  }
  const double mv_per_code = (double)Ads1292r::ecgMillivoltsPerCode();
  float r, e;
  for (bool more = true; more;) {
    if (fscanf(fr, "%f", &r) != 1) break;
    const int32_t resp_code = to_code((double)r * RESP_CODES_PER_UNIT);
    for (int k = 0; k < ECG_FS / RESP_FS; k++) {   // the chip samples respiration at 250 SPS too
      if (fscanf(fe, "%f", &e) != 1) { more = false; break; }
      chip.convert(resp_code, to_code((double)e / mv_per_code));
      on_drdy();
      if (++frames % DRAIN_EVERY == 0) main_loop();
    }
  }
  main_loop();

  fprintf(stderr, "pod_sim: %ld frames, FIFO max fill %u/32, dropped %u, datasheet violations %zu\n",
          frames, max_fill, (unsigned)fifo.dropped(), chip.violations.size());
  return chip.violations.empty() && fifo.dropped() == 0 ? 0 : 1;
}
