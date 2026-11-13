#include "breath_pacer.h"

const Rhythm RHYTHMS[] = {
    {"Box 4-4-4-4", {4000, 4000, 4000, 4000}},
    {"4-7-8", {4000, 7000, 8000, 0}},
    {"Relax 4-0-6-0", {4000, 0, 6000, 0}},   // 6 breaths/min, long exhale
};
const uint8_t RHYTHM_COUNT = sizeof(RHYTHMS) / sizeof(RHYTHMS[0]);

const char* const PHASE_NAMES[PHASE_COUNT] = {"INHALE", "HOLD_IN", "EXHALE", "HOLD_OUT"};

bool BreathPacer::start(uint8_t rhythm, uint16_t cycles, uint32_t now_ms) {
  if (rhythm >= RHYTHM_COUNT) return false;
  rhythm_ = rhythm;
  cycles_ = cycles;
  done_ = 0;
  phase_ = INHALE;
  phase_start_ = now_ms;
  active_ = true;
  return true;
}

uint8_t BreathPacer::update(uint32_t now_ms) {
  if (!active_) return 0;
  uint8_t events = 0;
  // 'while', not 'if': zero-length phases (HOLD_IN in Relax) are passed in the same call.
  // 'phase_start_ += duration' instead of '= now_ms': the rhythm doesn't drift by however
  // late this function happens to be called.
  while (now_ms - phase_start_ >= duration()) {
    phase_start_ += duration();
    phase_ = (Phase)(phase_ + 1);    // C++ has no ++ for enums
    if (phase_ == PHASE_COUNT) {     // wrap with a compare, not '%' (no hardware divide)
      phase_ = INHALE;
      done_++;
      events |= EV_CYCLE;
      if (cycles_ != 0 && done_ >= cycles_) {
        active_ = false;
        return events | EV_PHASE | EV_DONE;
      }
    }
    events |= EV_PHASE;
  }
  return events;
}

static float smoothstep(float t) { return t * t * (3.0f - 2.0f * t); }

float BreathPacer::level(uint32_t now_ms) const {
  if (!active_) return MIN_LEVEL;
  const uint32_t dur = duration();
  float t = dur == 0 ? 1.0f : (float)(now_ms - phase_start_) / (float)dur;
  if (t > 1.0f) t = 1.0f;
  float e;
  switch (phase_) {
    case INHALE: e = smoothstep(t); break;
    case HOLD_IN: e = 1.0f; break;
    case EXHALE: e = 1.0f - smoothstep(t); break;
    default: e = 0.0f; break;
  }
  return MIN_LEVEL + (1.0f - MIN_LEVEL) * e;
}
