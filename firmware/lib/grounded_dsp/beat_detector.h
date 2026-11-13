#pragma once
#include <stdint.h>
#include <string.h>

#include "biquad.h"
#include "filter_coeffs.h"

class BeatDetector {
 public:
  BeatDetector();

  int32_t update(float raw);

 private:
  static const int WIN = (int)(0.15f * ECG_FS);
  static const int RAW = (int)(0.4f * ECG_FS);
  static const int32_t REFRACTORY = (int32_t)(0.25f * ECG_FS);
  static const int32_t MAX_QRS = (int32_t)(0.2f * ECG_FS);
  static const int32_t WARMUP = 2 * ECG_FS;
  static constexpr float INV_WIN = 1.0f / WIN;

  static int32_t orderKey(float f) {
    int32_t i;
    memcpy(&i, &f, sizeof i);
    return i >= 0 ? i : i ^ 0x7FFFFFFF;
  }

  int32_t searchBack(int32_t n) const;

  BiquadCascade<ECG_SOS_N> filter_;
  float win_[WIN] = {};
  int win_i_ = 0;
  float win_sum_ = 0.0f;
  float prev_bp_ = 0.0f;
  int32_t raw_key_[RAW] = {};
  int raw_i_ = RAW - 1;

  float spk_ = 0.0f;
  float npk_ = 0.0f;
  float threshold_ = 0.0f;

  int32_t n_ = 0;
  bool in_qrs_ = false;
  int32_t qrs_start_ = 0;
  float qrs_mwi_peak_ = 0.0f;
  int32_t last_r_ = -1000000000;
};

class HrvTracker {
 public:
  explicit HrvTracker(float window_s = 60.0f) : window_s_(window_s) {}

  bool update(float ibi_s);
  float rmssd() const { return rmssd_; }
  float heartRate() const { return hr_; }

 private:
  float window_s_;
  float prev_ibi_ = -1.0f;
  float sum_sq_ = 0.0f;
  int32_t count_ = 0;
  float ibi_sum_ = 0.0f;
  int32_t ibi_count_ = 0;
  float elapsed_ = 0.0f;
  float rmssd_ = 0.0f;
  float hr_ = 0.0f;
};
