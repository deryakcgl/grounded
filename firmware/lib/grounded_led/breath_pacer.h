// Breathing pacer: which phase of a breathing rhythm we are in, and how bright the LED should be.
// Portable C++ (no Arduino calls): the desk LED firmware and the Mac's virtual LED
// (firmware/test_native/led_sim.cpp) run exactly the same code.
#pragma once
#include <stdint.h>

enum Phase : uint8_t { INHALE, HOLD_IN, EXHALE, HOLD_OUT, PHASE_COUNT };

struct Rhythm {
  const char* name;
  uint32_t ms[PHASE_COUNT];   // duration of each phase; 0 = phase is skipped
};

// Index = rhythm number in the protocol. At least one phase of every rhythm must be > 0.
extern const Rhythm RHYTHMS[];
extern const uint8_t RHYTHM_COUNT;
extern const char* const PHASE_NAMES[PHASE_COUNT];

class BreathPacer {
 public:
  // update() returns a combination of these flags
  enum : uint8_t { EV_PHASE = 1, EV_CYCLE = 2, EV_DONE = 4 };
  static constexpr float MIN_LEVEL = 0.02f;   // the LED never goes fully dark: shows it's on

  // Start guiding. cycles = 0: keep going until stop(). Returns false for an unknown rhythm.
  bool start(uint8_t rhythm, uint16_t cycles, uint32_t now_ms);
  void stop() { active_ = false; }

  // Advance to now_ms. Call often (every few ms); returns what happened since the last call.
  uint8_t update(uint32_t now_ms);

  // Brightness 0..1 as the eye should perceive it (gamma is applied by the LED driver).
  // Call after update() with the same now_ms.
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
