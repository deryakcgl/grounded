#include "breath_detector.h"

BreathDetector::BreathDetector() : filter_(RESP_SOS) {}

uint8_t BreathDetector::update(float raw) {
  const float x = filter_.update(raw);
  uint8_t events = 0;
  const int32_t n = n_++;

  const float a = x < 0.0f ? -x : x;
  env_fast_ += BREATH_ALPHA_FAST * (a - env_fast_);
  env_slow_ += BREATH_ALPHA_SLOW * (a - env_slow_);
  const float floor_level = FLOOR * env_slow_;
  threshold_ = K * (env_fast_ > floor_level ? env_fast_ : floor_level);

  if (n < WARMUP) return events;

  if (x < -threshold_) {
    below_ = true;
  } else if (x > threshold_ && below_) {
    below_ = false;
    if (last_breath_ < 0 || n - last_breath_ >= MIN_INTERVAL) {
      const bool ended_hold = in_hold_;
      if (in_hold_) {
        in_hold_ = false;
        hold_duration_ = (float)(n - last_breath_) / RESP_FS;
        events |= EV_HOLD_END;
      }
      last_interval_ = last_breath_ < 0 ? -1.0f : (float)(n - last_breath_) / RESP_FS;
      if (last_interval_ > 0.0f && !ended_hold) {
        avg_interval_ = avg_interval_ < 0.0f
                            ? last_interval_
                            : avg_interval_ + INTERVAL_ALPHA * (last_interval_ - avg_interval_);
        const int32_t limit = (int32_t)(HOLD_FACTOR * avg_interval_ * RESP_FS);
        hold_limit_ = limit > HOLD_SAMPLES ? limit : HOLD_SAMPLES;
      }
      last_breath_ = n;
      events |= EV_BREATH;
    }
  }

  if (!in_hold_ && last_breath_ >= 0 && n - last_breath_ > hold_limit_) {
    in_hold_ = true;
    hold_start_ = last_breath_;
    events |= EV_HOLD_START;
  }
  return events;
}
