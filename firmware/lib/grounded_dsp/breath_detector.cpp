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

  if (n < WARMUP) return events;   // ortalamalar oturana kadar karar verme

  // Histerezisli gecis: once -esik'in altina, sonra +esik'in ustune
  if (x < -threshold_) {
    below_ = true;
  } else if (x > threshold_ && below_) {
    below_ = false;
    if (last_breath_ < 0 || n - last_breath_ >= MIN_INTERVAL) {
      if (in_hold_) {
        in_hold_ = false;
        hold_duration_ = (float)(n - last_breath_) / RESP_FS;
        events |= EV_HOLD_END;
      }
      last_interval_ = last_breath_ < 0 ? -1.0f : (float)(n - last_breath_) / RESP_FS;
      last_breath_ = n;
      events |= EV_BREATH;
    }
  }

  // Nefes tutma: uzun suredir nefes yok
  if (!in_hold_ && last_breath_ >= 0 && n - last_breath_ > HOLD_SAMPLES) {
    in_hold_ = true;
    hold_start_ = last_breath_;
    events |= EV_HOLD_START;
  }
  return events;
}
