import argparse
import collections
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "firmware/test_native"
FS = 250
WINDOW_S = 10
MV_PER_CODE = 2420.0 / 6 / 8388607


class Stream:
    def __init__(self):
        self.resp = collections.deque(maxlen=FS * WINDOW_S)
        self.ecg = collections.deque(maxlen=FS * WINDOW_S)
        self.lead_off = 0
        self.frames = 0
        self.notes = []

    def feed(self, line):
        if line.startswith("R,"):
            try:
                _, r, e, lo = line.strip().split(",")
                self.resp.append(int(r))
                self.ecg.append(int(e) * MV_PER_CODE)
                self.lead_off = int(lo)
                self.frames += 1
            except ValueError:
                pass
        elif line.strip():
            self.notes.append(line.strip())
            print(line.rstrip())

    def start_serial(self, port):
        import serial
        ser = serial.Serial(port, 115200, timeout=0.5)

        def run():
            while True:
                self.feed(ser.readline().decode(errors="replace"))
        threading.Thread(target=run, daemon=True).start()

    def start_sim(self, subject):
        subprocess.run(["make", "-s", "-C", str(NATIVE), "pod_sim"], check=True)
        d = np.load(ROOT / "data" / f"{subject}_prepared.npz")
        vec = ROOT / "data/vectors"
        vec.mkdir(exist_ok=True)
        rf, ef = vec / f"scope_{subject}_resp.txt", vec / f"scope_{subject}_ecg.txt"
        np.savetxt(rf, d["resp"], fmt="%.9g")
        np.savetxt(ef, d["ecg"], fmt="%.9g")
        proc = subprocess.Popen([str(NATIVE / "pod_sim"), "--raw", str(rf), str(ef)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        def run():
            t0 = time.monotonic()
            for i, line in enumerate(proc.stdout):
                delay = i / FS - (time.monotonic() - t0)
                if delay > 0:
                    time.sleep(delay)
                self.feed(line)
            rf.unlink(missing_ok=True)
            ef.unlink(missing_ok=True)
        threading.Thread(target=run, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port")
    src.add_argument("--sim", metavar="SUBJECT")
    ap.add_argument("--snapshot", type=Path, help="save an image instead of opening a window")
    ap.add_argument("--seconds", type=float, default=15, help="with --snapshot: how long to record")
    args = ap.parse_args()

    if args.snapshot:
        import matplotlib
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    s = Stream()
    s.start_sim(args.sim) if args.sim else s.start_serial(args.port)

    fig, (ax_e, ax_r) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    line_e, = ax_e.plot([], [], color="tab:red", linewidth=0.9)
    line_r, = ax_r.plot([], [], color="tab:blue", linewidth=1.2)
    ax_e.set_ylabel("ECG (mV)")
    ax_r.set_ylabel("Respiration (ADC code)")
    ax_r.set_xlabel("Time (s, last 10 s)")
    t0 = time.monotonic()

    def update(_):
        n = len(s.ecg)
        if n < 2:
            return line_e, line_r
        t = np.arange(n) / FS
        e, r = np.array(s.ecg), np.array(s.resp)
        line_e.set_data(t, e)
        line_r.set_data(t, r)
        ax_e.set_xlim(0, WINDOW_S)
        for ax, y in ((ax_e, e), (ax_r, r)):
            lo, hi = np.percentile(y, 0.5), np.percentile(y, 99.5)
            pad = (hi - lo) * 0.15 + 1e-9
            ax.set_ylim(lo - pad, hi + pad)
        rate = s.frames / max(time.monotonic() - t0, 1e-3)
        contact = "electrodes on the skin" if s.lead_off == 0 else f"LEAD-OFF bits {s.lead_off}"
        ax_e.set_title(f"ADS1292R raw stream  |  {rate:.0f} frames/s  |  {contact}")
        return line_e, line_r

    if args.snapshot:
        time.sleep(args.seconds)
        update(0)
        fig.tight_layout()
        fig.savefig(args.snapshot, dpi=110)
        print(f"Saved {args.snapshot} ({s.frames} frames)")
    else:
        anim = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
        fig.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
