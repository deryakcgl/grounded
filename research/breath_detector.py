"""Breath detector: reference implementation (ported to the STM32).

Rules (so it can move to firmware):
- Samples are processed ONE AT A TIME (update); no arrays, just a few numbers in memory.
- Looks only at the past (causal): it never sees future samples.
- Input: 25 Hz respiration signal, already through the 0.05-1.0 Hz bandpass.

Method: zero crossing with an adaptive threshold and hysteresis.
- The signal's typical amplitude is tracked with two moving averages:
    env_fast (~4 s)  -> the threshold adapts quickly to breathing depth
    env_slow (~60 s) -> a floor so the threshold doesn't drop to zero during a breath hold
- threshold = K * max(env_fast, FLOOR * env_slow)
- Signal drops below -threshold and then rises above +threshold: 1 breath.
  (Like a thermostat: small wiggles in between are ignored.)
- No breath for HOLD_S seconds: breath hold.
"""
import math


class BreathDetector:
    def __init__(self, fs=25, k=0.3, tau_fast_s=4.0, tau_slow_s=60.0,
                 floor=0.2, min_interval_s=1.5, hold_s=10.0, warmup_s=10.0):
        self.fs = fs
        self.k = k
        self.floor = floor
        self.min_interval = int(min_interval_s * fs)   # fastest breathing: 40 per minute
        self.hold_samples = int(hold_s * fs)
        self.warmup = int(warmup_s * fs)

        # Exponential moving-average coefficients: env += alpha * (|x| - env)
        self.alpha_fast = 1.0 - math.exp(-1.0 / (tau_fast_s * fs))
        self.alpha_slow = 1.0 - math.exp(-1.0 / (tau_slow_s * fs))

        self.env_fast = 0.0
        self.env_slow = 0.0
        self.below = False         # hysteresis state: have we gone below -threshold?
        self.n = 0                 # samples processed (time counter)
        self.last_breath = None    # sample index of the last breath
        self.in_hold = False
        self.threshold = 0.0       # exposed for plotting

    def update(self, x):
        """Process one sample. Returns a list of events (usually empty).

        Events:
          ("breath", n, interval_s)     new breath; interval = time since the previous breath
          ("hold_start", n_start)       breath hold started (time of the last breath)
          ("hold_end", n, duration_s)   breath hold ended
        """
        events = []
        n = self.n
        self.n += 1

        a = abs(x)
        self.env_fast += self.alpha_fast * (a - self.env_fast)
        self.env_slow += self.alpha_slow * (a - self.env_slow)
        self.threshold = self.k * max(self.env_fast, self.floor * self.env_slow)

        if n < self.warmup:        # no decisions until the averages settle
            return events

        # --- Crossing with hysteresis: first down, then up ---
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

        # --- Breath hold: no breath for a long time ---
        if (not self.in_hold and self.last_breath is not None
                and n - self.last_breath > self.hold_samples):
            self.in_hold = True
            events.append(("hold_start", self.last_breath))

        return events
