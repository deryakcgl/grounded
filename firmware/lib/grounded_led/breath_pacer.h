#pragma once
#include <stdint.h>

enum Phase : uint8_t { INHALE, HOLD_IN, EXHALE, HOLD_OUT, PHASE_COUNT };

struct Rhythm {
  const char* name;
  uint32_t ms[PHASE_COUNT];
};

extern const Rhythm RHYTHMS[];
extern const uint8_t RHYTHM_COUNT;
extern const char* const PHASE_NAMES[PHASE_COUNT];

class BreathPacer {
 public:
  enum : uint8_t { EV_PHASE = 1, EV_CYCLE = 2, EV_DONE = 4 };
  static constexpr float MIN_LEVEL = 0.02f;

  bool start(uint8_t rhythm, uint16_t cycles, uint32_t now_ms);
  void stop() { active_ = false; }

  uint8_t update(uint32_t now_ms);

  float level(uint32_t now_ms) const;

  bool active() const { return active_; }
  uint8_t rhythm() const { return rhythm_; }
  Phase phase() const { return phase_; }
  uint16_t cycles() const { return cycles_; }
  uint16_t cyclesDone() const { return done_; }

 private:
  uint32_t duration() const { return RHYTHMS[rhythm_].ms[phase_]; }

  bool active_ = false;
  uint8_t rhythm_ = 0;
  Phase phase_ = INHALE;
  uint32_t phase_start_ = 0;
  uint16_t cycles_ = 0;
  uint16_t done_ = 0;
};
