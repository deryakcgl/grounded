"""Adim 4: R tepesi dedektoru ve HRV'yi WESAD verisinde degerlendir.

Once prepare_data.py calistirilmis olmali.
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt, find_peaks

from beat_detector import BeatDetector, HrvTracker

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
FIGS = HERE / "figures"
FIGS.mkdir(exist_ok=True)

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
d = np.load(DATA / f"{subject}_prepared.npz")
ecg, labels, FS = d["ecg"].astype(np.float64), d["labels_ecg"], int(d["fs_ecg"])

STATES = {1: "Baseline", 2: "Stress", 4: "Meditation"}
COLORS = {1: "tab:blue", 2: "tab:orange", 4: "tab:green"}
SOS = butter(2, [5, 15], btype="bandpass", fs=FS, output="sos")

# --- Dedektoru calistir ---
det = BeatDetector(SOS, fs=FS)
beats = []
for x in ecg:
    r = det.update(x)
    if r is not None:
        beats.append(r)
beats = np.array(beats)
ibi = np.diff(beats) / FS                              # atim araliklari (sn)

# --- Dogrulama: cevrimdisi referansla karsilastir ---
# WESAD'da R tepesi etiketi yok. Referans olarak gelecege de bakabilen (filtfilt)
# daha "rahat" bir yontem kullaniyoruz; bizim dedektor bunu ne kadar yakaliyor?
ref_f = sosfiltfilt(butter(2, [5, 30], btype="bandpass", fs=FS, output="sos"), ecg)
ref, _ = find_peaks(ref_f, distance=int(0.3 * FS), prominence=np.percentile(ref_f, 99) * 0.4)

TOL = int(0.05 * FS)                                   # +-50 ms icinde eslesirse dogru
j = np.searchsorted(ref, beats)
dist = np.minimum(np.abs(beats - ref[np.clip(j - 1, 0, len(ref) - 1)]),
                  np.abs(beats - ref[np.clip(j, 0, len(ref) - 1)]))
true_pos = int(np.sum(dist <= TOL))
sensitivity = true_pos / len(ref)                      # gercek atimlarin kacini bulduk
ppv = true_pos / len(beats)                            # bulduklarimizin kaci gercek

print(f"Bulunan atim: {len(beats)}   Referans: {len(ref)}")
print(f"Duyarlilik (kacirmama): {sensitivity:.1%}   Kesinlik (sahte olmama): {ppv:.1%}")
print(f"Zamanlama farki (medyan): {np.median(dist[dist <= TOL]) / FS * 1000:.1f} ms\n")

# --- HRV: 60 sn'lik pencereler ---
def hrv_windows(beat_idx):
    hrv = HrvTracker(window_s=60)
    t, rmssd, hr = [], [], []
    for b, x in zip(beat_idx[1:], np.diff(beat_idx) / FS):
        res = hrv.update(x)
        if res is not None:
            t.append(b)
            rmssd.append(res[0])
            hr.append(res[1])
    return np.array(t), np.array(rmssd), np.array(hr)

win_t, win_rmssd, win_hr = hrv_windows(beats)
ref_t, ref_rmssd, _ = hrv_windows(ref)          # ayni hesap, referans atimlarla
win_lab, ref_lab = labels[win_t], labels[ref_t]

print(f"{'Durum':<12}{'Pencere':>8}{'Kalp hizi':>12}{'RMSSD':>10}{'Ref. RMSSD':>13}")
for lab, name in STATES.items():
    m, mr = win_lab == lab, ref_lab == lab
    print(f"{name:<12}{m.sum():>8}{np.median(win_hr[m]):>9.0f}/dk"
          f"{np.median(win_rmssd[m]):>8.0f} ms{np.median(ref_rmssd[mr]):>10.0f} ms")

# --- Grafik 1: her durumdan 8 sn EKG ve bulunan R tepeleri ---
fig, axes = plt.subplots(3, 1, figsize=(13, 8))
for ax, (lab, name) in zip(axes, STATES.items()):
    start = int(np.argmax(labels == lab)) + 120 * FS
    w = slice(start, start + 8 * FS)
    t = np.arange(8 * FS) / FS
    ax.plot(t, ecg[w], color=COLORS[lab], linewidth=0.9)
    sel = beats[(beats >= w.start) & (beats < w.stop)]
    ax.plot((sel - w.start) / FS, ecg[sel], "v", color="black", markersize=8,
            label=f"bulunan R tepesi ({len(sel)})")
    ax.set_title(name)
    ax.legend(loc="upper right", fontsize=8)
axes[-1].set_xlabel("Zaman (s)")
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_beat_detection.png", dpi=120)

# --- Grafik 2: oturum boyunca kalp hizi ve RMSSD ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
t_min = np.arange(len(labels)) / FS / 60
for ax, top in ((ax1, 130), (ax2, 150)):
    for lab, name in STATES.items():
        ax.fill_between(t_min, 0, top, where=labels == lab, color=COLORS[lab],
                        alpha=0.12, step="mid", label=name)
ax1.plot(win_t / FS / 60, win_hr, "o-", color="0.2", markersize=3)
ax1.set_ylim(40, 130)
ax1.set_ylabel("Kalp hizi (atim/dk)")
ax1.legend(loc="upper right", fontsize=8)
ax2.plot(win_t / FS / 60, win_rmssd, "o-", color="tab:red", markersize=3)
ax2.set_ylim(0, 150)
ax2.set_ylabel("RMSSD (ms)\nyuksek = rahat")
ax2.set_xlabel("Zaman (dakika)")
ax1.set_title(f"{subject}: 60 sn'lik pencerelerde kalp hizi ve HRV")
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_hrv.png", dpi=120)

plt.show()
