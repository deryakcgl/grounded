// Heartbeat (R-peak) detector: simplified Pan-Tompkins with search-back.
// Python reference: research/beat_detector.py (the method is explained there).
// Memory: two ring buffers, 37 floats + 100 int32 = ~550 bytes.
//
// Written for a Cortex-M0+ (no FPU, no hardware divide): every float operation and every
// integer division/modulo is a library call (~50-470 cycles). The hot path therefore avoids
// '%' and '/', and the search-back compares integers instead of floats.
#pragma once
#include <stdint.h>
#include <string.h>

#include "biquad.h"
#include "filter_coeffs.h"

class BeatDetector {
 public:
  BeatDetector();

  // Process one raw ECG sample. Returns the sample index of an R peak if found, else -1.
  // The R peak is reported after the QRS ends (~100-200 ms delay), but the index is exact.
  int32_t update(float raw);

 private:
  static const int WIN = (int)(0.15f * ECG_FS);          // 150 ms moving-window integration
  static const int RAW = (int)(0.4f * ECG_FS);           // 400 ms of raw ECG (search-back)
  static const int32_t REFRACTORY = (int32_t)(0.25f * ECG_FS);
  static const int32_t MAX_QRS = (int32_t)(0.2f * ECG_FS);
  static const int32_t WARMUP = 2 * ECG_FS;
  static constexpr float INV_WIN = 1.0f / WIN;          // multiply instead of divide

  // Maps a float to an int32 with the SAME ordering: a < b  <=>  key(a) < key(b).
  // IEEE-754 floats are sign + magnitude. For positive floats the bit pattern, read as an
  // integer, already grows with the value. For negative floats it grows as the value
  // shrinks, so we flip the 31 magnitude bits to reverse that order.
  // memcpy is the standard-safe way to reinterpret bits; it compiles to a plain register move.
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
  int32_t raw_key_[RAW] = {};   // orderKey() of the raw ECG; only used to find the maximum
  int raw_i_ = RAW - 1;         // position of the newest raw sample

  float spk_ = 0.0f;
  float npk_ = 0.0f;
  float threshold_ = 0.0f;

  int32_t n_ = 0;
  bool in_qrs_ = false;
  int32_t qrs_start_ = 0;
  float qrs_mwi_peak_ = 0.0f;
  int32_t last_r_ = -1000000000;
};

// HRV (RMSSD) and heart rate from beat intervals; keeps no arrays, resets at each window end.
class HrvTracker {
 public:
  explicit HrvTracker(float window_s = 60.0f) : window_s_(window_s) {}

  // New beat interval (s). Returns true when a window is complete and a result is ready.
  bool update(float ibi_s);
  float rmssd() const { return rmssd_; }     // ms
  float heartRate() const { return hr_; }    // beats/min

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
