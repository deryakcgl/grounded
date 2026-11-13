"""Stress score v2: learn the weights from data, evaluated leave-one-subject-out (LOSO).

v1 used hand-picked weights (0.50 -ln RMSSD, 0.25 heart rate, 0.25 breathing irregularity).
v2 learns them with logistic regression on PERSONAL z-scores (each feature relative to that
person's own calibration minutes, exactly like the host does).

Honest evaluation: for each of the 15 subjects, the model is trained on the other 14 and tested
on the one it never saw - like a new user of the product. Compared with:
  v1        the current hand-made score
  HR only   heart-rate z-score alone (the single best feature in the validation)
If v2 can't beat "HR only", the learned model adds nothing.

Caveat: the feature list was chosen after looking at this data (we saw RMSSD fail while people
were talking), so even LOSO numbers are a little optimistic.

Usage: python research/stress_v2.py        (runs the virtual device for all subjects, ~1 min)
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "host"))
from metrics import WEIGHTS as V1_WEIGHTS, baseline_stats  # noqa: E402
from validate_subjects import DATA, auc, subject_minutes  # noqa: E402

FEATURES = ["neg_ln_rmssd", "hr_bpm", "breath_cv", "breath_rate"]
LAMBDA = 1.0          # L2 penalty: keeps weights small unless the data clearly needs them
STATES = {1: "baseline", 3: "amusement", 4: "meditation"}


def personal_z(f, lab):
    """Feature matrix of z-scores against the person's calibration minutes (label 1).
    Missing values (too few breaths) become 0 = 'like your normal'."""
    stats = baseline_stats(f, lab == 1, keys=FEATURES)
    return np.column_stack([np.nan_to_num((f[k] - stats[k][0]) / stats[k][1]) for k in FEATURES])


def fit_logistic(X, y, lam=LAMBDA):
    """L2-regularised logistic regression by Newton's method (IRLS).

    p = sigmoid(b + X w). Each Newton step solves H step = gradient, where H is the curvature
    of the loss; for this convex loss ~10 steps reach the exact optimum.
    Stress minutes are rare (~1 in 5), so both classes get the same total weight; otherwise the
    model could do well by mostly ignoring stress.
    """
    sw = np.where(y == 1, 0.5 / y.sum(), 0.5 / (1 - y).sum()) * len(y)
    Xb = np.column_stack([np.ones(len(X)), X])           # first column: intercept
    w = np.zeros(Xb.shape[1])
    reg = lam * np.eye(len(w))
    reg[0, 0] = 0.0                                      # don't shrink the intercept
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
    # "v2 safe": the same fit, but HRV may only push the score UP when it is LOW (physiology).
    # Unconstrained, the weight comes out negative (see below); with one linear constraint on a
    # convex problem the optimum then sits on the boundary, weight = 0 - i.e. fit without it.
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
            score = Z @ weights                          # ranking only: intercept/sigmoid don't matter
            stress = score[lab == 2]
            row = {k: auc(stress, score[lab == k]) for k in STATES}
            row["others"] = auc(stress, score[lab != 2])
            methods[name].append(row)

    # --- Per subject ---
    print(f"\nAUC stress vs ALL other minutes, per unseen subject (model trained on the other 14):")
    print(f"{'Subj':<6}" + "".join(f"{m:>9}" for m in methods))
    for i, s in enumerate(subjects):
        print(f"{s:<6}" + "".join(f"{methods[m][i]['others']:>9.2f}" for m in methods))

    # --- Summary ---
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

    # --- Final model on all subjects: the weights for the product ---
    X = np.vstack([data[s][0] for s in subjects])
    y = np.concatenate([(data[s][1] == 2).astype(float) for s in subjects])
    b, ws = fit_logistic(X[:, safe], y)
    print("\nFinal 'v2 safe' weights (all 15 subjects) for host/metrics.py:")
    print("  WEIGHTS = {" + ", ".join(f'"{FEATURES[i]}": {v:.3f}' for i, v in zip(safe, ws)) + "}")
    print(f"  (intercept {b:+.2f} is not used: the product keeps 50 = personal normal)")

    # --- Figure ---
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
