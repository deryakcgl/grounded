"""Step 3a: filter the respiration signal and look at its frequency spectrum.

Run prepare_data.py first.
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt, welch

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"      # data/ at the project root
FIGS = HERE / "figures"          # research/figures/

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
d = np.load(DATA / f"{subject}_prepared.npz")
resp, labels, FS = d["resp"], d["labels_resp"], int(d["fs_resp"])

# --- Bandpass filter: 0.05 - 1.0 Hz ---
# Below 0.05 Hz: slow drift of the signal (DC and drift), not breathing.
# Above 1.0 Hz: noise and heartbeat residue; the fastest breathing is ~0.67 Hz.
# The sos format is numerically more stable at low cutoff frequencies.
LOW_HZ, HIGH_HZ = 0.05, 1.0
sos = butter(2, [LOW_HZ, HIGH_HZ], btype="bandpass", fs=FS, output="sos")
resp_f = sosfiltfilt(sos, resp)

STATES = {1: "Baseline", 2: "Stress", 4: "Meditation"}

def first_run(label):
    """[start, end) indices of the first contiguous run of the label."""
    start = int(np.argmax(labels == label))
    end = start + int(np.argmax(labels[start:] != label))
    if end == start:              # the label runs to the end of the file
        end = len(labels)
    return start, end

FIGS.mkdir(exist_ok=True)

# --- Figure 1: raw and filtered, 30 seconds ---
fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
t = np.arange(30 * FS) / FS

for ax, (lab, name) in zip(axes, STATES.items()):
    start, _ = first_run(lab)
    w = slice(start + 60 * FS, start + 90 * FS)
    raw = resp[w] - np.mean(resp[w])
    ax.plot(t, raw, color="0.7", linewidth=1, label="raw (25 Hz)")
    ax.plot(t, resp_f[w], color="tab:green", linewidth=1.6, label=f"filtered {LOW_HZ}-{HIGH_HZ} Hz")
    ax.set_title(name)
    ax.legend(loc="upper right")
axes[-1].set_xlabel("Time (s)")
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_resp_filtered.png", dpi=120)

# --- Figure 2: frequency spectrum (Welch) ---
# Welch: splits the signal into 60 s segments, takes each one's FFT and averages them.
# 60 s segments -> frequency resolution 1/60 Hz = 1 breath per minute.
fig, ax = plt.subplots(figsize=(10, 5))
print(f"{'State':<12}{'Length':>8}{'Dominant rate':>16}")

for lab, name in STATES.items():
    start, end = first_run(lab)
    f, psd = welch(resp_f[start:end], fs=FS, nperseg=60 * FS)
    bpm = f * 60
    band = (f >= 0.1) & (f <= 0.7)
    peak_bpm = bpm[band][np.argmax(psd[band])]
    ax.plot(bpm, psd / psd[band].max(), linewidth=1.8, label=f"{name} (peak {peak_bpm:.0f}/min)")
    print(f"{name:<12}{(end - start) / FS / 60:>5.1f}min{peak_bpm:>11.0f} /min")

ax.axvspan(6, 40, color="tab:green", alpha=0.08, label="normal breathing range (6-40/min)")
ax.set_xlim(0, 60)
ax.set_xlabel("Frequency (breaths / minute)")
ax.set_ylabel("Power (each state relative to its own peak)")
ax.set_title(f"{subject} - Respiration spectrum")
ax.legend()
fig.tight_layout()
fig.savefig(FIGS / f"{subject}_resp_spectrum.png", dpi=120)

plt.show()
