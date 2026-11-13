// Cihaz -> host protokolu: her olay bir metin satiri.
// Host karsiligi: host/protocol.py (bu dosyayla birlikte degistir).
//
//   B,<t_ms>,<aralik_ms>          nefes
//   H,<t_ms>                      nefes tutma basladi (t = son nefes)
//   E,<t_ms>,<sure_ms>            nefes tutma bitti
//   V,<t_ms>,<rmssd_x10>,<hr_x10> HRV penceresi (60 sn); x10 = 0.1 hassasiyet
//
// t_ms: cihaz acildigindan beri milisaniye. Saat bilgisini host ekler.
// Neden sadece tam sayi? Cihazda float yazdirmak ~7 KB double kutuphanesi ceker
// (bkz. dsp_target_test). Neden tek tek atimlar yok? Bluetooth'ta her atimi
// gondermek pili tuketir; HRV'yi cihaz hesaplar, host sadece sonucu alir.
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
