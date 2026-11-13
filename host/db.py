"""SQLite veritabani: cihazdan gelen olaylarin kalici kaydi.

Konum: data/grounded.db. data/ git'e girmez; saglik verisi asla repoya girmemeli.
Zamanlar yerel saatle 'YYYY-MM-DD HH:MM:SS.fff' metni: SQLite'in tarih
fonksiyonlari bunu anlar, insan (ve ileride LLM) de kolayca okur.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "grounded.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS breaths (
    ts          TEXT PRIMARY KEY,   -- nefesin zamani
    interval_s  REAL NOT NULL       -- onceki nefesten bu yana gecen sure
);
CREATE TABLE IF NOT EXISTS holds (
    start_ts    TEXT PRIMARY KEY,   -- son nefesin zamani (tutma burada basladi)
    duration_s  REAL                -- bitince doldurulur; NULL = devam ediyor
);
CREATE TABLE IF NOT EXISTS hrv (
    ts          TEXT PRIMARY KEY,   -- 60 sn'lik pencerenin bittigi an
    rmssd_ms    REAL NOT NULL,      -- yuksek = rahat
    hr_bpm      REAL NOT NULL
);
"""


def connect(path=DB_PATH):
    path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
