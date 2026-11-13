#include "beat_detector.h"

#include <math.h>

BeatDetector::BeatDetector() : filter_(ECG_SOS) {}

int32_t BeatDetector::update(float raw) {
  const int32_t n = n_++;
  raw_[n % RAW] = raw;

  const float y = filter_.update(raw);        // 1. bant geciren
  const float d = y - prev_bp_;                // 2. turev
  prev_bp_ = y;
  const float sq = d * d;                      // 3. kare
  win_sum_ += sq - win_[win_i_];               // 4. kayan ortalama
  win_[win_i_] = sq;
  win_i_ = (win_i_ + 1) % WIN;
  const float mwi = win_sum_ / WIN;

  if (n < WARMUP) {                            // ilk 2 sn: seviyeleri ogren
    if (mwi > spk_) spk_ = mwi;
    npk_ += BEAT_ALPHA_NOISE * (mwi - npk_);
    threshold_ = npk_ + 0.25f * (spk_ - npk_);
    return -1;
  }

  int32_t beat = -1;
  if (!in_qrs_) {
    npk_ += BEAT_ALPHA_NOISE * (mwi - npk_);   // QRS disinda = gurultu
    if (mwi > threshold_ && n - last_r_ > REFRACTORY) {
      in_qrs_ = true;
      qrs_start_ = n;
      qrs_mwi_peak_ = mwi;
    }
  } else {
    if (mwi > qrs_mwi_peak_) qrs_mwi_peak_ = mwi;
    // QRS bitti: tepecik esigin yarisinin altina indi ya da cok uzun surdu
    if (mwi < 0.5f * threshold_ || n - qrs_start_ > MAX_QRS) {
      in_qrs_ = false;
      spk_ = 0.125f * qrs_mwi_peak_ + 0.875f * spk_;
      beat = searchBack(n);
      last_r_ = beat;
    }
  }

  threshold_ = npk_ + 0.25f * (spk_ - npk_);
  return beat;
}

int32_t BeatDetector::searchBack(int32_t n) const {
  int32_t span = n - last_r_ - 1;
  if (span > RAW) span = RAW;
  int32_t best_idx = n;
  float best_val = -INFINITY;
  for (int32_t i = n - span + 1; i <= n; i++) {
    const float v = raw_[i % RAW];
    if (v > best_val) {
      best_val = v;
      best_idx = i;
    }
  }
  return best_idx;
}

bool HrvTracker::update(float ibi_s) {
  bool ready = false;
  elapsed_ += ibi_s;

  const bool valid = ibi_s >= 0.3f && ibi_s <= 2.0f;   // 30-200 atim/dk
  if (valid && prev_ibi_ > 0.0f) {
    // Ardisik araliklar %30'dan fazla farkliysa: kacirilmis ya da sahte atim
    if (fabsf(ibi_s - prev_ibi_) / prev_ibi_ < 0.3f) {
      const float diff_ms = (ibi_s - prev_ibi_) * 1000.0f;
      sum_sq_ += diff_ms * diff_ms;
      count_++;
    }
  }
  if (valid) {
    ibi_sum_ += ibi_s;
    ibi_count_++;
  }
  prev_ibi_ = valid ? ibi_s : -1.0f;

  if (elapsed_ >= window_s_) {
    if (count_ >= 10) {
      rmssd_ = sqrtf(sum_sq_ / (float)count_);
      hr_ = 60.0f * (float)ibi_count_ / ibi_sum_;
      ready = true;
    }
    sum_sq_ = 0.0f;
    count_ = 0;
    ibi_sum_ = 0.0f;
    ibi_count_ = 0;
    elapsed_ = 0.0f;
  }
  return ready;
}
