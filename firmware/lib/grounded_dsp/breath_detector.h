// Nefes dedektoru: uyarlanabilir esikli, histerezisli sifir gecisi.
// Python karsiligi: research/breath_detector.py (yontemin aciklamasi orada).
// Fark: bu sinif bant geciren filtreyi de icinde barindirir; HAM solunum ornegi alir.
#pragma once
#include <stdint.h>

#include "biquad.h"
#include "filter_coeffs.h"

class BreathDetector {
 public:
  // update() donus degeri bu bayraklarin birlesimi (ayni ornekte birden fazla olabilir)
  enum : uint8_t { EV_BREATH = 1, EV_HOLD_START = 2, EV_HOLD_END = 4 };

  BreathDetector();

  uint8_t update(float raw);

  // Son olaya ait bilgiler
  int32_t lastBreathSample() const { return last_breath_; }
  float lastInterval() const { return last_interval_; }    // sn, ilk nefeste -1
  int32_t holdStartSample() const { return hold_start_; }
  float holdDuration() const { return hold_duration_; }     // sn
  float threshold() const { return threshold_; }

 private:
  static const int32_t MIN_INTERVAL = (int32_t)(1.5f * RESP_FS);   // dakikada en fazla 40
  static const int32_t HOLD_SAMPLES = 10 * RESP_FS;                 // 10 sn
  static const int32_t WARMUP = 10 * RESP_FS;
  static constexpr float K = 0.3f;
  static constexpr float FLOOR = 0.2f;

  BiquadCascade<RESP_SOS_N> filter_;
  float env_fast_ = 0.0f;
  float env_slow_ = 0.0f;
  float threshold_ = 0.0f;
  bool below_ = false;
  bool in_hold_ = false;
  int32_t n_ = 0;
  int32_t last_breath_ = -1;    // -1: henuz nefes yok
  float last_interval_ = -1.0f;
  int32_t hold_start_ = -1;
  float hold_duration_ = 0.0f;
};
