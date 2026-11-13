#pragma once
#include <stdint.h>

#include "biquad.h"
#include "filter_coeffs.h"

class BreathDetector {
 public:
  enum : uint8_t { EV_BREATH = 1, EV_HOLD_START = 2, EV_HOLD_END = 4 };

  BreathDetector();

  uint8_t update(float raw);

  int32_t lastBreathSample() const { return last_breath_; }
  float lastInterval() const { return last_interval_; }
  int32_t holdStartSample() const { return hold_start_; }
  float holdDuration() const { return hold_duration_; }
  float threshold() const { return threshold_; }

 private:
  static const int32_t MIN_INTERVAL = (int32_t)(1.5f * RESP_FS);
  static const int32_t HOLD_SAMPLES = 10 * RESP_FS;
  static constexpr float HOLD_FACTOR = 2.0f;
  static constexpr float INTERVAL_ALPHA = 0.2f;
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
  int32_t last_breath_ = -1;
  float last_interval_ = -1.0f;
  int32_t hold_start_ = -1;
  float hold_duration_ = 0.0f;
  float avg_interval_ = -1.0f;
  int32_t hold_limit_ = HOLD_SAMPLES;
};
