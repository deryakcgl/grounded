"""Ask questions about your data in plain English (text-to-SQL with a local LLM).

Flow:
  question -> LLM writes ONE SQLite query -> query runs in a locked-down connection
           -> (on error: the error goes back to the LLM, up to MAX_RETRIES)
           -> LLM answers from the returned rows -> invented-number check

The LLM's SQL is never trusted. Three independent guards:
  1. The database is opened READ-ONLY (SQLite itself refuses writes).
  2. An authorizer: SQLite asks us about every action the query would take;
     only SELECT and reading the allowed tables is permitted (no sqlite_master,
     no ATTACH, no PRAGMA, no writes).
  3. Limits: queries are aborted after QUERY_TIMEOUT_S, and at most MAX_ROWS rows are read.
(sqlite3's execute() also refuses more than one statement per call.)

Usage:
  python host/ask.py "Which day this week was the most stressful?"
  python host/ask.py --sql "..."          # also print the generated SQL
  python host/ask.py                      # interactive
"""
import argparse
import re
import sqlite3
import sys
import time
from datetime import datetime

import db
from llm import DEFAULT_MODEL, chat, unverified_numbers

ALLOWED_TABLES = {"minute_metrics", "breaths", "holds", "hrv"}
MAX_ROWS = 50
QUERY_TIMEOUT_S = 2.0
MAX_RETRIES = 2

SCHEMA_DOC = """SQLite tables. Timestamps are TEXT in local time, 'YYYY-MM-DD HH:MM:SS.fff'.
Use date(ts), time(ts), strftime('%H', ts) etc. on them.

minute_metrics   -- one row per minute (the 60 s window ending at ts). Use this table for most questions.
  ts           TEXT
  breath_rate  REAL     breaths per minute (can be NULL)
  breath_cv    REAL     breathing irregularity, 0 = perfectly regular (can be NULL)
  holds        INTEGER  breath holds that started in this minute
  rmssd_ms     REAL     heart rate variability (HRV); higher = more relaxed
  hr_bpm       REAL     heart rate, beats per minute
  stress       REAL     0-100; 50 = the user's personal normal, >= 70 = stressed, <= 35 = calm

breaths          -- one row per detected breath
  ts           TEXT
  interval_s   REAL     seconds since the previous breath

holds            -- breath holds longer than 10 seconds
  start_ts     TEXT
  duration_s   REAL     length of the hold in seconds (NULL while still holding)

hrv              -- the same minutes as minute_metrics (ts, rmssd_ms, hr_bpm); prefer minute_metrics"""

SQL_PROMPT = """You translate questions about the user's breathing and heart data into ONE SQLite query.

{schema}

Rules:
- Today is {today}. "Yesterday" = date('{today}', '-1 day').
  "This week" = the last 7 days including today: date(ts) >= date('{today}', '-6 days').
- Write a single SELECT statement. Only the tables above.
- Return only the columns needed to answer. Round averages with ROUND(x, 1).
- For "when" questions return the moment, not just the day: strftime('%Y-%m-%d %H:%M', ts),
  and pick the row with ORDER BY ... LIMIT 1 (not MAX() next to a date column).
- If the question cannot be answered from these tables, return: SELECT 'cannot answer' AS error;
- Reply with only the SQL inside a ```sql block, no explanation."""

# Worked examples help small models a lot. They must NOT overlap with the evaluation
# questions in research/eval_ask.py, otherwise the score would be inflated (leakage).
FEW_SHOT = [
    ("What was my average heart rate yesterday?",
     "SELECT ROUND(AVG(hr_bpm), 1) AS avg_hr FROM minute_metrics "
     "WHERE date(ts) = date('{today}', '-1 day');"),
    ("How many breath holds did I have this week?",
     "SELECT COUNT(*) AS holds FROM holds WHERE date(start_ts) >= date('{today}', '-6 days');"),
    ("Show my stress by hour today.",
     "SELECT strftime('%H:00', ts) AS hour, ROUND(AVG(stress), 1) AS avg_stress "
     "FROM minute_metrics WHERE date(ts) = '{today}' GROUP BY hour ORDER BY hour;"),
]

ANSWER_PROMPT = """You are Grounded, a calm breathing coach. Answer the user's question in 1-3 short
sentences, using ONLY the query result below. Copy numbers exactly as given (you may drop decimals).
Stress score: 50 = the user's normal, >= 70 = stressed, <= 35 = calm. HRV (RMSSD): higher = more relaxed.
No medical advice. If the result is empty or says 'cannot answer', say you don't have data for that."""


