"""Cihazdan gelen olaylari okuyup veritabanina yazar.

Kaynaklar:
  sim     Sanal cihaz: firmware'in C++ kodunu Mac'te WESAD verisiyle calistirir
          (firmware/test_native, "device" modu). Gercek cihaz yokken bunu kullaniriz.
  serial  (ileride) Gercek cihaz, seri port uzerinden.

Kullanim:
  python host/ingest.py --source sim --subject S2 --start "2026-11-12 09:00"

Ayni veriyi tekrar yuklemek guvenli: zaman damgasi ayni olan satir atlanir.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import db
from protocol import Breath, HoldEnd, HoldStart, Hrv, parse

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "firmware/test_native"


def sim_lines(subject):
    """Sanal cihazi calistirip protokol satirlarini dondurur."""
    vec = ROOT / "data/vectors"
    vec.mkdir(exist_ok=True)
    resp_file, ecg_file = vec / f"{subject}_resp25.txt", vec / f"{subject}_ecg250.txt"
    if not (resp_file.exists() and ecg_file.exists()):
        d = np.load(ROOT / "data" / f"{subject}_prepared.npz")
        np.savetxt(resp_file, d["resp"], fmt="%.9g")
        np.savetxt(ecg_file, d["ecg"], fmt="%.9g")
    subprocess.run(["make", "-s", "-C", str(NATIVE)], check=True)
    out = subprocess.run([str(NATIVE / "dsp_test"), "device", str(resp_file), str(ecg_file)],
                         check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def ingest(lines, start, conn):
    """Protokol satirlarini veritabanina yazar. Cihaz zamani (ms) + baslangic = gercek saat."""
    def ts(t_ms):
        return (start + timedelta(milliseconds=t_ms)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    counts = {"breath": 0, "hold": 0, "hrv": 0, "bozuk": 0}
    with conn:   # tek islem (transaction): ya hepsi yazilir ya hicbiri
        for line in lines:
            ev = parse(line)
            if isinstance(ev, Breath):
                conn.execute("INSERT OR IGNORE INTO breaths VALUES (?, ?)",
                             (ts(ev.t_ms), ev.interval_ms / 1000))
                counts["breath"] += 1
            elif isinstance(ev, HoldStart):
                conn.execute("INSERT OR IGNORE INTO holds VALUES (?, NULL)", (ts(ev.t_ms),))
                counts["hold"] += 1
            elif isinstance(ev, HoldEnd):
                # Bitis, acik kalan son tutmaya yazilir
                conn.execute("""UPDATE holds SET duration_s = ?
                                WHERE start_ts = (SELECT MAX(start_ts) FROM holds
                                                  WHERE duration_s IS NULL AND start_ts <= ?)""",
                             (ev.duration_ms / 1000, ts(ev.t_ms)))
            elif isinstance(ev, Hrv):
                conn.execute("INSERT OR IGNORE INTO hrv VALUES (?, ?, ?)",
                             (ts(ev.t_ms), ev.rmssd_ms, ev.hr_bpm))
                counts["hrv"] += 1
            else:
                counts["bozuk"] += 1
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim"], default="sim")
    ap.add_argument("--subject", default="S2")
    ap.add_argument("--start", default=datetime.now().strftime("%Y-%m-%d 09:00"),
                    help="Kaydin baslangic saati (varsayilan: bugun 09:00)")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    lines = sim_lines(args.subject)
    conn = db.connect()
    counts = ingest(lines, start, conn)
    print(f"Okunan: {counts['breath']} nefes, {counts['hold']} nefes tutma, "
          f"{counts['hrv']} HRV penceresi, {counts['bozuk']} bozuk satir")

    print("\nSaat saat ozet (veritabanindan):")
    rows = conn.execute("""
        SELECT strftime('%H:00', b.ts)          AS saat,
               COUNT(*) * 60.0 / SUM(b.interval_s) AS nefes_dk,
               (SELECT AVG(rmssd_ms) FROM hrv WHERE strftime('%Y-%m-%d %H', hrv.ts)
                                                   = strftime('%Y-%m-%d %H', b.ts)) AS rmssd,
               (SELECT AVG(hr_bpm) FROM hrv WHERE strftime('%Y-%m-%d %H', hrv.ts)
                                                 = strftime('%Y-%m-%d %H', b.ts)) AS kalp
        FROM breaths b
        WHERE date(b.ts) = date(?)
        GROUP BY strftime('%Y-%m-%d %H', b.ts)
        ORDER BY saat""", (start.strftime("%Y-%m-%d"),)).fetchall()
    print(f"{'Saat':<7}{'Nefes':>10}{'RMSSD':>10}{'Kalp':>9}")
    for saat, nefes, rmssd, kalp in rows:
        print(f"{saat:<7}{nefes:>7.1f}/dk{rmssd:>7.0f} ms{kalp:>6.0f}/dk")
    print(f"\nVeritabani: {db.DB_PATH}")


if __name__ == "__main__":
    sys.exit(main())
