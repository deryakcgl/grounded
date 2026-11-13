"""WESAD gogus verisini ADS1292R'nin kullanacagi hizlara indirip kucuk bir dosyaya kaydeder.

- Solunum: 700 Hz -> 25 Hz
- EKG:     700 Hz -> 250 Hz
Bir kez calistirilir; sonraki scriptler buyuk .pkl yerine bu dosyayi okur.
"""
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.signal import decimate, resample_poly

DATA = Path(__file__).resolve().parent.parent / "data"   # proje kokundeki data/

FS_RAW  = 700
FS_RESP = 25
FS_ECG  = 250

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
src = DATA / f"{subject}.pkl"
dst = DATA / f"{subject}_prepared.npz"

print(f"Yukleniyor: {src} (bu biraz surer)")
with open(src, "rb") as f:
    data = pickle.load(f, encoding="latin1")

chest  = data["signal"]["chest"]
resp   = chest["Resp"].flatten().astype(np.float64)
ecg    = chest["ECG"].flatten().astype(np.float64)
labels = data["label"].astype(np.int8)

# --- Solunum: 700 -> 25 Hz (28 kat) ---
# decimate once alcak geciren filtre uygular, sonra ornek atlar (aliasing olmasin diye).
# scipy tek adimda en fazla ~13 kat onerir, bu yuzden 7 x 4 = 28 iki adimda yapiyoruz.
resp_25 = decimate(resp,    7, ftype="fir", zero_phase=True)
resp_25 = decimate(resp_25, 4, ftype="fir", zero_phase=True)

# --- EKG: 700 -> 250 Hz ---
# 250/700 = 5/14 tam sayi bir kat degil; resample_poly 5 ile carpip 14'e boler (filtreli).
ecg_250 = resample_poly(ecg, 5, 14)

# --- Etiketler ---
# Etiketler kategori (1, 2, 4...), filtrelenemez; sadece ornek atliyoruz.
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
print(f"Solunum: {len(resp):>9} ornek ({mb(resp):6.1f} MB) -> {len(resp_25):>7} ornek ({mb(resp_25.astype(np.float32)):5.2f} MB)")
print(f"EKG:     {len(ecg):>9} ornek ({mb(ecg):6.1f} MB) -> {len(ecg_250):>7} ornek ({mb(ecg_250.astype(np.float32)):5.2f} MB)")
print(f"Kaydedildi: {dst}")
