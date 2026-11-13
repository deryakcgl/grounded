// Reduces the sample rate by R: averages R input samples into one output sample.
// Used for respiration: the ADS1292R samples both channels at 250 SPS, the breath detector
// runs at 25 Hz. Averaging is also a simple low-pass (anti-aliasing) filter; breathing is
// below 1 Hz, far from where it lets anything through.
#pragma once

template <int R>
class Decimator {
 public:
  // Returns true when an output sample is ready (every R inputs).
  bool push(float x, float& out) {
    sum_ += x;
    if (++n_ < R) return false;
    out = sum_ * INV_R;   // multiply, don't divide (no FPU, no hardware divide)
    sum_ = 0.0f;
    n_ = 0;
    return true;
  }

 private:
  static constexpr float INV_R = 1.0f / R;
  float sum_ = 0.0f;
  int n_ = 0;
};
