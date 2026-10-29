import pickle
import numpy as np
import matplotlib.pyplot as plt

FS = 700  # WESAD gogus sensorleri: saniyede 700 ornek

# --- 1. Veriyi yukle ---
with open("data/S2.pkl", "rb") as f:
    data = pickle.load(f, encoding="latin1")  # Python 2 ile kaydedilmis, bu yuzden latin1

chest  = data["signal"]["chest"]
ecg    = chest["ECG"].flatten()    # (N, 1) -> (N,)
resp   = chest["Resp"].flatten()
labels = data["label"]

# --- 2. Yapiyi incele ---
print("Gogus sinyalleri:", list(chest.keys()))
print(f"Ornek sayisi: {len(ecg)}  ->  {len(ecg) / FS / 60:.1f} dakika")
for lab in [1, 2, 4]:
    sure = np.sum(labels == lab) / FS / 60
    print(f"Etiket {lab}: {sure:.1f} dakika")

# --- 3. Her durumdan 30 saniyelik bir pencere sec ---
def window_for(label, seconds=30, skip_seconds=60):
    """Etiketin ilk gorundugu yerden skip_seconds sonra baslayan pencere."""
    start = np.argmax(labels == label) + skip_seconds * FS
    return slice(start, start + seconds * FS)

states = {1: "Baseline", 2: "Stress", 4: "Meditation"}

fig, axes = plt.subplots(2, 3, figsize=(15, 6), sharex=True)
t = np.arange(30 * FS) / FS  # 0-30 saniye zaman ekseni

for col, (lab, name) in enumerate(states.items()):
    w = window_for(lab)
    axes[0, col].plot(t, ecg[w], linewidth=0.6)
    axes[0, col].set_title(f"{name} - EKG")
    axes[1, col].plot(t, resp[w], linewidth=0.8, color="tab:green")
    axes[1, col].set_title(f"{name} - Solunum")
    axes[1, col].set_xlabel("Zaman (s)")

plt.tight_layout()
plt.show()
