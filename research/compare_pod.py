import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))
from protocol import Breath, HoldStart, Hrv, parse

NATIVE = ROOT / "firmware/test_native"
VEC = ROOT / "data/vectors"
VEC.mkdir(exist_ok=True)


def events(text):
    out = {"breath": [], "hold": [], "hrv": []}
    for line in text.splitlines():
        ev = parse(line)
        if isinstance(ev, Breath):
            out["breath"].append(ev.t_ms)
        elif isinstance(ev, HoldStart):
            out["hold"].append(ev.t_ms)
        elif isinstance(ev, Hrv):
            out["hrv"].append((ev.t_ms, ev.rmssd_ms))
    return out


def matched(a, b, tol):
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0:
        return 1.0
    j = np.clip(np.searchsorted(b, a), 1, len(b) - 1)
    d = np.minimum(np.abs(a - b[j - 1]), np.abs(a - b[j]))
    return float(np.mean(d <= tol))


subprocess.run(["make", "-s", "-C", str(NATIVE), "dsp_test", "pod_sim"], check=True)
print(f"{'Subj':<5}{'breaths':>9}{'match':>8}{'holds':>7}{'match':>8}{'HRV win':>9}{'match':>8}"
      f"{'max dRMSSD':>12}  pod_sim")
worst = 1.0
for p in sorted(ROOT.glob("data/S*_prepared.npz"), key=lambda p: int(p.name[1:].split("_")[0])):
    subj = p.name.split("_")[0]
    d = np.load(p)
    rf, ef = VEC / f"{subj}_resp25.txt", VEC / f"{subj}_ecg250.txt"
    np.savetxt(rf, d["resp"], fmt="%.9g")
    np.savetxt(ef, d["ecg"], fmt="%.9g")
    ref = events(subprocess.run([str(NATIVE / "dsp_test"), "device", rf, ef],
                                check=True, capture_output=True, text=True).stdout)
    pod = subprocess.run([str(NATIVE / "pod_sim"), rf, ef], capture_output=True, text=True)
    got = events(pod.stdout)
    rf.unlink()
    ef.unlink()

    mb = matched(ref["breath"], got["breath"], 40)
    mh = matched(ref["hold"], got["hold"], 40)
    rt, rr = np.array([h[0] for h in ref["hrv"]]), np.array([h[1] for h in ref["hrv"]])
    gt, gr = np.array([h[0] for h in got["hrv"]]), np.array([h[1] for h in got["hrv"]])
    mv = matched(rt, gt, 4)
    n = min(len(rr), len(gr))
    drm = float(np.max(np.abs(rr[:n] - gr[:n]))) if n else 0.0
    worst = min(worst, mb, mh, mv)
    status = "ok" if pod.returncode == 0 else f"FAILED: {pod.stderr.strip()}"
    print(f"{subj:<5}{len(ref['breath']):>9}{mb:>8.1%}{len(ref['hold']):>7}{mh:>8.1%}"
          f"{len(rt):>9}{mv:>8.1%}{drm:>10.1f}ms  {status}")
print(f"\nWorst match: {worst:.1%}")
