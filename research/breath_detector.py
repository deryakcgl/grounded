"""Nefes dedektoru: referans uygulama (STM32'ye tasinacak).

Kurallar (firmware'e tasinabilsin diye):
- Ornekler TEK TEK islenir (update), dizi tutulmaz; sadece birkac sayi hafizada.
- Sadece gecmise bakar (nedensel): gelecekteki ornekleri bilmez.
- Girdi: 0.05-1.0 Hz bant geciren filtreden gecmis, 25 Hz solunum sinyali.

Yontem: uyarlanabilir esikli, histerezisli sifir gecisi.
- Sinyalin tipik genligini iki hareketli ortalama ile takip ederiz:
    env_fast (~4 sn)  -> esikler nefes derinligine hizla uyum saglar
    env_slow (~60 sn) -> nefes tutarken esik sifira inmesin diye taban
- Esik = K * max(env_fast, FLOOR * env_slow)
- Sinyal -esik'in altina inip sonra +esik'in ustune cikarsa: 1 nefes.
  (Termostat gibi: arada kalan kucuk dalgalanmalar sayilmaz.)
- HOLD_S saniyedir nefes yoksa: nefes tutma.
"""
import math


class BreathDetector:
    def __init__(self, fs=25, k=0.3, tau_fast_s=4.0, tau_slow_s=60.0,
                 floor=0.2, min_interval_s=1.5, hold_s=10.0, warmup_s=10.0):
        self.fs = fs
        self.k = k
        self.floor = floor
        self.min_interval = int(min_interval_s * fs)   # en hizli nefes: dakikada 40
        self.hold_samples = int(hold_s * fs)
        self.warmup = int(warmup_s * fs)

        # Ustel hareketli ortalama katsayilari: env += alpha * (|x| - env)
        self.alpha_fast = 1.0 - math.exp(-1.0 / (tau_fast_s * fs))
        self.alpha_slow = 1.0 - math.exp(-1.0 / (tau_slow_s * fs))

        self.env_fast = 0.0
        self.env_slow = 0.0
        self.below = False         # histerezis durumu: -esik'in altina indik mi?
        self.n = 0                 # islenen ornek sayisi (zaman sayaci)
        self.last_breath = None    # son nefesin ornek indisi
        self.in_hold = False
        self.threshold = 0.0       # grafik icin disariya acik

    def update(self, x):
        """Bir ornek isle. Olay listesi dondurur (cogu zaman bos).

        Olaylar:
          ("breath", n, aralik_sn)      yeni nefes; aralik = onceki nefesten bu yana
          ("hold_start", n_baslangic)   nefes tutma basladi (son nefesin zamani)
          ("hold_end", n, sure_sn)      nefes tutma bitti
        """
        events = []
        n = self.n
        self.n += 1

        a = abs(x)
        self.env_fast += self.alpha_fast * (a - self.env_fast)
        self.env_slow += self.alpha_slow * (a - self.env_slow)
        self.threshold = self.k * max(self.env_fast, self.floor * self.env_slow)

        if n < self.warmup:        # ortalamalar oturana kadar karar verme
            return events

        # --- Histerezisli gecis: once asagi, sonra yukari ---
        if x < -self.threshold:
            self.below = True
        elif x > self.threshold and self.below:
            self.below = False
            if self.last_breath is None or n - self.last_breath >= self.min_interval:
                if self.in_hold:
                    self.in_hold = False
                    events.append(("hold_end", n, (n - self.last_breath) / self.fs))
                interval = None if self.last_breath is None else (n - self.last_breath) / self.fs
                events.append(("breath", n, interval))
                self.last_breath = n

        # --- Nefes tutma: uzun suredir nefes yok ---
        if (not self.in_hold and self.last_breath is not None
                and n - self.last_breath > self.hold_samples):
            self.in_hold = True
            events.append(("hold_start", self.last_breath))

        return events
