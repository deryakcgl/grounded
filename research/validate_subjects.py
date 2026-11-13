"""Step 6b validation: do the stress score and detectors work on subjects we never looked at?

For each subject:
  1. The virtual device (firmware C++ code) processes WESAD data -> protocol lines
  2. Per-minute features and stress score with the SAME functions as host/metrics.py
  3. The personal normal is computed ONLY from the calibration segment (baseline label)
     (in production: the first days of data), so the stress segment can't affect it.
  4. The beat detector is compared with an offline reference.

S2 is reported separately: we looked at it while designing the score, so it isn't "unseen".
Note: since v2, host/metrics.py's weights were fitted on ALL 15 subjects, so this script's AUCs
are in-sample. The honest numbers for v2 are the leave-one-subject-out ones from stress_v2.py.

Usage: python research/validate_subjects.py
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt, find_peaks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "host"))
from metrics import WEIGHTS, baseline_stats, stress_score, window_features  # noqa: E402
from protocol import Breath, HoldStart, Hrv, parse  # noqa: E402

DATA = ROOT / "data"
NATIVE = ROOT / "firmware/test_native"
TMP = DATA / "vectors"
FIGS = HERE / "figures"
TMP.mkdir(exist_ok=True)
FIGS.mkdir(exist_ok=True)

DESIGN_SUBJECT = "S2"
FEATURES = ["neg_ln_rmssd", "hr_bpm", "breath_cv", "breath_rate"]


def auc(pos, neg):
    """Probability that a random 'pos' minute's value is larger than a random 'neg' minute's."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    pos, neg = pos[~np.isnan(pos)], neg[~np.isnan(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return gt / (len(pos) * len(neg))


def run_native(*args):
    return subprocess.run([str(NATIVE / "dsp_test"), *map(str, args)],
                          check=True, capture_output=True, text=True).stdout


def subject_minutes(subject):
    """Per-minute features (same code as the host) and WESAD labels for one subject.
    Runs the virtual device (the firmware's C++ code) on the subject's data.
    Returns (features dict, label per minute); label 0 = mixed window."""
    d = np.load(DATA / f"{subject}_prepared.npz")
    labels, fs = d["labels_resp"], int(d["fs_resp"])
    resp_f, ecg_f = TMP / f"{subject}_resp25.txt", TMP / f"{subject}_ecg250.txt"
    np.savetxt(resp_f, d["resp"], fmt="%.9g")
    np.savetxt(ecg_f, d["ecg"], fmt="%.9g")

    # --- 1. Virtual device ---
    events = [parse(line) for line in run_native("device", resp_f, ecg_f).splitlines()]
    hrv = [e for e in events if isinstance(e, Hrv)]
    br = [e for e in events if isinstance(e, Breath)]
    holds = [e for e in events if isinstance(e, HoldStart)]

    # --- 2. Features (same code as the host) ---
    win_t = np.array([e.t_ms / 1000 for e in hrv])
    f = window_features(win_t, [e.rmssd_ms for e in hrv], [e.hr_bpm for e in hrv],
                        [e.t_ms / 1000 for e in br], [e.interval_ms / 1000 for e in br],
                        [e.t_ms / 1000 for e in holds])

    # Window label: the state covering >=80% of it, else 0 (mixed)
    def window_label(t1):
        seg = labels[int(max(0, t1 - 60) * fs):int(t1 * fs)]
        vals, counts = np.unique(seg, return_counts=True)
        i = np.argmax(counts)
        return int(vals[i]) if counts[i] >= 0.8 * len(seg) else 0
    lab = np.array([window_label(t) for t in win_t])
    resp_f.unlink()
    ecg_f.unlink()
    return f, lab


def evaluate(subject):
    f, lab = subject_minutes(subject)
    d = np.load(DATA / f"{subject}_prepared.npz")
    ecg_f = TMP / f"{subject}_ecg250.txt"
    np.savetxt(ecg_f, d["ecg"], fmt="%.9g")

    # --- 3. Score: normal from calibration ONLY ---
    calib = lab == 1
    stress = stress_score(f, baseline_stats(f, calib))
    stress_all = stress_score(f, baseline_stats(f))      # comparison: old method

    # --- 4. Beat detector check ---
    beats = np.array([int(x.split(",")[1]) for x in run_native("ecg", ecg_f).splitlines()
                      if x.startswith("beat")])
    ecg = d["ecg"].astype(np.float64)
    ref_f = sosfiltfilt(butter(2, [5, 30], btype="bandpass", fs=250, output="sos"), ecg)
    # The reference tries both polarities: does the R peak point up or down?
    best = None
    for sign in (1, -1):
        ref, _ = find_peaks(sign * ref_f, distance=75,
                            prominence=np.percentile(sign * ref_f, 99) * 0.4)
        j = np.searchsorted(beats, ref)
        dist = np.minimum(np.abs(ref - beats[np.clip(j - 1, 0, len(beats) - 1)]),
                          np.abs(ref - beats[np.clip(j, 0, len(beats) - 1)]))
        sens = float(np.mean(dist <= 12))   # +-50 ms
        if best is None or sens > best[0]:
            best = (sens, sign, len(ref))
    # The detector assumes a positive R; if R is negative, the raw ECG's peaks point down
    raw_polarity = 1 if np.percentile(ecg, 99.5) - np.median(ecg) > \
        np.median(ecg) - np.percentile(ecg, 0.5) else -1

    ecg_f.unlink()

    s, b, m, a = (lab == 2), (lab == 1), (lab == 4), (lab == 3)
    return {
        "subject": subject,
        "minutes": {k: int(np.sum(lab == k)) for k in (1, 2, 3, 4)},
        "auc_vs_base": auc(stress[s], stress[b]),
        "auc_vs_med": auc(stress[s], stress[m]),
        "auc_vs_amuse": auc(stress[s], stress[a]),
        "auc_vs_base_oldbaseline": auc(stress_all[s], stress_all[b]),
        "feat_auc": {k: auc(f[k][s], f[k][b]) for k in FEATURES},
        "mean": {k: float(np.mean(stress[lab == k])) if np.any(lab == k) else np.nan
                 for k in (1, 2, 3, 4)},
        "beat_sens": best[0], "polarity": raw_polarity,
        "breath_rate_med": {k: float(np.nanmedian(f["breath_rate"][lab == k])) for k in (1, 2)},
    }


