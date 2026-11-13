import math


class BreathDetector:
    def __init__(self, fs=25, k=0.3, tau_fast_s=4.0, tau_slow_s=60.0,
                 floor=0.2, min_interval_s=1.5, hold_s=10.0, warmup_s=10.0,
                 hold_factor=2.0, interval_alpha=0.2):
        self.fs = fs
        self.k = k
        self.floor = floor
        self.min_interval = int(min_interval_s * fs)
        self.hold_samples = int(hold_s * fs)
        self.hold_factor = hold_factor
        self.interval_alpha = interval_alpha
        self.avg_interval = None
        self.hold_limit = self.hold_samples
        self.warmup = int(warmup_s * fs)

        self.alpha_fast = 1.0 - math.exp(-1.0 / (tau_fast_s * fs))
        self.alpha_slow = 1.0 - math.exp(-1.0 / (tau_slow_s * fs))

        self.env_fast = 0.0
        self.env_slow = 0.0
        self.below = False
        self.n = 0
        self.last_breath = None
        self.in_hold = False
        self.threshold = 0.0

    def update(self, x):
        events = []
        n = self.n
        self.n += 1

        a = abs(x)
        self.env_fast += self.alpha_fast * (a - self.env_fast)
        self.env_slow += self.alpha_slow * (a - self.env_slow)
        self.threshold = self.k * max(self.env_fast, self.floor * self.env_slow)

        if n < self.warmup:
            return events

        if x < -self.threshold:
            self.below = True
        elif x > self.threshold and self.below:
            self.below = False
            if self.last_breath is None or n - self.last_breath >= self.min_interval:
                ended_hold = self.in_hold
                if self.in_hold:
                    self.in_hold = False
                    events.append(("hold_end", n, (n - self.last_breath) / self.fs))
                interval = None if self.last_breath is None else (n - self.last_breath) / self.fs
                if interval is not None and not ended_hold:
                    self.avg_interval = interval if self.avg_interval is None else \
                        self.avg_interval + self.interval_alpha * (interval - self.avg_interval)
                    self.hold_limit = max(self.hold_samples,
                                          int(self.hold_factor * self.avg_interval * self.fs))
                events.append(("breath", n, interval))
                self.last_breath = n

        if (not self.in_hold and self.last_breath is not None
                and n - self.last_breath > self.hold_limit):
            self.in_hold = True
            events.append(("hold_start", self.last_breath))

        return events
