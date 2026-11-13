#include "pod_pipeline.h"

#include "protocol.h"

void PodPipeline::send(int len) {
  if (len > 0) write_(line_, (size_t)len);
}

void PodPipeline::push(float resp, float ecg, uint8_t lead_off) {
  const int32_t n = n_++;

  if (lead_off != lead_off_) {
    lead_off_ = lead_off;
    send(proto_lead_off(line_, sizeof line_, sample_to_ms(n, ECG_FS), lead_off));
  }

  const int32_t b = beat_.update(ecg);
  if (b >= 0) {
    if (on_beat_) on_beat_();
    if (prev_beat_ >= 0 && hrv_.update((float)(b - prev_beat_) / ECG_FS)) {
      send(proto_hrv(line_, sizeof line_, sample_to_ms(b, ECG_FS), hrv_.rmssd(), hrv_.heartRate()));
    }
    prev_beat_ = b;
  }

  float r;
  if (!resp_dec_.push(resp, r)) return;
  const uint8_t ev = breath_.update(r);
  const uint32_t t = sample_to_ms(breath_.lastBreathSample(), RESP_FS);
  if (ev & BreathDetector::EV_HOLD_END) {
    send(proto_hold_end(line_, sizeof line_, t, (uint32_t)(breath_.holdDuration() * 1000.0f + 0.5f)));
  }
  if ((ev & BreathDetector::EV_BREATH) && breath_.lastInterval() > 0.0f) {
    send(proto_breath(line_, sizeof line_, t, (uint32_t)(breath_.lastInterval() * 1000.0f + 0.5f)));
  }
  if (ev & BreathDetector::EV_HOLD_START) {
    send(proto_hold_start(line_, sizeof line_, sample_to_ms(breath_.holdStartSample(), RESP_FS)));
  }
}
