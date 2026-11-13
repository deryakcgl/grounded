#pragma once

template <int R>
class Decimator {
 public:
  bool push(float x, float& out) {
    sum_ += x;
    if (++n_ < R) return false;
    out = sum_ * INV_R;
    sum_ = 0.0f;
    n_ = 0;
    return true;
  }

 private:
  static constexpr float INV_R = 1.0f / R;
  float sum_ = 0.0f;
  int n_ = 0;
};
