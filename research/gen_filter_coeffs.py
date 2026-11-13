"""Firmware icin filtre katsayilarini ve sabitleri uretir.

Cikti: firmware/lib/grounded_dsp/filter_coeffs.h
Katsayilari elle kopyalamak yerine buradan uretiyoruz: Python'da test ettigimiz
filtre ile cihazdaki filtre her zaman ayni olsun.
"""
import math
from pathlib import Path

from scipy.signal import butter

OUT = Path(__file__).resolve().parent.parent / "firmware/lib/grounded_dsp/filter_coeffs.h"

RESP_FS, ECG_FS = 25, 250
resp_sos = butter(2, [0.05, 1.0], btype="bandpass", fs=RESP_FS, output="sos")
ecg_sos = butter(2, [5, 15], btype="bandpass", fs=ECG_FS, output="sos")


def alpha(tau_s, fs):
    """Ustel hareketli ortalama katsayisi (breath_detector.py ile ayni formul)."""
    return 1.0 - math.exp(-1.0 / (tau_s * fs))


def c_float(v):
    """C float sabiti: 9 basamak float32'yi kayipsiz temsil eder; '1f' gecersiz, '1.0f' olmali."""
    s = f"{v:.9g}"
    if "." not in s and "e" not in s:
        s += ".0"
    return s + "f"


def sos_array(name, sos):
    rows = ",\n".join("    {" + ", ".join(c_float(v) for v in s) + "}" for s in sos)
    return f"static const float {name}[{len(sos)}][6] = {{\n{rows}\n}};\n"


text = f"""// OTOMATIK URETILDI: research/gen_filter_coeffs.py
// Elle degistirme; Python'da degistir ve yeniden uret.
#pragma once

// Solunum: {RESP_FS} Hz, 2. derece Butterworth bant geciren 0.05-1.0 Hz
#define RESP_FS {RESP_FS}
#define RESP_SOS_N {len(resp_sos)}
{sos_array("RESP_SOS", resp_sos)}
static const float BREATH_ALPHA_FAST = {c_float(alpha(4.0, RESP_FS))};   // tau = 4 sn
static const float BREATH_ALPHA_SLOW = {c_float(alpha(60.0, RESP_FS))};  // tau = 60 sn

// EKG: {ECG_FS} Hz, 2. derece Butterworth bant geciren 5-15 Hz
#define ECG_FS {ECG_FS}
#define ECG_SOS_N {len(ecg_sos)}
{sos_array("ECG_SOS", ecg_sos)}
static const float BEAT_ALPHA_NOISE = {c_float(alpha(1.0, ECG_FS))};  // tau = 1 sn
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(text)
print(f"Yazildi: {OUT}")
