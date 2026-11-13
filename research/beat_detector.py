"""Heartbeat (R-peak) detector and HRV: reference implementation (ported to the STM32).

Rules (same as the breath detector):
- Samples are processed one at a time, looking only at the past.
- Two small ring buffers: 150 ms moving window (38 samples) and 400 ms of raw ECG (100 samples).
  ~550 bytes as float; fits easily in the STM32C031's 12 KB of RAM.
- Input: raw ECG at 250 Hz.

Method: simplified Pan-Tompkins (1985, the classic ECG method).
  1. Bandpass 5-15 Hz -> the QRS complex's energy lives here; baseline wander from
     breathing (<1 Hz) and muscle noise (>40 Hz) are removed.
  2. Derivative -> the QRS is the steepest part; the derivative emphasizes it.
  3. Square     -> everything becomes positive, large slopes grow even larger.
  4. 150 ms moving-window integration -> one "bump" per QRS.
  5. Adaptive threshold: signal (SPK) and noise (NPK) levels are tracked,
     the threshold sits between them.
  6. When the bump crosses the threshold and falls back, a QRS has been found. But the filter
     and the moving window delay the signal, so the true R peak has already passed. So we keep
     the last 400 ms of raw ECG and search back for the largest sample
     (Pan-Tompkins' "search back" idea). Assumption: R is positive (depends on electrode placement).
"""
import math


class BiquadCascade:
    """Applies a filter in scipy's sos (second-order sections) format, sample by sample.
    The firmware does exactly the same: 2 state variables per section."""

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
        self.refractory = int(refractory_s * fs)      # fastest heart: 240 per minute
        self.max_qrs = int(0.2 * fs)                  # a QRS lasts at most ~200 ms
        self.warmup = int(warmup_s * fs)

        self.win = [0.0] * int(window_s * fs)         # ring buffer
        self.inv_win = 1.0 / len(self.win)            # firmware multiplies instead of dividing
        self.win_i = 0
        self.win_sum = 0.0
        self.prev_bp = 0.0

        self.raw = [0.0] * int(0.4 * fs)              # raw ECG ring buffer (for search-back)

        self.spk = 0.0      # typical QRS bump height
        self.npk = 0.0      # typical noise level
        self.alpha_noise = 1.0 - math.exp(-1.0 / (1.0 * fs))
        self.threshold = 0.0

        self.n = 0
        self.in_qrs = False
        self.qrs_start = 0
        self.qrs_mwi_peak = 0.0
        self.last_r = -10 ** 9

    def update(self, x):
        """Process one ECG sample. Returns the R-peak index if found, else None.
        Note: R is reported after the QRS ends (~100-200 ms delay); the index is exact."""
        n = self.n
        self.n += 1
        self.raw[n % len(self.raw)] = x

        y = self.bp.update(x)                         # 1. bandpass
        d = y - self.prev_bp                          # 2. derivative
        self.prev_bp = y
        sq = d * d                                    # 3. square
        self.win_sum += sq - self.win[self.win_i]     # 4. moving-window integration (O(1))
        self.win[self.win_i] = sq
        self.win_i = (self.win_i + 1) % len(self.win)
        mwi = self.win_sum * self.inv_win

        if n < self.warmup:                           # first 2 s: learn the levels
            self.spk = max(self.spk, mwi)
            self.npk += self.alpha_noise * (mwi - self.npk)
            self.threshold = self.npk + 0.25 * (self.spk - self.npk)
            return None

        beat = None
        if not self.in_qrs:
            self.npk += self.alpha_noise * (mwi - self.npk)   # outside a QRS = noise
            if mwi > self.threshold and n - self.last_r > self.refractory:
                self.in_qrs = True
                self.qrs_start = n
                self.qrs_mwi_peak = mwi
        else:
            self.qrs_mwi_peak = max(self.qrs_mwi_peak, mwi)
            # QRS ended: bump fell below half the threshold (hysteresis) or lasted too long
            if mwi < 0.5 * self.threshold or n - self.qrs_start > self.max_qrs:
                self.in_qrs = False
                self.spk = 0.125 * self.qrs_mwi_peak + 0.875 * self.spk
                beat = self._search_back(n)
                self.last_r = beat

        self.threshold = self.npk + 0.25 * (self.spk - self.npk)
        return beat

    def _search_back(self, n):
        """Index of the largest sample in the raw ECG buffer, without reaching back into the previous R."""
        span = min(len(self.raw), n - self.last_r - 1)
        best_idx, best_val = n, -math.inf
        for i in range(n - span + 1, n + 1):
            v = self.raw[i % len(self.raw)]
            if v > best_val:
                best_val, best_idx = v, i
        return best_idx


class HrvTracker:
    """Computes HRV from inter-beat intervals (IBI). No arrays needed in firmware:
    only a sum and a counter, reset at the end of each window."""

    def __init__(self, window_s=60.0):
        self.window_s = window_s
        self.prev_ibi = None
        self.sum_sq = 0.0
        self.count = 0
        self.ibi_sum = 0.0
        self.ibi_count = 0
        self.elapsed = 0.0

    def update(self, ibi_s):
        """New beat interval (s). When the window is full, returns (rmssd_ms, heart_rate)."""
        result = None
        self.elapsed += ibi_s

        valid = 0.3 <= ibi_s <= 2.0                   # physiological range (30-200 beats/min)
        if valid and self.prev_ibi is not None:
            # Consecutive intervals differing by more than 30%: a missed or false beat
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