def main():
    subprocess.run(["make", "-s", "-C", str(NATIVE)], check=True)
    subjects = sorted((p.name.split("_")[0] for p in DATA.glob("S*_prepared.npz")),
                      key=lambda s: int(s[1:]))
    results = []
    print(f"{'Subj':<5}{'Calib':>6}{'Strss':>6}{'Med':>5} | {'AUC vs':>7}{'vs':>6}{'vs':>6}"
          f" | {'Avg score B/S/M':>16} | {'Beat':>6} {'R':>2} | {'Breath B->S':>11}")
    print(f"{'':<5}{'min':>6}{'min':>6}{'min':>5} | {'base':>7}{'med':>6}{'amuse':>6} |"
          f"{'':>17} | {'sens':>6} {'':>2} |")
    for subj in subjects:
        r = evaluate(subj)
        results.append(r)
        mm, mn = r["minutes"], r["mean"]
        tag = " (design)" if subj == DESIGN_SUBJECT else ""
        print(f"{subj:<5}{mm[1]:>6}{mm[2]:>6}{mm[4]:>5} | {r['auc_vs_base']:>7.2f}"
              f"{r['auc_vs_med']:>6.2f}{r['auc_vs_amuse']:>6.2f} | "
              f"{mn[1]:>4.0f} /{mn[2]:>4.0f} /{mn[4]:>4.0f}  | {r['beat_sens']:>6.0%} "
              f"{'+' if r['polarity'] > 0 else '-':>2} | "
              f"{r['breath_rate_med'][1]:>4.1f}->{r['breath_rate_med'][2]:>4.1f}{tag}")

    unseen = [r for r in results if r["subject"] != DESIGN_SUBJECT]
    print(f"\n=== {len(unseen)} unseen subjects (excluding S2) ===")
    for key, name in (("auc_vs_base", "stress vs baseline"), ("auc_vs_med", "stress vs meditation"),
                      ("auc_vs_amuse", "stress vs amusement"),
                      ("auc_vs_base_oldbaseline", "stress vs baseline (old: normal=whole rec.)")):
        v = np.array([r[key] for r in unseen])
        print(f"AUC {name:<44} median {np.nanmedian(v):.2f}, worst {np.nanmin(v):.2f}, "
              f">=0.8: {np.sum(v >= 0.8)}/{np.sum(~np.isnan(v))}")
    print("\nPer-feature stress vs baseline AUC (median; 0.5 = useless):")
    for k in FEATURES:
        v = np.array([r["feat_auc"][k] for r in unseen])
        used = "in score" if k in WEIGHTS else "NOT in score"
        print(f"  {k:<14}{np.nanmedian(v):.2f}   ({used})")

    # --- Figure: AUC per subject ---
    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = np.arange(len(results))
    for off, key, name, color in ((-0.27, "auc_vs_base", "vs baseline", "tab:blue"),
                                  (0.0, "auc_vs_med", "vs meditation", "tab:green"),
                                  (0.27, "auc_vs_amuse", "vs amusement", "tab:purple")):
        ax.bar(x + off, [r[key] for r in results], width=0.27, color=color, label=name)
    ax.axhline(0.5, color="0.4", linestyle="--", linewidth=1, label="coin flip (0.5)")
    ax.axhline(0.8, color="tab:red", linestyle=":", linewidth=1, label="good (0.8)")
    ax.set_xticks(x, [r["subject"] + ("*" if r["subject"] == DESIGN_SUBJECT else "")
                      for r in results])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("AUC (are stress minutes separated?)")
    ax.set_title("Stress score, per subject (* = subject used in design; in-sample since v2)")
    ax.legend(loc="lower right", fontsize=8, ncol=5)
    fig.tight_layout()
    fig.savefig(FIGS / "validation_auc.png", dpi=120)
    print(f"\nFigure: {FIGS / 'validation_auc.png'}")


if __name__ == "__main__":
    main()
