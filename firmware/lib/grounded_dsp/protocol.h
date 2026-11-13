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

static inline int proto_lead_off(char* buf, size_t n, uint32_t t_ms, uint8_t bits) {
  return snprintf(buf, n, "L,%lu,%u\n", (unsigned long)t_ms, (unsigned)bits);
}

static inline int proto_hrv(char* buf, size_t n, uint32_t t_ms, float rmssd_ms, float hr_bpm) {
  return snprintf(buf, n, "V,%lu,%lu,%lu\n", (unsigned long)t_ms,
                  (unsigned long)(rmssd_ms * 10.0f + 0.5f), (unsigned long)(hr_bpm * 10.0f + 0.5f));
}
