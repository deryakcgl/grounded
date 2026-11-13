// IIR filter made of second-order sections (biquads), sample by sample.
// Uses scipy's sos format: each row is {b0, b1, b2, a0, a1, a2}, a0 = 1.
// Python reference: research/beat_detector.py -> BiquadCascade
#pragma once

template <int N>
class BiquadCascade {
 public:
  explicit BiquadCascade(const float (*sos)[6]) : sos_(sos) {}

  float update(float x) {
    for (int i = 0; i < N; i++) {
      const float* s = sos_[i];
      // Direct Form II Transposed: 2 state variables per section
      float y = s[0] * x + z_[i][0];
      z_[i][0] = s[1] * x - s[4] * y + z_[i][1];
      z_[i][1] = s[2] * x - s[5] * y;
      x = y;
    }
    return x;
  }

 private:
  const float (*sos_)[6];
  float z_[N][2] = {};
};
