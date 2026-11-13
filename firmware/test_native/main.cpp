#include <stdio.h>
#include <string.h>

#include "beat_detector.h"
#include "breath_detector.h"
#include "protocol.h"

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

static int run_device(FILE* fr, FILE* fe) {
  static_assert(ECG_FS % RESP_FS == 0, "ECG rate must be a multiple of the respiration rate");
  BreathDetector breath;
  BeatDetector beat;
  HrvTracker hrv;
  int32_t prev_beat = -1;
  char line[48];
  float r, e;

  for (;;) {
    for (int k = 0; k < ECG_FS / RESP_FS; k++) {
      if (fscanf(fe, "%f", &e) != 1) return 0;
      const int32_t b = beat.update(e);
      if (b < 0) continue;
      if (prev_beat >= 0 && hrv.update((float)(b - prev_beat) / ECG_FS)) {
        proto_hrv(line, sizeof line, sample_to_ms(b, ECG_FS), hrv.rmssd(), hrv.heartRate());
        fputs(line, stdout);
      }
      prev_beat = b;
    }
    if (fscanf(fr, "%f", &r) != 1) return 0;
    const uint8_t ev = breath.update(r);
    const uint32_t t = sample_to_ms(breath.lastBreathSample(), RESP_FS);
    if (ev & BreathDetector::EV_HOLD_END) {
      proto_hold_end(line, sizeof line, t, (uint32_t)(breath.holdDuration() * 1000.0f + 0.5f));
      fputs(line, stdout);
    }
    if ((ev & BreathDetector::EV_BREATH) && breath.lastInterval() > 0.0f) {
      proto_breath(line, sizeof line, t, (uint32_t)(breath.lastInterval() * 1000.0f + 0.5f));
      fputs(line, stdout);
    }
    if (ev & BreathDetector::EV_HOLD_START) {
      proto_hold_start(line, sizeof line, sample_to_ms(breath.holdStartSample(), RESP_FS));
      fputs(line, stdout);
    }
  }
}

int main(int argc, char** argv) {
  if (argc == 4 && strcmp(argv[1], "device") == 0) {
    FILE* fr = fopen(argv[2], "r");
    FILE* fe = fopen(argv[3], "r");
    if (!fr || !fe) {
      perror("file");
      return 1;
    }
    const int rc = run_device(fr, fe);
    fclose(fr);
    fclose(fe);
    return rc;
  }
  if (argc != 3) {
    fprintf(stderr, "usage: %s resp|ecg <file> | device <resp> <ecg>\n", argv[0]);
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
