import pickle
import sys
import zipfile
from pathlib import Path

import numpy as np
from scipy.signal import decimate, resample_poly

DATA = Path(__file__).resolve().parent.parent / "data"

FS_RAW  = 700
FS_RESP = 25
FS_ECG  = 250

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
source = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else None
dst = DATA / f"{subject}_prepared.npz"

if source and source.suffix == ".zip":
    zip_path = source
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

resp_25 = decimate(resp,    7, ftype="fir", zero_phase=True)
resp_25 = decimate(resp_25, 4, ftype="fir", zero_phase=True)

ecg_250 = resample_poly(ecg, 5, 14)

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
