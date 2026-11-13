// The chest pod's signal chain, from ADC frames to protocol lines (protocol.h):
//   ECG (250 Hz)          -> BeatDetector -> HrvTracker -> "V" lines
//   respiration (250 Hz)  -> average of 10 -> 25 Hz -> BreathDetector -> "B" / "H" / "E" lines
//   lead-off bits         -> "L" line when they change
// Hardware-free: the pod firmware and the Mac's pod simulation (test_native/pod_sim.cpp)
// run this same code.
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "beat_detector.h"
#include "breath_detector.h"
#include "decimator.h"
#include "filter_coeffs.h"

class PodPipeline {
 public:
  typedef void (*Writer)(const char* text, size_t len);
  static_assert(ECG_FS % RESP_FS == 0, "frame rate must be a multiple of the respiration rate");

  explicit PodPipeline(Writer write) : write_(write) {}

  // One frame at ECG_FS. resp and ecg in any consistent units (the detectors adapt to the
  // signal level); ECG is passed in millivolts to match the data the detectors were tuned on.
  void push(float resp, float ecg, uint8_t lead_off);

 private:
  void send(int len);

  Writer write_;
  BreathDetector breath_;
  BeatDetector beat_;
  HrvTracker hrv_;
  Decimator<ECG_FS / RESP_FS> resp_dec_;
  int32_t n_ = 0;            // frames processed (ECG sample index)
  int32_t prev_beat_ = -1;
  int lead_off_ = -1;        // -1: not reported yet
  char line_[48];
};
