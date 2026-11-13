import math
import sys
from datetime import datetime

import numpy as np

import db

WEIGHTS = {"hr_bpm": 0.506, "breath_cv": 0.178, "breath_rate": -0.059}
WINDOW_S = 60.0
TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_metrics (
    ts           TEXT PRIMARY KEY,
    breath_rate  REAL,
    breath_cv    REAL,
    holds        INTEGER,
    rmssd_ms     REAL,
    hr_bpm       REAL,
    stress       REAL
);
"""


def window_features(win_t, rmssd, hr, breath_t, breath_int, hold_t):
    win_t, breath_t, breath_int, hold_t = map(np.asarray, (win_t, breath_t, breath_int, hold_t))
    rate, cv, holds = [], [], []
    for t in win_t:
        m = (breath_t > t - WINDOW_S) & (breath_t <= t)
        iv = breath_int[m]
        if len(iv) >= 3:
            rate.append(60.0 / iv.mean())
            cv.append(iv.std() / iv.mean())
        else:
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
    stats = {}
    for k in (keys or WEIGHTS):
        x = features[k] if mask is None else features[k][mask]
        med = np.nanmedian(x)
        mad = 1.4826 * np.nanmedian(np.abs(x - med))
        stats[k] = (med, mad if mad > 0 else 1.0)
    return stats


def stress_score(features, stats):
    raw = sum(w * np.nan_to_num((features[k] - stats[k][0]) / stats[k][1])
              for k, w in WEIGHTS.items())
    return 100.0 / (1.0 + np.exp(-raw))


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
    stress = stress_score(f, baseline_stats(f))

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
