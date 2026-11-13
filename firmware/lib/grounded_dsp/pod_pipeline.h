#pragma once
#include <stddef.h>
#include <stdint.h>

#include "beat_detector.h"
#include "breath_detector.h"
#include "decimator.h"
#include "filter_coeffs.h"

class PodPipeline {
 public:
  typedef void (*Writer)(const char* text, size_t len);
  static_assert(ECG_FS % RESP_FS == 0, "frame rate must be a multiple of the respiration rate");

  typedef void (*BeatHook)();

  explicit PodPipeline(Writer write, BeatHook on_beat = nullptr) : write_(write), on_beat_(on_beat) {}

  void push(float resp, float ecg, uint8_t lead_off);

 private:
  void send(int len);

  Writer write_;
  BeatHook on_beat_;
  BreathDetector breath_;
  BeatDetector beat_;
  HrvTracker hrv_;
  Decimator<ECG_FS / RESP_FS> resp_dec_;
  int32_t n_ = 0;
  int32_t prev_beat_ = -1;
  int lead_off_ = -1;
  char line_[48];
};
