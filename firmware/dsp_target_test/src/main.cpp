// grounded_dsp'nin STM32 uzerindeki testi.
// Flash'a gomulu WESAD parcalarini isler, sonuclari Mac'teki C++ ile karsilastirir
// ve ornek basina islem suresini olcer.
#include <Arduino.h>

#include "beat_detector.h"
#include "breath_detector.h"
#include "test_vectors.h"

#define COUNT(a) (int)(sizeof(a) / sizeof((a)[0]))

// Gercek zaman butcesi: bir sonraki ornek gelmeden islemi bitirmeliyiz.
static const uint32_t RESP_BUDGET_US = 1000000 / RESP_FS;   // 40000 us
static const uint32_t ECG_BUDGET_US = 1000000 / ECG_FS;     // 4000 us

static bool check(const char* name, const int32_t* found, int n_found,
                  const int32_t* expected, int n_expected) {
  int same = 0;
  for (int i = 0; i < n_found && i < n_expected; i++) {
    if (found[i] == expected[i]) same++;
  }
  const bool ok = (n_found == n_expected) && (same == n_expected);
  Serial.print(name);
  Serial.print(": bulunan ");
  Serial.print(n_found);
  Serial.print(", beklenen ");
  Serial.print(n_expected);
  Serial.print(", ayni ");
  Serial.print(same);
  Serial.println(ok ? "  -> GECTI" : "  -> KALDI");
  return ok;
}

static void report_time(const char* name, uint32_t total_us, int n, uint32_t worst_us,
                        uint32_t budget_us) {
  Serial.print(name);
  Serial.print(": ornek basina ort. ");
  Serial.print(total_us / (uint32_t)n);
  Serial.print(" us, en kotu ");
  Serial.print(worst_us);
  Serial.print(" us (butce ");
  Serial.print(budget_us);
  // Yuzdeyi binde olarak tam sayi hesapla. Serial.print(float) ARKADA double kullanir
  // ve tek bir satir icin ~7 KB double kutuphanesini flash'a ceker!
  const uint32_t permille = (uint32_t)((uint64_t)total_us * 1000u / ((uint64_t)n * budget_us));
  Serial.print(" us, kullanim %");
  Serial.print(permille / 10);
  Serial.print('.');
  Serial.print(permille % 10);
  Serial.println(")");
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("=== grounded_dsp STM32 testi ===");

  // --- Solunum ---
  static int32_t breaths[COUNT(EXP_BREATHS) + 8];
  int n_breaths = 0;
  uint32_t total = 0, worst = 0;
  BreathDetector bd;
  for (int i = 0; i < COUNT(RESP_DATA); i++) {
    const float x = (float)RESP_DATA[i] * RESP_SCALE;
    const uint32_t t0 = micros();
    const uint8_t ev = bd.update(x);
    const uint32_t dt = micros() - t0;
    total += dt;
    if (dt > worst) worst = dt;
    if ((ev & BreathDetector::EV_BREATH) && n_breaths < COUNT(breaths)) {
      breaths[n_breaths++] = bd.lastBreathSample();
    }
  }
  const bool ok_resp = check("Nefes", breaths, n_breaths, EXP_BREATHS, COUNT(EXP_BREATHS));
  report_time("Nefes", total, COUNT(RESP_DATA), worst, RESP_BUDGET_US);

  // --- EKG ---
  static int32_t beats[COUNT(EXP_BEATS) + 8];
  int n_beats = 0;
  total = 0;
  worst = 0;
  BeatDetector kd;
  for (int i = 0; i < COUNT(ECG_DATA); i++) {
    const float x = (float)ECG_DATA[i] * ECG_SCALE;
    const uint32_t t0 = micros();
    const int32_t r = kd.update(x);
    const uint32_t dt = micros() - t0;
    total += dt;
    if (dt > worst) worst = dt;
    if (r >= 0 && n_beats < COUNT(beats)) beats[n_beats++] = r;
  }
  const bool ok_ecg = check("Atim", beats, n_beats, EXP_BEATS, COUNT(EXP_BEATS));
  report_time("Atim", total, COUNT(ECG_DATA), worst, ECG_BUDGET_US);

  Serial.println(ok_resp && ok_ecg ? "=== SONUC: GECTI ===" : "=== SONUC: KALDI ===");
}

void loop() {}
