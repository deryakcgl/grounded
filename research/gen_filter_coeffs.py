import math
from pathlib import Path

from scipy.signal import butter

OUT = Path(__file__).resolve().parent.parent / "firmware/lib/grounded_dsp/filter_coeffs.h"

RESP_FS, ECG_FS = 25, 250
resp_sos = butter(2, [0.05, 1.0], btype="bandpass", fs=RESP_FS, output="sos")
ecg_sos = butter(2, [5, 15], btype="bandpass", fs=ECG_FS, output="sos")


def alpha(tau_s, fs):
    return 1.0 - math.exp(-1.0 / (tau_s * fs))


def c_float(v):
    s = f"{v:.9g}"
    if "." not in s and "e" not in s:
        s += ".0"
    return s + "f"


def sos_array(name, sos):
    rows = ",\n".join("    {" + ", ".join(c_float(v) for v in s) + "}" for s in sos)
    return f"static const float {name}[{len(sos)}][6] = {{\n{rows}\n}};\n"


text = f"""
#pragma once

#define RESP_FS {RESP_FS}
#define RESP_SOS_N {len(resp_sos)}
{sos_array("RESP_SOS", resp_sos)}
static const float BREATH_ALPHA_FAST = {c_float(alpha(4.0, RESP_FS))};
static const float BREATH_ALPHA_SLOW = {c_float(alpha(60.0, RESP_FS))};

#define ECG_FS {ECG_FS}
#define ECG_SOS_N {len(ecg_sos)}
{sos_array("ECG_SOS", ecg_sos)}
static const float BEAT_ALPHA_NOISE = {c_float(alpha(1.0, ECG_FS))};
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(text.lstrip())
print(f"Wrote: {OUT}")
