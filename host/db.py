import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "grounded.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS breaths (
    ts          TEXT PRIMARY KEY,
    interval_s  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS holds (
    start_ts    TEXT PRIMARY KEY,
    duration_s  REAL
);
CREATE TABLE IF NOT EXISTS lead_off (
    ts          TEXT PRIMARY KEY,
    bits        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS hrv (
    ts          TEXT PRIMARY KEY,
    rmssd_ms    REAL NOT NULL,
    hr_bpm      REAL NOT NULL
);
"""


def connect(path=DB_PATH):
    path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
