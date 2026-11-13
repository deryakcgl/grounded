"""Adim 3b: nefes dedektorunu WESAD verisinde ve yapay nefes tutma testinde degerlendir.

Once prepare_data.py calistirilmis olmali.
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfilt, sosfiltfilt, welch

from breath_detector import BreathDetector

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
FIGS = HERE / "figures"
FIGS.mkdir(exist_ok=True)

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
d = np.load(DATA / f"{subject}_prepared.npz")
resp, labels, FS = d["resp"].astype(np.float64), d["labels_resp"], int(d["fs_resp"])

STATES = {1: "Baseline", 2: "Stress", 4: "Meditation"}
COLORS = {1: "tab:blue", 2: "tab:orange", 4: "tab:green"}

# Nedensel filtre (sosfilt): cihazda canli veriyle yapabilecegimizin aynisi.
# 3a'daki sosfiltfilt gelecege de bakiyordu; firmware bunu yapamaz.
SOS = butter(2, [0.05, 1.0], btype="bandpass", fs=FS, output="sos")


def run(signal):
    """Dedektoru sinyal uzerinde ornek ornek calistir."""
    det = BreathDetector(fs=FS)
    breaths, holds, thr = [], [], np.empty(len(signal))
    hold_start = None
    for i, x in enumerate(signal):
        for ev in det.update(x):
            if ev[0] == "breath":
                breaths.append((ev[1], ev[2]))
            elif ev[0] == "hold_start":
                hold_start = ev[1]
            elif ev[0] == "hold_end":
                holds.append((hold_start, ev[1], ev[2]))
        thr[i] = det.threshold
    return breaths, holds, thr


resp_f = sosfilt(SOS, resp)
breaths, holds, thr = run(resp_f)
b_idx = np.array([b[0] for b in breaths])
b_int = np.array([b[1] if b[1] is not None else np.nan for b in breaths])

# --- Sonuclar: durum basina dedektor ve FFT karsilastirmasi ---
print(f"Toplam: {len(breaths)} nefes, {len(holds)} nefes tutma (>10 sn)\n")
print(f"{'Durum':<12}{'Nefes':>7}{'Ort. hiz':>11}{'Medyan':>9}{'FFT':>7}{'Duzensizlik':>13}")
resp_zero_phase = sosfiltfilt(SOS, resp)
for lab, name in STATES.items():
    mask = labels == lab
    minutes = mask.sum() / FS / 60
    in_state = mask[b_idx]
    intervals = b_int[in_state]
    intervals = intervals[~np.isnan(intervals)]
    # FFT: etiketin ilk kesintisiz bolumu
    start = int(np.argmax(mask))
    end = start + int(np.argmax(~mask[start:])) or len(mask)
    f, psd = welch(resp_zero_phase[start:end], fs=FS, nperseg=60 * FS)
    band = (f >= 0.1) & (f <= 0.7)
    fft_bpm = f[band][np.argmax(psd[band])] * 60
    # Duzensizlik: nefes araliklarinin degisim katsayisi (std / ortalama)
    cv = np.std(intervals) / np.mean(intervals)
    print(f"{name:<12}{in_state.sum():>7}{in_state.sum() / minutes:>9.1f}/dk"
          f"{60 / np.median(intervals):>7.1f}/dk{fft_bpm:>5.0f}/dk{cv:>12.2f}")

for s, e, dur in holds:
    print(f"Nefes tutma: {s / FS / 60:6.2f}. dk, {dur:.1f} sn, etiket={labels[s]}")

# --- Grafik 1: her durumdan 60 sn, esikler ve bulunan nefesler ---
fig, axes = plt.subplots(3, 1, figsize=(13, 9))
for ax, (lab, name) in zip(axes, STATES.items()):
    start = int(np.argmax(labels == lab)) + 60 * FS
    w = slice(start, start + 60 * FS)
    t = np.arange(60 * FS) / FS
    ax.fill_between(t, -thr[w], thr[w], color="0.85", label="histerezis bandi (+-esik)")
    ax.plot(t, resp_f[w], color=COLORS[lab], linewidth=1.4, label="solunum (nedensel filtre)")
    sel = b_idx[(b_idx >= w.start) & (b_idx < w.stop)]
    ax.plot((sel - w.start) / FS, resp_f[sel], "v", color="black", markersize=8,
            label=f"bulunan nefes ({len(sel)})")
    ax.set_title(f"{name}: 60 sn'de {len(sel)} nefes")
    ax.legend(loc="upper right", fontsize=8)
axes[-1].set_xlabel("Zaman (s)")
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_breath_detection.png", dpi=120)

# --- Grafik 2: tum oturum boyunca nefes hizi ---
fig, ax = plt.subplots(figsize=(13, 4.5))
t_min = np.arange(len(labels)) / FS / 60
for lab, name in STATES.items():
    ax.fill_between(t_min, 0, 50, where=labels == lab, color=COLORS[lab], alpha=0.12,
                    step="mid", label=name)
ax.plot(b_idx / FS / 60, 60 / b_int, ".", color="0.3", markersize=3, label="her nefesin anlik hizi")
for s, e, _ in holds:
    ax.axvspan(s / FS / 60, e / FS / 60, color="red", alpha=0.3)
ax.set_ylim(0, 50)
ax.set_xlabel("Zaman (dakika)")
ax.set_ylabel("Nefes / dakika")
ax.set_title(f"{subject}: oturum boyunca nefes hizi (kirmizi = nefes tutma)")
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_breath_rate.png", dpi=120)

# --- Yapay test: nefes tutmayi yakalayabiliyor muyuz? ---
# WESAD'da nefes tutma etiketi yok; o yuzden bir tane ekliyoruz:
# baseline'dan 2 dakika al, 40-55 sn arasinda sinyali sabit tut (nefes tutmus gibi).
print("\nYapay nefes tutma testi (40. sn'de 15 sn tutma):")
start = int(np.argmax(labels == 1)) + 120 * FS
test = resp[start:start + 120 * FS].copy()
h0, h1 = 40 * FS, 55 * FS
rng = np.random.default_rng(0)
test[h0:h1] = test[h0] + rng.normal(0, 0.02 * np.std(test), h1 - h0)
_, test_holds, _ = run(sosfilt(SOS, test))
if test_holds:
    for s, e, dur in test_holds:
        print(f"  Bulundu: {s / FS:.1f}. sn'de basladi, {dur:.1f} sn surdu")
else:
    print("  Bulunamadi!")

plt.show()
