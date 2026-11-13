// grounded_dsp kutuphanesini bilgisayarda (Mac) calistiran test programi.
// Firmware ile AYNI .cpp dosyalarini derler; tek fark girdinin dosyadan gelmesi.
//
// Kullanim:
//   ./dsp_test resp <dosya>   -> her satira bir solunum ornegi (25 Hz)
//   ./dsp_test ecg  <dosya>   -> her satira bir EKG ornegi (250 Hz)
// Cikti (stdout, CSV): olay satirlari; research/compare_native.py okur.
#include <stdio.h>
#include <string.h>

#include "beat_detector.h"
#include "breath_detector.h"

static int run_resp(FILE* f) {
  BreathDetector det;
  float x;
  while (fscanf(f, "%f", &x) == 1) {
    const uint8_t ev = det.update(x);
    if (ev & BreathDetector::EV_HOLD_END)
      printf("hold_end,%d,%.3f\n", (int)det.lastBreathSample(), (double)det.holdDuration());
    if (ev & BreathDetector::EV_BREATH)
      printf("breath,%d,%.3f\n", (int)det.lastBreathSample(), (double)det.lastInterval());
    if (ev & BreathDetector::EV_HOLD_START)
      printf("hold_start,%d\n", (int)det.holdStartSample());
  }
  return 0;
}

static int run_ecg(FILE* f) {
  BeatDetector det;
  HrvTracker hrv;
  float x;
  int32_t prev = -1;
  while (fscanf(f, "%f", &x) == 1) {
    const int32_t r = det.update(x);
    if (r < 0) continue;
    printf("beat,%d\n", (int)r);
    if (prev >= 0 && hrv.update((float)(r - prev) / ECG_FS))
      printf("hrv,%d,%.2f,%.2f\n", (int)r, (double)hrv.rmssd(), (double)hrv.heartRate());
    prev = r;
  }
  return 0;
}

int main(int argc, char** argv) {
  if (argc != 3) {
    fprintf(stderr, "kullanim: %s resp|ecg <dosya>\n", argv[0]);
    return 2;
  }
  FILE* f = fopen(argv[2], "r");
  if (!f) {
    perror(argv[2]);
    return 1;
  }
  int rc = 2;
  if (strcmp(argv[1], "resp") == 0) rc = run_resp(f);
  if (strcmp(argv[1], "ecg") == 0) rc = run_ecg(f);
  fclose(f);
  return rc;
}
