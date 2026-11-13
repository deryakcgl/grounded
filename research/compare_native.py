"""Adim 5: C++ dedektorlerini (firmware kodu) Python referansiyla karsilastir.

1. WESAD verisini metin dosyasina yazar (data/vectors/, git'e girmez).
2. firmware/test_native'i derleyip C++ dedektorlerini bu veriyle calistirir.
3. Ayni veriyi Python dedektorlerinden gecirir ve sonuclari karsilastirir.

Once prepare_data.py ve gen_filter_coeffs.py calistirilmis olmali.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

from breath_detector import BreathDetector
from beat_detector import BeatDetector, HrvTracker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
NATIVE = ROOT / "firmware/test_native"
VEC = DATA / "vectors"
VEC.mkdir(exist_ok=True)

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
d = np.load(DATA / f"{subject}_prepared.npz")
resp, ecg = d["resp"], d["ecg"]          # float32: cihazdaki gibi

# --- 1. Veriyi metin olarak yaz (float32'yi kayipsiz temsil eden 9 basamak) ---
resp_file, ecg_file = VEC / f"{subject}_resp25.txt", VEC / f"{subject}_ecg250.txt"
np.savetxt(resp_file, resp, fmt="%.9g")
np.savetxt(ecg_file, ecg, fmt="%.9g")

# --- 2. C++: derle ve calistir ---
subprocess.run(["make", "-s", "-C", str(NATIVE)], check=True)


def run_cpp(kind, path):
    out = subprocess.run([str(NATIVE / "dsp_test"), kind, str(path)],
                         check=True, capture_output=True, text=True).stdout
    return [line.split(",") for line in out.splitlines()]


cpp_resp = run_cpp("resp", resp_file)
cpp_ecg = run_cpp("ecg", ecg_file)
cpp_breaths = np.array([int(r[1]) for r in cpp_resp if r[0] == "breath"])
cpp_holds = np.array([int(r[1]) for r in cpp_resp if r[0] == "hold_start"])
cpp_beats = np.array([int(r[1]) for r in cpp_ecg if r[0] == "beat"])
cpp_rmssd = np.array([float(r[2]) for r in cpp_ecg if r[0] == "hrv"])

# --- 3. Python referansi (float64) ---
resp_f = sosfilt(butter(2, [0.05, 1.0], btype="bandpass", fs=25, output="sos"),
                 resp.astype(np.float64))
bd = BreathDetector(fs=25)
py_breaths, py_holds = [], []
for x in resp_f:
    for ev in bd.update(x):
        if ev[0] == "breath":
            py_breaths.append(ev[1])
        elif ev[0] == "hold_start":
            py_holds.append(ev[1])
py_breaths, py_holds = np.array(py_breaths), np.array(py_holds)

det = BeatDetector(butter(2, [5, 15], btype="bandpass", fs=250, output="sos"), fs=250)
py_beats = np.array([r for x in ecg.astype(np.float64) if (r := det.update(x)) is not None])
hrv = HrvTracker()
py_rmssd = np.array([res[0] for x in np.diff(py_beats) / 250 if (res := hrv.update(x))])


def match(a, b, tol=0):
    """a'daki olaylarin kaci b'de +-tol ornek icinde var."""
    j = np.searchsorted(b, a)
    lo = np.abs(a - b[np.clip(j - 1, 0, len(b) - 1)])
    hi = np.abs(a - b[np.clip(j, 0, len(b) - 1)])
    return int(np.sum(np.minimum(lo, hi) <= tol))


print(f"{'':<14}{'Python':>9}{'C++':>9}{'Birebir ayni':>15}{'+-1 ornek':>12}")
for name, py, cpp in (("Nefes", py_breaths, cpp_breaths),
                      ("Nefes tutma", py_holds, cpp_holds),
                      ("Kalp atisi", py_beats, cpp_beats)):
    exact, near = match(py, cpp, 0), match(py, cpp, 1)
    print(f"{name:<14}{len(py):>9}{len(cpp):>9}{exact / len(py):>14.2%}{near / len(py):>11.2%}")

n = min(len(py_rmssd), len(cpp_rmssd))
diff = np.abs(py_rmssd[:n] - cpp_rmssd[:n])
print(f"\nRMSSD pencereleri: Python {len(py_rmssd)}, C++ {len(cpp_rmssd)}; "
      f"en buyuk fark {diff.max():.3f} ms")