# --- 1. LLM -> SQL ---

def extract_sql(text):
    """Takes the SQL out of the reply (```sql ... ``` block, or the whole reply)."""
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()


def generate_sql(question, today, model, history=()):
    msgs = [{"role": "system", "content": SQL_PROMPT.format(schema=SCHEMA_DOC, today=today)}]
    for q, sql in FEW_SHOT:
        msgs += [{"role": "user", "content": q},
                 {"role": "assistant", "content": f"```sql\n{sql.format(today=today)}\n```"}]
    msgs.append({"role": "user", "content": question})
    msgs += list(history)                    # earlier failed attempts and their errors
    return extract_sql(chat(msgs, model=model, temperature=0.0))   # 0: SQL should be deterministic


# --- 2. Locked-down execution ---

def _authorizer(action, arg1, arg2, dbname, source):
    """Called by SQLite for every action in the query while it is compiled."""
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:        # arg1 = table name
        return sqlite3.SQLITE_OK if arg1 in ALLOWED_TABLES else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK             # date(), AVG(), ROUND() ...
    # Everything else: writes, ATTACH, PRAGMA, ... Recursive CTEs are refused too: they
    # read their own name like a table. Not needed for these questions, and it removes
    # the easiest way to write an endless query.
    return sqlite3.SQLITE_DENY


def open_readonly(path=db.DB_PATH):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.set_authorizer(_authorizer)
    return conn


def run_sql(conn, sql):
    """Runs the query with the guards. Returns (column names, rows, truncated).
    Raises sqlite3.Error with a readable message if the query is refused or fails."""
    deadline = time.monotonic() + QUERY_TIMEOUT_S
    # Called every N virtual-machine steps; a non-zero return aborts the query.
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1)
    finally:
        conn.set_progress_handler(None, 0)
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, rows[:MAX_ROWS], len(rows) > MAX_ROWS


# --- 3. Rows -> answer ---

def tidy(v):
    """Round floats the way a person would say them, so the answer can copy them exactly."""
    if isinstance(v, float):
        return round(v) if abs(v) >= 10 else round(v, 2)
    return v


def answer(question, cols, rows, model):
    table = [dict(zip(cols, map(tidy, r))) for r in rows]
    reply = chat([{"role": "system", "content": ANSWER_PROMPT},
                  {"role": "user", "content": f"Question: {question}\nQuery result: {table}"}],
                 model=model)
    return reply, table


def ask(question, conn, today, model=DEFAULT_MODEL):
    """Full pipeline. Returns a dict with sql, attempts, cols, rows, answer, unverified, error."""
    history, sql, err = [], None, None
    for attempt in range(1 + MAX_RETRIES):
        sql = generate_sql(question, today, model, history)
        try:
            cols, rows, truncated = run_sql(conn, sql)
            break
        except (sqlite3.Error, sqlite3.Warning) as e:   # Warning: e.g. more than one statement
            err = str(e)
            history += [{"role": "assistant", "content": f"```sql\n{sql}\n```"},
                        {"role": "user", "content": f"That query failed: {err}. "
                                                    "Fix it and reply with only the SQL."}]
    else:
        return {"sql": sql, "attempts": attempt + 1, "error": err}

    text, table = answer(question, cols, rows, model)
    return {"sql": sql, "attempts": attempt + 1, "cols": cols, "rows": rows,
            "truncated": truncated, "answer": text,
            "unverified": unverified_numbers(text, {"question": question, "rows": table}), "error": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--sql", action="store_true", help="print the generated SQL and rows")
    ap.add_argument("--today", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    conn = open_readonly()
    questions = [args.question] if args.question else iter(lambda: input("\nask> ").strip(), "")
    for q in questions:
        try:
            r = ask(q, conn, args.today, args.model)
        except OSError as e:
            print(f"Could not reach Ollama ({e}). Is 'ollama serve' running?")
            return 1
        if args.sql or r["error"]:
            print(f"SQL ({r['attempts']} attempt(s)): {r['sql']}")
        if r["error"]:
            print(f"Could not answer: {r['error']}")
            continue
        if args.sql:
            print(f"Rows: {r['rows'][:10]}{' ...' if len(r['rows']) > 10 else ''}\n")
        print(r["answer"])
        if r["unverified"]:
            print(f"(WARNING: numbers not found in the query result: {', '.join(r['unverified'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
