// Breath detector: zero crossing with an adaptive threshold and hysteresis.
// Python reference: research/breath_detector.py (the method is explained there).
// Difference: this class also contains the bandpass filter; it takes RAW respiration samples.
#pragma once
#include <stdint.h>

#include "biquad.h"
#include "filter_coeffs.h"

class BreathDetector {
 public:
  // update() returns a combination of these flags (several can occur on the same sample)
  enum : uint8_t { EV_BREATH = 1, EV_HOLD_START = 2, EV_HOLD_END = 4 };

  BreathDetector();

  uint8_t update(float raw);

  // Details of the most recent events
  int32_t lastBreathSample() const { return last_breath_; }
  float lastInterval() const { return last_interval_; }    // s, -1 on the first breath
  int32_t holdStartSample() const { return hold_start_; }
  float holdDuration() const { return hold_duration_; }     // s
  float threshold() const { return threshold_; }

 private:
  static const int32_t MIN_INTERVAL = (int32_t)(1.5f * RESP_FS);   // at most 40 per minute
  static const int32_t HOLD_SAMPLES = 10 * RESP_FS;                 // 10 s
  static const int32_t WARMUP = 10 * RESP_FS;
  static constexpr float K = 0.3f;
  static constexpr float FLOOR = 0.2f;

  BiquadCascade<RESP_SOS_N> filter_;
  float env_fast_ = 0.0f;
  float env_slow_ = 0.0f;
  float threshold_ = 0.0f;
  bool below_ = false;
  bool in_hold_ = false;
  int32_t n_ = 0;
  int32_t last_breath_ = -1;    // -1: no breath yet
  float last_interval_ = -1.0f;
  int32_t hold_start_ = -1;
  float hold_duration_ = 0.0f;
};
