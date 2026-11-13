"""Reads events from the device and writes them to the database.

Sources:
  sim     Virtual device: runs the firmware's C++ code on the Mac with WESAD data
          (firmware/test_native, "device" mode). Used while there is no real device.
  serial  (later) The real device, over a serial port.

Usage:
  python host/ingest.py --source sim --subject S2 --start "2026-11-12 09:00"

Re-loading the same data is safe: rows with an existing timestamp are skipped.
"""
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
    """Runs the virtual device and returns its protocol lines."""
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


def ingest(lines, start, conn):
    """Writes protocol lines to the database. Device time (ms) + start = wall-clock time."""
    def ts(t_ms):
        return (start + timedelta(milliseconds=t_ms)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    counts = {"breath": 0, "hold": 0, "hrv": 0, "lead_off": 0, "malformed": 0}
    with conn:   # one transaction: either everything is written or nothing
        for line in lines:
            if line.startswith("#"):        # debug text from the device
                continue
            ev = parse(line)
            if isinstance(ev, Breath):
                conn.execute("INSERT OR IGNORE INTO breaths VALUES (?, ?)",
                             (ts(ev.t_ms), ev.interval_ms / 1000))
                counts["breath"] += 1
            elif isinstance(ev, HoldStart):
                conn.execute("INSERT OR IGNORE INTO holds VALUES (?, NULL)", (ts(ev.t_ms),))
                counts["hold"] += 1
            elif isinstance(ev, HoldEnd):
                # The end is written to the most recent open hold
                conn.execute("""UPDATE holds SET duration_s = ?
                                WHERE start_ts = (SELECT MAX(start_ts) FROM holds
                                                  WHERE duration_s IS NULL AND start_ts <= ?)""",
                             (ev.duration_ms / 1000, ts(ev.t_ms)))
            elif isinstance(ev, LeadOff):
                counts["lead_off"] += 1     # not stored yet; will gate the metrics later
            elif isinstance(ev, Hrv):
                conn.execute("INSERT OR IGNORE INTO hrv VALUES (?, ?, ?)",
                             (ts(ev.t_ms), ev.rmssd_ms, ev.hr_bpm))
                counts["hrv"] += 1
            else:
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
