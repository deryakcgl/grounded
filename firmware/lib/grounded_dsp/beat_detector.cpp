#include "beat_detector.h"

#include <math.h>

BeatDetector::BeatDetector() : filter_(ECG_SOS) {}

int32_t BeatDetector::update(float raw) {
  const int32_t n = n_++;
  if (++raw_i_ == RAW) raw_i_ = 0;
  raw_key_[raw_i_] = orderKey(raw);

  const float y = filter_.update(raw);
  const float d = y - prev_bp_;
  prev_bp_ = y;
  const float sq = d * d;
  win_sum_ += sq - win_[win_i_];
  win_[win_i_] = sq;
  if (++win_i_ == WIN) win_i_ = 0;
  const float mwi = win_sum_ * INV_WIN;

  if (n < WARMUP) {
    if (mwi > spk_) spk_ = mwi;
    npk_ += BEAT_ALPHA_NOISE * (mwi - npk_);
    threshold_ = npk_ + 0.25f * (spk_ - npk_);
    return -1;
  }

  int32_t beat = -1;
  if (!in_qrs_) {
    npk_ += BEAT_ALPHA_NOISE * (mwi - npk_);
    if (mwi > threshold_ && n - last_r_ > REFRACTORY) {
      in_qrs_ = true;
      qrs_start_ = n;
      qrs_mwi_peak_ = mwi;
    }
  } else {
    if (mwi > qrs_mwi_peak_) qrs_mwi_peak_ = mwi;
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
  if (span < 1) return n;
  int pos = raw_i_ - (int)(span - 1);
  if (pos < 0) pos += RAW;
  int32_t best_k = 0;
  int32_t best_key = raw_key_[pos];
  for (int32_t k = 1; k < span; k++) {
    if (++pos == RAW) pos = 0;
    if (raw_key_[pos] > best_key) {
      best_key = raw_key_[pos];
      best_k = k;
    }
  }
  return n - span + 1 + best_k;
}

bool HrvTracker::update(float ibi_s) {
  bool ready = false;
  elapsed_ += ibi_s;

  const bool valid = ibi_s >= 0.3f && ibi_s <= 2.0f;
  if (valid && prev_ibi_ > 0.0f) {
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
