"""SQLite database: the persistent record of events coming from the device.

Location: data/grounded.db. data/ is not in git; health data must never enter the repo.
Times are local time as 'YYYY-MM-DD HH:MM:SS.fff' text: SQLite's date functions
understand it, and humans (and later the LLM) can read it easily.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "grounded.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS breaths (
    ts          TEXT PRIMARY KEY,   -- time of the breath
    interval_s  REAL NOT NULL       -- time since the previous breath
);
CREATE TABLE IF NOT EXISTS holds (
    start_ts    TEXT PRIMARY KEY,   -- time of the last breath (the hold started here)
    duration_s  REAL                -- filled in when it ends; NULL = still holding
);
CREATE TABLE IF NOT EXISTS hrv (
    ts          TEXT PRIMARY KEY,   -- end of the 60 s window
    rmssd_ms    REAL NOT NULL,      -- higher = more relaxed
    hr_bpm      REAL NOT NULL
);
"""


def connect(path=DB_PATH):
    path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
