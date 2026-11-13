// Device -> host protocol: one text line per event.
// Host counterpart: host/protocol.py (change both together).
//
//   B,<t_ms>,<interval_ms>        breath
//   H,<t_ms>                      breath hold started (t = last breath)
//   E,<t_ms>,<duration_ms>        breath hold ended
//   V,<t_ms>,<rmssd_x10>,<hr_x10> HRV window (60 s); x10 = 0.1 resolution
//
// t_ms: milliseconds since the device started. The host adds wall-clock time.
// Why integers only? Printing floats on the device pulls in ~7 KB of double-math library
// (see dsp_target_test). Why no individual beats? Sending every beat over Bluetooth
// drains the battery; the device computes HRV and the host only receives the result.
#pragma once
#include <stdint.h>
#include <stdio.h>

static inline uint32_t sample_to_ms(int32_t sample, uint32_t fs) {
  return (uint32_t)((uint64_t)sample * 1000u / fs);
}

static inline int proto_breath(char* buf, size_t n, uint32_t t_ms, uint32_t interval_ms) {
  return snprintf(buf, n, "B,%lu,%lu\n", (unsigned long)t_ms, (unsigned long)interval_ms);
}

static inline int proto_hold_start(char* buf, size_t n, uint32_t t_ms) {
  return snprintf(buf, n, "H,%lu\n", (unsigned long)t_ms);
}

static inline int proto_hold_end(char* buf, size_t n, uint32_t t_ms, uint32_t duration_ms) {
  return snprintf(buf, n, "E,%lu,%lu\n", (unsigned long)t_ms, (unsigned long)duration_ms);
}

static inline int proto_hrv(char* buf, size_t n, uint32_t t_ms, float rmssd_ms, float hr_bpm) {
  return snprintf(buf, n, "V,%lu,%lu,%lu\n", (unsigned long)t_ms,
                  (unsigned long)(rmssd_ms * 10.0f + 0.5f), (unsigned long)(hr_bpm * 10.0f + 0.5f));
}
