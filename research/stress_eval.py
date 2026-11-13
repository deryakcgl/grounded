"""Adim 6b: stres skoru WESAD etiketleriyle ne kadar uyusuyor?

host/ingest.py ve host/metrics.py calistirilmis olmali (ayni --start ile).
Host uygulamasi etiketleri bilmez; burada sadece degerlendirme icin eslestiriyoruz.

Kullanim: python research/stress_eval.py --start "2026-11-12 09:00"
"""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIGS = HERE / "figures"

ap = argparse.ArgumentParser()
ap.add_argument("--subject", default="S2")
ap.add_argument("--start", default=datetime.now().strftime("%Y-%m-%d 09:00"))
args = ap.parse_args()
start = datetime.strptime(args.start, "%Y-%m-%d %H:%M")

d = np.load(ROOT / "data" / f"{args.subject}_prepared.npz")
labels, fs = d["labels_resp"], int(d["fs_resp"])

conn = sqlite3.connect(ROOT / "data/grounded.db")
rows = conn.execute("""SELECT ts, stress, rmssd_ms, hr_bpm, breath_cv FROM minute_metrics
                       WHERE date(ts) = date(?) ORDER BY ts""", (args.start,)).fetchall()
t_end = np.array([(datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S.%f") - start).total_seconds()
                  for r in rows])
stress = np.array([r[1] for r in rows])


def window_label(t1):
    """60 sn'lik pencerenin cogunluk etiketi; %80'den azi tek etiketse 0 (karisik)."""
    seg = labels[int(max(0, t1 - 60) * fs):int(t1 * fs)]
    vals, counts = np.unique(seg, return_counts=True)
    i = np.argmax(counts)
    return int(vals[i]) if counts[i] >= 0.8 * len(seg) else 0


lab = np.array([window_label(t) for t in t_end])
STATES = {1: "Baseline", 2: "Stress", 4: "Meditation"}
COLORS = {1: "tab:blue", 2: "tab:orange", 4: "tab:green"}


def auc(pos, neg):
    """ROC AUC (Mann-Whitney): rastgele bir 'pos' dakikanin skoru, rastgele bir 'neg'
    dakikanin skorundan yuksek olma olasiligi. 0.5 = yazi tura, 1.0 = kusursuz ayirt etme."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    greater = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return greater / (len(pos) * len(neg))


print(f"{'Durum':<12}{'Dakika':>7}{'Ort. stres':>12}{'Medyan':>8}")
for k, name in STATES.items():
    s = stress[lab == k]
    print(f"{name:<12}{len(s):>7}{s.mean():>12.0f}{np.median(s):>8.0f}")

print(f"\nAUC  stres vs baseline:   {auc(stress[lab == 2], stress[lab == 1]):.2f}")
print(f"AUC  stres vs meditasyon: {auc(stress[lab == 2], stress[lab == 4]):.2f}")
print(f"AUC  stres vs digerleri:  {auc(stress[lab == 2], stress[(lab == 1) | (lab == 4)]):.2f}")

# --- Grafik: gun boyu stres skoru ve gercek durumlar ---
fig, ax = plt.subplots(figsize=(13, 4.5))
t_min_all = np.arange(len(labels)) / fs / 60
for k, name in STATES.items():
    ax.fill_between(t_min_all, 0, 100, where=labels == k, color=COLORS[k], alpha=0.13,
                    step="mid", label=f"gercek: {name}")
ax.plot(t_end / 60, stress, "o-", color="tab:red", markersize=3, label="stres skoru")
ax.axhline(50, color="0.5", linestyle="--", linewidth=1, label="kisisel normal (50)")
ax.set_ylim(0, 100)
ax.set_xlabel("Zaman (dakika)")
ax.set_ylabel("Stres skoru")
ax.set_title(f"{args.subject}: stres skoru (v1, kural tabanli) ve gercek durumlar")
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
FIGS.mkdir(exist_ok=True)
fig.savefig(FIGS / f"{args.subject}_stress_score.png", dpi=120)
print(f"\nGrafik: {FIGS / f'{args.subject}_stress_score.png'}")
