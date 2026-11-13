import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import db
from protocol import Breath, HoldEnd, HoldStart, Hrv, LeadOff, parse

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "firmware/test_native"


def sim_lines(subject):
    vec = ROOT / "data/vectors"
    vec.mkdir(exist_ok=True)
    resp_file, ecg_file = vec / f"{subject}_resp25.txt", vec / f"{subject}_ecg250.txt"
    if not (resp_file.exists() and ecg_file.exists()):
        d = np.load(ROOT / "data" / f"{subject}_prepared.npz")
        np.savetxt(resp_file, d["resp"], fmt="%.9g")
        np.savetxt(ecg_file, d["ecg"], fmt="%.9g")
    subprocess.run(["make", "-s", "-C", str(NATIVE)], check=True)
    out = subprocess.run([str(NATIVE / "dsp_test"), "device", str(resp_file), str(ecg_file)],
                         check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def store_event(conn, ev, ts):
    if isinstance(ev, Breath):
        conn.execute("INSERT OR IGNORE INTO breaths VALUES (?, ?)", (ts, ev.interval_ms / 1000))
        return "breath"
    if isinstance(ev, HoldStart):
        conn.execute("INSERT OR IGNORE INTO holds VALUES (?, NULL)", (ts,))
        return "hold"
    if isinstance(ev, HoldEnd):
        conn.execute("""UPDATE holds SET duration_s = ?
                        WHERE start_ts = (SELECT MAX(start_ts) FROM holds
                                          WHERE duration_s IS NULL AND start_ts <= ?)""",
                     (ev.duration_ms / 1000, ts))
        return "hold_end"
    if isinstance(ev, LeadOff):
        conn.execute("INSERT OR IGNORE INTO lead_off VALUES (?, ?)", (ts, ev.bits))
        return "lead_off"
    if isinstance(ev, Hrv):
        conn.execute("INSERT OR IGNORE INTO hrv VALUES (?, ?, ?)", (ts, ev.rmssd_ms, ev.hr_bpm))
        return "hrv"
    return None


def ts_text(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def ingest(lines, start, conn):
    counts = {"breath": 0, "hold": 0, "hrv": 0, "lead_off": 0, "malformed": 0}
    with conn:
        for line in lines:
            if line.startswith("#"):
                continue
            ev = parse(line)
            kind = store_event(conn, ev, ts_text(start + timedelta(milliseconds=ev.t_ms))) if ev else None
            if kind in counts:
                counts[kind] += 1
            elif kind is None:
                counts["malformed"] += 1
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim"], default="sim")
    ap.add_argument("--subject", default="S2")
    ap.add_argument("--start", default=datetime.now().strftime("%Y-%m-%d 09:00"),
                    help="Recording start time (default: today 09:00)")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    lines = sim_lines(args.subject)
    conn = db.connect()
    counts = ingest(lines, start, conn)
    print(f"Read: {counts['breath']} breaths, {counts['hold']} breath holds, "
          f"{counts['hrv']} HRV windows, {counts['malformed']} malformed lines")

    print("\nHourly summary (from the database):")
    rows = conn.execute("""
        SELECT strftime('%H:00', b.ts)          AS hour,
               COUNT(*) * 60.0 / SUM(b.interval_s) AS breaths_per_min,
               (SELECT AVG(rmssd_ms) FROM hrv WHERE strftime('%Y-%m-%d %H', hrv.ts)
                                                   = strftime('%Y-%m-%d %H', b.ts)) AS rmssd,
               (SELECT AVG(hr_bpm) FROM hrv WHERE strftime('%Y-%m-%d %H', hrv.ts)
                                                 = strftime('%Y-%m-%d %H', b.ts)) AS heart_rate
        FROM breaths b
        WHERE date(b.ts) = date(?)
        GROUP BY strftime('%Y-%m-%d %H', b.ts)
        ORDER BY hour""", (start.strftime("%Y-%m-%d"),)).fetchall()
    print(f"{'Hour':<7}{'Breaths':>11}{'RMSSD':>10}{'HR':>10}")
    for hour, breaths, rmssd, hr in rows:
        print(f"{hour:<7}{breaths:>7.1f}/min{rmssd:>7.0f} ms{hr:>6.0f}/min")
    print(f"\nDatabase: {db.DB_PATH}")


if __name__ == "__main__":
    sys.exit(main())
