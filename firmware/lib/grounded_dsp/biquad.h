// Ikinci derece bolumlerden (biquad) olusan IIR filtre, ornek ornek.
// scipy'nin sos formatini kullanir: her satir {b0, b1, b2, a0, a1, a2}, a0 = 1.
// Python karsiligi: research/beat_detector.py -> BiquadCascade
#pragma once

template <int N>
class BiquadCascade {
 public:
  explicit BiquadCascade(const float (*sos)[6]) : sos_(sos) {}

  float update(float x) {
    for (int i = 0; i < N; i++) {
      const float* s = sos_[i];
      // Direct Form II Transposed: bolum basina 2 durum degiskeni
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
