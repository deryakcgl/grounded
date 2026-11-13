"""Per-minute metrics and stress score (v2: weights learned from data).

For each HRV window (60 s):
  - breathing rate and breathing irregularity (from that minute's breaths)
  - RMSSD and heart rate (from the device)
  - stress score 0-100: 50 = your normal, higher = more stressed than your normal

The score is relative to the person's OWN normal (no absolute thresholds):
  z = (value - personal median) / personal spread   (median and MAD: robust to outliers)
  raw = sum of WEIGHTS[k] * z(k)
  score = 100 / (1 + e^-raw)          50 = your normal

Weights (v2) come from research/stress_v2.py: logistic regression on 15 WESAD subjects,
evaluated leave-one-subject-out (14/15 unseen subjects with AUC >= 0.8; v1 had 11/15).
HRV (RMSSD) has weight 0 on purpose: fitted freely, the model gave HIGH HRV a stress weight,
because WESAD's stress task is a spoken talk and talking inflates RMSSD. That is a shortcut
that would fail for silent everyday stress, so HRV may only count in the physiological
direction (low HRV = more tense) - and with that constraint the data gives it weight 0.
RMSSD is still measured, stored and shown; it's just not part of this score.
Limitation: excitement (e.g. laughing) raises heart rate too; the score measures tension /
arousal, and can't tell why.
v1 (hand-picked): 0.50 -ln RMSSD, 0.25 heart rate, 0.25 breathing irregularity.

The math lives in pure functions (window_features, baseline_stats, stress_score);
research/validate_subjects.py uses the SAME functions.

Usage:  python host/metrics.py
"""
import math
import sys
from datetime import datetime

import numpy as np

import db

WEIGHTS = {"hr_bpm": 0.506, "breath_cv": 0.178, "breath_rate": -0.059}   # v2, see above
WINDOW_S = 60.0
TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_metrics (
    ts           TEXT PRIMARY KEY,   -- end of the 60 s window (same as hrv.ts)
    breath_rate  REAL,               -- breaths / min
    breath_cv    REAL,               -- coefficient of variation of breath intervals (std/mean)
    holds        INTEGER,            -- breath holds starting in this minute
    rmssd_ms     REAL,
    hr_bpm       REAL,
    stress       REAL                -- 0-100, 50 = personal normal
);
"""


# --- Pure computation (database-independent; times in seconds, same clock) ---

def window_features(win_t, rmssd, hr, breath_t, breath_int, hold_t):
    """Features for each HRV window. Output: feature name -> array."""
    win_t, breath_t, breath_int, hold_t = map(np.asarray, (win_t, breath_t, breath_int, hold_t))
    rate, cv, holds = [], [], []
    for t in win_t:
        m = (breath_t > t - WINDOW_S) & (breath_t <= t)
        iv = breath_int[m]
        if len(iv) >= 3:
            rate.append(60.0 / iv.mean())
            cv.append(iv.std() / iv.mean())
        else:   # too few breaths: rate/irregularity not reliable
            rate.append(math.nan)
            cv.append(math.nan)
        holds.append(int(np.sum((hold_t > t - WINDOW_S) & (hold_t <= t))))
    rmssd = np.asarray(rmssd, dtype=float)
    return {
        "breath_rate": np.array(rate),
        "breath_cv": np.array(cv),
        "holds": np.array(holds),
        "rmssd_ms": rmssd,
        "hr_bpm": np.asarray(hr, dtype=float),
        "neg_ln_rmssd": -np.log(rmssd),
    }


def baseline_stats(features, mask=None, keys=None):
    """Personal normal: (median, spread) per feature. mask: which minutes count as normal.
    In production: the first days of data. In research: the calibration (baseline) segment.
    keys: which features (default: the ones in the score)."""
    stats = {}
    for k in (keys or WEIGHTS):
        x = features[k] if mask is None else features[k][mask]
        med = np.nanmedian(x)
        mad = 1.4826 * np.nanmedian(np.abs(x - med))   # 1.4826: makes MAD equal to std for a normal distribution
        stats[k] = (med, mad if mad > 0 else 1.0)
    return stats


def stress_score(features, stats):
    """0-100 stress score; 50 = personal normal."""
    raw = sum(w * np.nan_to_num((features[k] - stats[k][0]) / stats[k][1])
              for k, w in WEIGHTS.items())
    return 100.0 / (1.0 + np.exp(-raw))


# --- Database ---

def compute(conn):
    conn.executescript(SCHEMA)
    hrv = conn.execute("SELECT ts, rmssd_ms, hr_bpm FROM hrv ORDER BY ts").fetchall()
    if not hrv:
        return 0
    breaths = conn.execute("SELECT ts, interval_s FROM breaths ORDER BY ts").fetchall()
    holds = conn.execute("SELECT start_ts FROM holds ORDER BY start_ts").fetchall()

    def sec(ts):
        return datetime.strptime(ts, TS_FORMAT).timestamp()

    f = window_features([sec(r[0]) for r in hrv], [r[1] for r in hrv], [r[2] for r in hrv],
                        [sec(r[0]) for r in breaths], [r[1] for r in breaths],
                        [sec(r[0]) for r in holds])
    stress = stress_score(f, baseline_stats(f))   # v1: whole recording; later: past days

    def num(x):
        return None if math.isnan(x) else float(x)

    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO minute_metrics VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(hrv[i][0], num(f["breath_rate"][i]), num(f["breath_cv"][i]), int(f["holds"][i]),
              float(f["rmssd_ms"][i]), float(f["hr_bpm"][i]), float(stress[i]))
             for i in range(len(hrv))])
    return len(hrv)


def main():
    conn = db.connect()
    n = compute(conn)
    print(f"{n} minutes computed.\n")
    print(f"{'Time':<7}{'Stress':>7}{'RMSSD':>9}{'HR':>7}{'Breath':>8}{'Irreg.':>10}")
    for row in conn.execute("""
        SELECT strftime('%H:%M', ts), stress, rmssd_ms, hr_bpm, breath_rate, breath_cv
        FROM minute_metrics ORDER BY ts"""):
        hhmm, s, rm, hr, br, cv = row
        bar = "#" * int(s / 5)
        print(f"{hhmm:<7}{s:>6.0f} {rm:>6.0f}ms{hr:>6.0f}{(br or 0):>7.1f}{(cv or 0):>9.2f}  {bar}")


if __name__ == "__main__":
    sys.exit(main())
