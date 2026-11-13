"""Dakikalik metrikler ve stres skoru (kural tabanli, v1).

Her HRV penceresi (60 sn) icin:
  - nefes hizi ve nefes duzensizligi (o dakikadaki nefeslerden)
  - RMSSD ve kalp hizi (cihazdan)
  - stres skoru 0-100: 50 = senin normalin, yukari = normalinden stresli

Skor, kisinin KENDI normaline gore hesaplanir (mutlak esik yok):
  z = (deger - kisisel medyan) / kisisel yayilim   (medyan ve MAD: aykiri degerlere dayanikli)
  ham = 0.50 * z(-ln RMSSD) + 0.25 * z(kalp hizi) + 0.25 * z(nefes duzensizligi)
  skor = 100 / (1 + e^-ham)

Neden nefes HIZI yok: WESAD'da stres sirasinda nefes hizi dustu (konusma etkisi),
meditasyonda da dustu; hiz tek basina stresi ayirt etmiyor. Duzensizlik ise ediyor.
Agirliklar elle secildi (v1). Ileride cok kisili veriyle ogrenilecek (ML).

Kullanim:  python host/metrics.py
"""
import math
import sys

import numpy as np

import db

WEIGHTS = {"neg_ln_rmssd": 0.50, "hr_bpm": 0.25, "breath_cv": 0.25}

SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_metrics (
    ts           TEXT PRIMARY KEY,   -- 60 sn'lik pencerenin sonu (hrv.ts ile ayni)
    breath_rate  REAL,               -- nefes / dk
    breath_cv    REAL,               -- nefes araliklarinin degisim katsayisi (std/ort)
    holds        INTEGER,            -- bu dakikada baslayan nefes tutma sayisi
    rmssd_ms     REAL,
    hr_bpm       REAL,
    stress       REAL                -- 0-100, 50 = kisisel normal
);
"""


def robust_z(x):
    """Kisisel medyana gore sapma, MAD ile olceklenmis (1.4826: normal dagilimda std'ye esitler)."""
    med = np.nanmedian(x)
    mad = 1.4826 * np.nanmedian(np.abs(x - med))
    return (x - med) / (mad if mad > 0 else 1.0)


def compute(conn):
    conn.executescript(SCHEMA)
    windows = conn.execute("SELECT ts, rmssd_ms, hr_bpm FROM hrv ORDER BY ts").fetchall()

    rows = []
    for ts, rmssd, hr in windows:
        intervals = np.array([r[0] for r in conn.execute(
            "SELECT interval_s FROM breaths WHERE ts > datetime(?, '-60 seconds') AND ts <= ?",
            (ts, ts))])
        holds = conn.execute(
            "SELECT COUNT(*) FROM holds WHERE start_ts > datetime(?, '-60 seconds') AND start_ts <= ?",
            (ts, ts)).fetchone()[0]
        if len(intervals) >= 3:
            rate = 60.0 / intervals.mean()
            cv = intervals.std() / intervals.mean()
        else:   # cok az nefes: hiz/duzensizlik guvenilir degil
            rate = cv = math.nan
        rows.append((ts, rate, cv, holds, rmssd, hr))

    if not rows:
        return 0
    rate, cv, rmssd, hr = (np.array([r[i] for r in rows], dtype=float) for i in (1, 2, 4, 5))
    features = {"neg_ln_rmssd": -np.log(rmssd), "hr_bpm": hr, "breath_cv": cv}
    raw = sum(w * np.nan_to_num(robust_z(features[k])) for k, w in WEIGHTS.items())
    stress = 100.0 / (1.0 + np.exp(-raw))

    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO minute_metrics VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(r[0], None if math.isnan(r[1]) else r[1], None if math.isnan(r[2]) else r[2],
              r[3], r[4], r[5], float(s)) for r, s in zip(rows, stress)])
    return len(rows)


def main():
    conn = db.connect()
    n = compute(conn)
    print(f"{n} dakika hesaplandi.\n")
    print(f"{'Saat':<7}{'Stres':>7}{'RMSSD':>9}{'Kalp':>7}{'Nefes':>8}{'Duzensiz':>10}")
    for row in conn.execute("""
        SELECT strftime('%H:%M', ts), stress, rmssd_ms, hr_bpm, breath_rate, breath_cv
        FROM minute_metrics ORDER BY ts"""):
        saat, s, rm, hr, br, cv = row
        bar = "#" * int(s / 5)
        print(f"{saat:<7}{s:>6.0f} {rm:>6.0f}ms{hr:>6.0f}{(br or 0):>7.1f}{(cv or 0):>9.2f}  {bar}")


if __name__ == "__main__":
    sys.exit(main())
