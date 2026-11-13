"""Adim 3a: solunum sinyalini filtrele ve frekans spektrumuna bak.

Once prepare_data.py calistirilmis olmali.
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt, welch

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"      # proje kokundeki data/
FIGS = HERE / "figures"          # research/figures/

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
d = np.load(DATA / f"{subject}_prepared.npz")
resp, labels, FS = d["resp"], d["labels_resp"], int(d["fs_resp"])

# --- Bant geciren filtre: 0.05 - 1.0 Hz ---
# 0.05 Hz alti: sinyalin yavasca kaymasi (DC ve drift), nefes degil.
# 1.0 Hz ustu: gurultu ve kalp atisi kalintisi; en hizli nefes ~0.67 Hz.
# sos formati dusuk kesim frekanslarinda sayisal olarak daha kararli.
LOW_HZ, HIGH_HZ = 0.05, 1.0
sos = butter(2, [LOW_HZ, HIGH_HZ], btype="bandpass", fs=FS, output="sos")
resp_f = sosfiltfilt(sos, resp)

STATES = {1: "Baseline", 2: "Stress", 4: "Meditation"}

def first_run(label):
    """Etiketin ilk kesintisiz bolumunun [baslangic, bitis) indisleri."""
    start = int(np.argmax(labels == label))
    end = start + int(np.argmax(labels[start:] != label))
    if end == start:              # etiket dosyanin sonuna kadar suruyorsa
        end = len(labels)
    return start, end

FIGS.mkdir(exist_ok=True)

# --- Grafik 1: ham ve filtrelenmis, 30 saniye ---
fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
t = np.arange(30 * FS) / FS

for ax, (lab, name) in zip(axes, STATES.items()):
    start, _ = first_run(lab)
    w = slice(start + 60 * FS, start + 90 * FS)
    raw = resp[w] - np.mean(resp[w])
    ax.plot(t, raw, color="0.7", linewidth=1, label="ham (25 Hz)")
    ax.plot(t, resp_f[w], color="tab:green", linewidth=1.6, label=f"filtreli {LOW_HZ}-{HIGH_HZ} Hz")
    ax.set_title(name)
    ax.legend(loc="upper right")
axes[-1].set_xlabel("Zaman (s)")
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_resp_filtered.png", dpi=120)

# --- Grafik 2: frekans spektrumu (Welch) ---
# Welch: sinyali 60 sn'lik parcalara boler, her birinin FFT'sini alip ortalar.
# 60 sn'lik parca -> frekans cozunurlugu 1/60 Hz = dakikada 1 nefes.
fig, ax = plt.subplots(figsize=(10, 5))
print(f"{'Durum':<12}{'Sure':>8}{'Baskin nefes':>16}")

for lab, name in STATES.items():
    start, end = first_run(lab)
    f, psd = welch(resp_f[start:end], fs=FS, nperseg=60 * FS)
    bpm = f * 60
    band = (f >= 0.1) & (f <= 0.7)
    peak_bpm = bpm[band][np.argmax(psd[band])]
    ax.plot(bpm, psd / psd[band].max(), linewidth=1.8, label=f"{name} (tepe {peak_bpm:.0f}/dk)")
    print(f"{name:<12}{(end - start) / FS / 60:>6.1f}dk{peak_bpm:>12.0f} /dk")

ax.axvspan(6, 40, color="tab:green", alpha=0.08, label="normal nefes araligi (6-40/dk)")
ax.set_xlim(0, 60)
ax.set_xlabel("Frekans (nefes / dakika)")
ax.set_ylabel("Guc (her durum kendi tepesine gore)")
ax.set_title(f"{subject} - Solunum spektrumu")
ax.legend()
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_resp_spectrum.png", dpi=120)

plt.show()
