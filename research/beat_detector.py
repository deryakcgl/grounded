"""Kalp atisi (R tepesi) dedektoru ve HRV: referans uygulama (STM32'ye tasinacak).

Kurallar (nefes dedektoruyle ayni):
- Ornekler tek tek islenir, sadece gecmise bakar.
- Iki kucuk halka tampon: 150 ms kayan ortalama (38 ornek) ve 400 ms ham EKG (100 ornek).
  float ile ~550 bayt; STM32C031'in 12 KB RAM'ine rahat sigar.
- Girdi: 250 Hz ham EKG.

Yontem: sadelestirilmis Pan-Tompkins (1985, EKG'de klasik yontem).
  1. Bant geciren filtre 5-15 Hz -> QRS kompleksinin enerjisi burada; nefes kaynakli
     taban kaymasi (<1 Hz) ve kas gurultusu (>40 Hz) atilir.
  2. Turev   -> QRS en dik egimli kisim; turev onu one cikarir.
  3. Kare    -> hepsi pozitif olur, buyuk egimler daha da buyur.
  4. 150 ms kayan ortalama -> QRS boyunca tek bir "tepecik" olusur.
  5. Uyarlanabilir esik: sinyal (SPK) ve gurultu (NPK) seviyeleri takip edilir,
     esik ikisinin arasinda durur.
  6. Tepecik esigi gecip geri indiginde QRS bulunmus demektir. Ama filtre ve kayan
     ortalama sinyali geciktirdigi icin gercek R bu anda coktan gecmistir. Bu yuzden
     ham EKG'nin son 400 ms'sini tutup geriye donup en buyuk noktayi ariyoruz
     (Pan-Tompkins'in "search back" fikri). Varsayim: R pozitif (elektrot yerlesimine bagli).
"""
import math


class BiquadCascade:
    """scipy'nin sos (ikinci derece bolum) formatindaki filtreyi ornek ornek uygular.
    Firmware'de de aynen boyle yazilacak: her bolum icin 2 durum degiskeni."""

    def __init__(self, sos):
        self.sos = [tuple(s) for s in sos]
        self.z = [[0.0, 0.0] for _ in self.sos]

    def update(self, x):
        for (b0, b1, b2, _a0, a1, a2), z in zip(self.sos, self.z):
            y = b0 * x + z[0]                 # Direct Form II Transposed
            z[0] = b1 * x - a1 * y + z[1]
            z[1] = b2 * x - a2 * y
            x = y
        return x


class BeatDetector:
    def __init__(self, sos, fs=250, refractory_s=0.25, window_s=0.15, warmup_s=2.0):
        self.fs = fs
        self.bp = BiquadCascade(sos)
        self.refractory = int(refractory_s * fs)      # en hizli kalp: dakikada 240
        self.max_qrs = int(0.2 * fs)                  # QRS en fazla ~200 ms surer
        self.warmup = int(warmup_s * fs)

        self.win = [0.0] * int(window_s * fs)         # halka tampon
        self.win_i = 0
        self.win_sum = 0.0
        self.prev_bp = 0.0

        self.raw = [0.0] * int(0.4 * fs)              # ham EKG halka tamponu (geri arama icin)

        self.spk = 0.0      # tipik QRS tepecigi yuksekligi
        self.npk = 0.0      # tipik gurultu seviyesi
        self.alpha_noise = 1.0 - math.exp(-1.0 / (1.0 * fs))
        self.threshold = 0.0

        self.n = 0
        self.in_qrs = False
        self.qrs_start = 0
        self.qrs_mwi_peak = 0.0
        self.last_r = -10 ** 9

    def update(self, x):
        """Bir EKG ornegi isle. R tepesi bulunursa indisini dondurur, yoksa None.
        Not: R'yi QRS bittikten sonra bildiririz (~100-200 ms gecikme); indis dogrudur."""
        n = self.n
        self.n += 1
        self.raw[n % len(self.raw)] = x

        y = self.bp.update(x)                         # 1. bant geciren
        d = y - self.prev_bp                          # 2. turev
        self.prev_bp = y
        sq = d * d                                    # 3. kare
        self.win_sum += sq - self.win[self.win_i]     # 4. kayan ortalama (O(1))
        self.win[self.win_i] = sq
        self.win_i = (self.win_i + 1) % len(self.win)
        mwi = self.win_sum / len(self.win)

        if n < self.warmup:                           # ilk 2 sn: seviyeleri ogren
            self.spk = max(self.spk, mwi)
            self.npk += self.alpha_noise * (mwi - self.npk)
            self.threshold = self.npk + 0.25 * (self.spk - self.npk)
            return None

        beat = None
        if not self.in_qrs:
            self.npk += self.alpha_noise * (mwi - self.npk)   # QRS disinda = gurultu
            if mwi > self.threshold and n - self.last_r > self.refractory:
                self.in_qrs = True
                self.qrs_start = n
                self.qrs_mwi_peak = mwi
        else:
            self.qrs_mwi_peak = max(self.qrs_mwi_peak, mwi)
            # QRS bitti: tepecik esigin yarisinin altina indi (histerezis) ya da cok uzun surdu
            if mwi < 0.5 * self.threshold or n - self.qrs_start > self.max_qrs:
                self.in_qrs = False
                self.spk = 0.125 * self.qrs_mwi_peak + 0.875 * self.spk
                beat = self._search_back(n)
                self.last_r = beat

        self.threshold = self.npk + 0.25 * (self.spk - self.npk)
        return beat

    def _search_back(self, n):
        """Ham EKG tamponunda, onceki R'ye karismadan, en buyuk ornegin indisi."""
        span = min(len(self.raw), n - self.last_r - 1)
        best_idx, best_val = n, -math.inf
        for i in range(n - span + 1, n + 1):
            v = self.raw[i % len(self.raw)]
            if v > best_val:
                best_val, best_idx = v, i
        return best_idx


class HrvTracker:
    """Atim araliklarindan (IBI) HRV hesaplar. Firmware'de dizi gerekmez:
    sadece toplam ve sayac tutulur, her pencere sonunda sifirlanir."""

    def __init__(self, window_s=60.0):
        self.window_s = window_s
        self.prev_ibi = None
        self.sum_sq = 0.0
        self.count = 0
        self.ibi_sum = 0.0
        self.ibi_count = 0
        self.elapsed = 0.0

    def update(self, ibi_s):
        """Yeni atim araligi (sn). Pencere dolunca (rmssd_ms, kalp_hizi) dondurur."""
        result = None
        self.elapsed += ibi_s

        valid = 0.3 <= ibi_s <= 2.0                   # fizyolojik aralik (30-200 atim/dk)
        if valid and self.prev_ibi is not None:
            # Ardisik araliklar %30'dan fazla farkliysa: kacirilmis ya da sahte atim
            if abs(ibi_s - self.prev_ibi) / self.prev_ibi < 0.3:
                diff_ms = (ibi_s - self.prev_ibi) * 1000.0
                self.sum_sq += diff_ms * diff_ms
                self.count += 1
        if valid:
            self.ibi_sum += ibi_s
            self.ibi_count += 1
        self.prev_ibi = ibi_s if valid else None

        if self.elapsed >= self.window_s:
            if self.count >= 10:
                rmssd = math.sqrt(self.sum_sq / self.count)
                hr = 60.0 * self.ibi_count / self.ibi_sum
                result = (rmssd, hr)
            self.sum_sq, self.count = 0.0, 0
            self.ibi_sum, self.ibi_count = 0.0, 0
            self.elapsed = 0.0
        return result
