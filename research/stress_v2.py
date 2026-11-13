import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "host"))
from metrics import baseline_stats, window_features
from protocol import Breath, HoldStart, Hrv, parse

DATA = ROOT / "data"
NATIVE = ROOT / "firmware/test_native"
TMP = DATA / "vectors"
V1_WEIGHTS = {"neg_ln_rmssd": 0.50, "hr_bpm": 0.25, "breath_cv": 0.25}


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    pos, neg = pos[~np.isnan(pos)], neg[~np.isnan(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return gt / (len(pos) * len(neg))


def subject_minutes(subject):
    d = np.load(DATA / f"{subject}_prepared.npz")
    labels, fs = d["labels_resp"], int(d["fs_resp"])
    TMP.mkdir(exist_ok=True)
    resp_f, ecg_f = TMP / f"{subject}_resp25.txt", TMP / f"{subject}_ecg250.txt"
    np.savetxt(resp_f, d["resp"], fmt="%.9g")
    np.savetxt(ecg_f, d["ecg"], fmt="%.9g")
    out = subprocess.run([str(NATIVE / "dsp_test"), "device", str(resp_f), str(ecg_f)],
                         check=True, capture_output=True, text=True).stdout
    resp_f.unlink()
    ecg_f.unlink()

    events = [parse(line) for line in out.splitlines()]
    hrv = [e for e in events if isinstance(e, Hrv)]
    br = [e for e in events if isinstance(e, Breath)]
    holds = [e for e in events if isinstance(e, HoldStart)]
    win_t = np.array([e.t_ms / 1000 for e in hrv])
    f = window_features(win_t, [e.rmssd_ms for e in hrv], [e.hr_bpm for e in hrv],
                        [e.t_ms / 1000 for e in br], [e.interval_ms / 1000 for e in br],
                        [e.t_ms / 1000 for e in holds])

    def window_label(t1):
        seg = labels[int(max(0, t1 - 60) * fs):int(t1 * fs)]
        vals, counts = np.unique(seg, return_counts=True)
        i = np.argmax(counts)
        return int(vals[i]) if counts[i] >= 0.8 * len(seg) else 0
    return f, np.array([window_label(t) for t in win_t])

FEATURES = ["neg_ln_rmssd", "hr_bpm", "breath_cv", "breath_rate"]
LAMBDA = 1.0
STATES = {1: "baseline", 3: "amusement", 4: "meditation"}


def personal_z(f, lab):
    stats = baseline_stats(f, lab == 1, keys=FEATURES)
    return np.column_stack([np.nan_to_num((f[k] - stats[k][0]) / stats[k][1]) for k in FEATURES])


def fit_logistic(X, y, lam=LAMBDA):
    sw = np.where(y == 1, 0.5 / y.sum(), 0.5 / (1 - y).sum()) * len(y)
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    reg = lam * np.eye(len(w))
    reg[0, 0] = 0.0
    for _ in range(50):
        p = 1.0 / (1.0 + np.exp(-Xb @ w))
        grad = Xb.T @ (sw * (p - y)) + reg @ w
        hess = (Xb * (sw * p * (1 - p))[:, None]).T @ Xb + reg
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w[0], w[1:]


def main():
    subprocess.run(["make", "-s", "-C", str(NATIVE), "dsp_test"], check=True)
    print("Building per-minute features for all subjects (virtual device)...")
    subjects = sorted((p.name.split("_")[0] for p in DATA.glob("S*_prepared.npz")),
                      key=lambda s: int(s[1:]))
    data = {}
    for s in subjects:
        f, lab = subject_minutes(s)
        keep = np.isin(lab, [1, 2, 3, 4])
        data[s] = (personal_z(f, lab)[keep], lab[keep])

    v1 = np.array([V1_WEIGHTS.get(k, 0.0) for k in FEATURES])
    hr = np.array([1.0 if k == "hr_bpm" else 0.0 for k in FEATURES])
    safe = [i for i, k in enumerate(FEATURES) if k != "neg_ln_rmssd"]
    methods = {"v1": [], "HR only": [], "v2": [], "v2 safe": []}
    fold_w, fold_w_safe = [], []

    for test in subjects:
        X = np.vstack([data[s][0] for s in subjects if s != test])
        y = np.concatenate([(data[s][1] == 2).astype(float) for s in subjects if s != test])
        _, w = fit_logistic(X, y)
        fold_w.append(w)
        _, ws = fit_logistic(X[:, safe], y)
        w_safe = np.zeros(len(FEATURES))
        w_safe[safe] = ws
        fold_w_safe.append(w_safe)
        Z, lab = data[test]
        for name, weights in (("v1", v1), ("HR only", hr), ("v2", w), ("v2 safe", w_safe)):
            score = Z @ weights
            stress = score[lab == 2]
            row = {k: auc(stress, score[lab == k]) for k in STATES}
            row["others"] = auc(stress, score[lab != 2])
            methods[name].append(row)

    print(f"\nAUC stress vs ALL other minutes, per unseen subject (model trained on the other 14):")
    print(f"{'Subj':<6}" + "".join(f"{m:>9}" for m in methods))
    for i, s in enumerate(subjects):
        print(f"{s:<6}" + "".join(f"{methods[m][i]['others']:>9.2f}" for m in methods))

    print(f"\n{'':<24}" + "".join(f"{m:>18}" for m in methods))
    for key, label in (("others", "stress vs all others"), (1, "stress vs baseline"),
                       (3, "stress vs amusement"), (4, "stress vs meditation")):
        cells = []
        for m in methods:
            v = np.array([r[key] for r in methods[m]])
            cells.append(f"{np.nanmedian(v):.2f} / {np.nanmin(v):.2f} / {np.sum(v >= 0.8):>2}")
        print(f"{label:<24}" + "".join(f"{c:>18}" for c in cells))
    print(f"{'':<24}" + "".join(f"{'median/worst/>=0.8':>18}" for _ in methods))

    W, WS = np.array(fold_w), np.array(fold_w_safe)
    print("\nLearned weights across the 15 folds (mean +- std): stable = trustworthy")
    print(f"  {'':<14}{'v2':>16}{'v2 safe':>16}")
    for i, k in enumerate(FEATURES):
        print(f"  {k:<14}{W[:, i].mean():>+9.3f} +-{W[:, i].std():.3f}"
              f"{WS[:, i].mean():>+9.3f} +-{WS[:, i].std():.3f}")

    X = np.vstack([data[s][0] for s in subjects])
    y = np.concatenate([(data[s][1] == 2).astype(float) for s in subjects])
    b, ws = fit_logistic(X[:, safe], y)
    print("\nFinal 'v2 safe' weights (all 15 subjects) for host/metrics.py:")
    print("  WEIGHTS = {" + ", ".join(f'"{FEATURES[i]}": {v:.3f}' for i, v in zip(safe, ws)) + "}")
    print(f"  (intercept {b:+.2f} is not used: the product keeps 50 = personal normal)")

    fig, ax = plt.subplots(figsize=(13, 4.5))
    x = np.arange(len(subjects))
    for off, m, color in ((-0.3, "v1", "tab:gray"), (-0.1, "HR only", "tab:orange"),
                          (0.1, "v2", "tab:red"), (0.3, "v2 safe", "tab:blue")):
        ax.bar(x + off, [r["others"] for r in methods[m]], width=0.2, color=color, label=m)
    ax.axhline(0.5, color="0.4", linestyle="--", linewidth=1, label="coin flip (0.5)")
    ax.axhline(0.8, color="tab:red", linestyle=":", linewidth=1, label="good (0.8)")
    ax.set_xticks(x, subjects)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("AUC: stress vs all other minutes")
    ax.set_title("Stress score per unseen subject (leave-one-subject-out)")
    ax.legend(loc="lower right", fontsize=8, ncol=6)
    fig.tight_layout()
    fig.savefig(HERE / "figures/stress_v2_loso.png", dpi=120)
    print(f"\nFigure: {HERE / 'figures/stress_v2_loso.png'}")


if __name__ == "__main__":
    main()
