"""Downsamples WESAD chest data to the rates the ADS1292R will use and saves a small file.

- Respiration: 700 Hz -> 25 Hz
- ECG:         700 Hz -> 250 Hz
Run once; later scripts read this file instead of the large .pkl.

Usage:
  python research/prepare_data.py S2                         # from data/S2.pkl
  python research/prepare_data.py S3 ~/Downloads/WESAD.zip   # straight from the zip (no extraction)
  python research/prepare_data.py S3 ~/Downloads/WESAD       # from an extracted WESAD folder
"""
import pickle
import sys
import zipfile
from pathlib import Path

import numpy as np
from scipy.signal import decimate, resample_poly

DATA = Path(__file__).resolve().parent.parent / "data"   # data/ at the project root

FS_RAW  = 700
FS_RESP = 25
FS_ECG  = 250

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
source = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else None
dst = DATA / f"{subject}_prepared.npz"

if source and source.suffix == ".zip":
    zip_path = source
    # Read the .pkl from inside the zip without extracting it: saves ~1 GB of disk
    member = f"WESAD/{subject}/{subject}.pkl"
    print(f"Loading: {zip_path}:{member} (this takes a while)")
    with zipfile.ZipFile(zip_path) as z, z.open(member) as f:
        data = pickle.load(f, encoding="latin1")
else:
    src = source / subject / f"{subject}.pkl" if source else DATA / f"{subject}.pkl"
    print(f"Loading: {src} (this takes a while)")
    with open(src, "rb") as f:
        data = pickle.load(f, encoding="latin1")

chest  = data["signal"]["chest"]
resp   = chest["Resp"].flatten().astype(np.float64)
ecg    = chest["ECG"].flatten().astype(np.float64)
labels = data["label"].astype(np.int8)

# --- Respiration: 700 -> 25 Hz (factor 28) ---
# decimate low-pass filters first, then drops samples (to avoid aliasing).
# scipy recommends at most ~13x per step, so we do 7 x 4 = 28 in two steps.
resp_25 = decimate(resp,    7, ftype="fir", zero_phase=True)
resp_25 = decimate(resp_25, 4, ftype="fir", zero_phase=True)

# --- ECG: 700 -> 250 Hz ---
# 250/700 = 5/14 is not an integer factor; resample_poly upsamples by 5 and downsamples by 14 (filtered).
ecg_250 = resample_poly(ecg, 5, 14)

# --- Labels ---
# Labels are categories (1, 2, 4...) and can't be filtered; we just drop samples.
labels_25  = labels[::FS_RAW // FS_RESP]
labels_250 = labels[np.arange(len(ecg_250)) * FS_RAW // FS_ECG]

n = min(len(resp_25), len(labels_25))
resp_25, labels_25 = resp_25[:n], labels_25[:n]

np.savez_compressed(
    dst,
    resp=resp_25.astype(np.float32), labels_resp=labels_25, fs_resp=FS_RESP,
    ecg=ecg_250.astype(np.float32),  labels_ecg=labels_250,  fs_ecg=FS_ECG,
)

mb = lambda a: a.nbytes / 1e6
print(f"Respiration: {len(resp):>9} samples ({mb(resp):6.1f} MB) -> {len(resp_25):>7} samples ({mb(resp_25.astype(np.float32)):5.2f} MB)")
print(f"ECG:         {len(ecg):>9} samples ({mb(ecg):6.1f} MB) -> {len(ecg_250):>7} samples ({mb(ecg_250.astype(np.float32)):5.2f} MB)")
print(f"Saved: {dst}")
