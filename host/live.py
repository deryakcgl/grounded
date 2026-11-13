import argparse
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import db
from coach import SCHEMA as COACH_SCHEMA, TS_FORMAT, Coach, bar
from ingest import store_event, ts_text
from led import open_led
from metrics import compute
from protocol import Hrv, LeadOff, parse

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "firmware/test_native"
MIN_HISTORY_MIN = 30


class SerialPod:
    def __init__(self, port):
        import serial
        self.ser = serial.Serial(port, 115200, timeout=0.5)
        self.lines = queue.Queue()
        self.done = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            raw = self.ser.readline()
            if raw:
                self.lines.put(raw.decode(errors="replace").strip())

    def now(self):
        return datetime.now()


class SimPod:
    def __init__(self, subject, speed):
        subprocess.run(["make", "-s", "-C", str(NATIVE), "pod_sim"], check=True)
        d = np.load(ROOT / "data" / f"{subject}_prepared.npz")
        vec = ROOT / "data/vectors"
        vec.mkdir(exist_ok=True)
        self.rf, self.ef = vec / f"live_{subject}_resp.txt", vec / f"live_{subject}_ecg.txt"
        np.savetxt(self.rf, d["resp"], fmt="%.9g")
        np.savetxt(self.ef, d["ecg"], fmt="%.9g")
        self.proc = subprocess.Popen([str(NATIVE / "pod_sim"), str(self.rf), str(self.ef)],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.speed, self.real0, self.start = speed, time.monotonic(), datetime.now()
        self.lines = queue.Queue()
        self.done = False
        threading.Thread(target=self._pace, daemon=True).start()

    def _pace(self):
        for line in self.proc.stdout:
            ev = parse(line)
            if ev is not None:
                delay = ev.t_ms / 1000 / self.speed - (time.monotonic() - self.real0)
                if delay > 0:
                    time.sleep(delay)
            self.lines.put(line.strip())
        self.rf.unlink(missing_ok=True)
        self.ef.unlink(missing_ok=True)
        self.done = True

    def now(self):
        return self.start + timedelta(seconds=(time.monotonic() - self.real0) * self.speed)


class DeviceClock:
    RESTART_MS = 60000

    def __init__(self, anchor=None):
        self.anchor, self.max_ms = anchor, 0

    def to_wall(self, t_ms, now):
        if self.anchor is None or t_ms < self.max_ms - self.RESTART_MS:
            if self.anchor is not None:
                print("        (pod restarted: clock set again)")
            self.anchor = now - timedelta(milliseconds=t_ms)
            self.max_ms = 0
        self.max_ms = max(self.max_ms, t_ms)
        return self.anchor + timedelta(milliseconds=t_ms)


def latest_minute(conn, ts):
    row = conn.execute("SELECT ts, stress, hr_bpm, breath_rate FROM minute_metrics WHERE ts = ?",
                       (ts,)).fetchone()
    return dict(zip(("ts", "stress", "hr_bpm", "breath_rate"), row)) if row else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pod", required=True, help="serial:<port> or sim:<subject>")
    ap.add_argument("--led", default="sim", help="sim or serial:<port>")
    ap.add_argument("--speed", type=float, default=60.0, help="simulation speed (sim pod only)")
    ap.add_argument("--db", type=Path, default=db.DB_PATH)
    args = ap.parse_args()

    kind, _, target = args.pod.partition(":")
    sim = kind == "sim"
    speed = args.speed if sim else 1.0
    pod = SimPod(target, speed) if sim else SerialPod(target)
    clock = DeviceClock(anchor=pod.start if sim else None)
    led_target = args.led.partition(":")[2] if args.led.startswith("serial:") else "sim"
    led = open_led(led_target, speed)

    conn = db.connect(args.db)
    conn.executescript(COACH_SCHEMA)
    coach = Coach(conn, led)
    print(f"Live: pod = {args.pod}, LED = {args.led}, database = {args.db}"
          + (f", {speed:g}x speed" if sim else "") + "\n")

    malformed = 0
    try:
        while not (pod.done and pod.lines.empty()):
            while not pod.lines.empty():
                line = pod.lines.get()
                if line.startswith("#"):
                    print(f"        pod says: {line[1:]}")
                    continue
                ev = parse(line)
                if ev is None:
                    malformed += 1
                    continue
                when = clock.to_wall(ev.t_ms, pod.now())
                with conn:
                    store_event(conn, ev, ts_text(when))
                if isinstance(ev, LeadOff):
                    coach.contact = ev.connected
                    print(f"{when:%H:%M:%S}  electrodes "
                          + ("on the skin" if ev.connected else f"OFF (bits {ev.bits}) - no coaching"))
                elif isinstance(ev, Hrv):
                    compute(conn)
                    m = latest_minute(conn, ts_text(when))
                    history = conn.execute("SELECT COUNT(*) FROM minute_metrics").fetchone()[0]
                    note = "" if history >= MIN_HISTORY_MIN else "  (learning your normal)"
                    print(f"{when:%H:%M}  {m['stress']:3.0f} {bar(m['stress']):<20} HR {m['hr_bpm']:3.0f}"
                          f"  breath {m['breath_rate'] or 0:4.1f}/min{note}")
                    if history >= MIN_HISTORY_MIN:
                        coach.on_minute(m, when)
            coach.poll(pod.now())
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopped.")
    coach.finish()
    led.close()
    if malformed:
        print(f"({malformed} malformed lines skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
