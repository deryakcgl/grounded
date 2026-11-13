"""STM32 uzerindeki test icin WESAD'dan kisa parcalar ve beklenen sonuclari uretir.

Cikti: firmware/dsp_target_test/include/test_vectors.h
- Solunum: baseline'dan 60 sn (25 Hz, 1500 ornek)
- EKG:     baseline'dan 10 sn (250 Hz, 2500 ornek)
Veriler int16 olarak saklanir (float'in yarisi kadar flash); kart float'a cevirir.
Beklenen sonuclar: ayni veriyle Mac'teki C++ testinden (firmware/test_native).

Once prepare_data.py calistirilmis olmali.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
NATIVE = ROOT / "firmware/test_native"
OUT = ROOT / "firmware/dsp_target_test/include/test_vectors.h"
VEC = DATA / "vectors"
VEC.mkdir(exist_ok=True)

subject = sys.argv[1] if len(sys.argv) > 1 else "S2"
d = np.load(DATA / f"{subject}_prepared.npz")


def segment(sig, labels, fs, skip_s, length_s):
    start = int(np.argmax(labels == 1)) + skip_s * fs   # baseline (etiket 1)
    return sig[start:start + length_s * fs]


def quantize(x):
    """float -> int16 ve olcek. Kartta: deger = q * olcek (float32 carpimi)."""
    scale = np.float32(np.max(np.abs(x)) / 32000)
    q = np.round(x / scale).astype(np.int16)
    return q, scale, q.astype(np.float32) * scale     # son: kartin gorecegi deger


resp_q, resp_scale, resp_deq = quantize(segment(d["resp"], d["labels_resp"], 25, 60, 60))
ecg_q, ecg_scale, ecg_deq = quantize(segment(d["ecg"], d["labels_ecg"], 250, 120, 10))

# Beklenen sonuclar: kartin gorecegi ayni degerlerle Mac'teki C++
subprocess.run(["make", "-s", "-C", str(NATIVE)], check=True)


def native(kind, values):
    path = VEC / f"target_{kind}.txt"
    np.savetxt(path, values, fmt="%.9g")
    out = subprocess.run([str(NATIVE / "dsp_test"), kind, str(path)],
                         check=True, capture_output=True, text=True).stdout
    return [line.split(",") for line in out.splitlines()]


exp_breaths = [int(r[1]) for r in native("resp", resp_deq) if r[0] == "breath"]
exp_beats = [int(r[1]) for r in native("ecg", ecg_deq) if r[0] == "beat"]


def c_array(ctype, name, values, per_line=16):
    lines = [", ".join(str(int(v)) for v in values[i:i + per_line])
             for i in range(0, len(values), per_line)]
    body = ",\n    ".join(lines)
    return f"static const {ctype} {name}[{len(values)}] = {{\n    {body}\n}};\n"


text = f"""// OTOMATIK URETILDI: research/gen_target_vectors.py ({subject})
// Elle degistirme.
#pragma once
#include <stdint.h>

// ARM'da 'const' diziler otomatik olarak flash'ta kalir (AVR'deki PROGMEM gerekmez).

// Solunum: baseline, 60 sn, 25 Hz
static const float RESP_SCALE = {float(resp_scale):.9g}f;
{c_array("int16_t", "RESP_DATA", resp_q)}
// EKG: baseline, 10 sn, 250 Hz
static const float ECG_SCALE = {float(ecg_scale):.9g}f;
{c_array("int16_t", "ECG_DATA", ecg_q)}
// Beklenen sonuclar (Mac'teki C++ ile ayni veri)
{c_array("int32_t", "EXP_BREATHS", exp_breaths)}
{c_array("int32_t", "EXP_BEATS", exp_beats)}"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(text)
print(f"Yazildi: {OUT}")
print(f"Solunum {len(resp_q)} ornek, EKG {len(ecg_q)} ornek, "
      f"veri {(resp_q.nbytes + ecg_q.nbytes) / 1024:.1f} KB")
print(f"Beklenen: {len(exp_breaths)} nefes, {len(exp_beats)} atim")
