"""Evening reflection: a short note about the day, written by a local LLM from the day's data.

Division of labour (important):
  1. Python computes the day's FACTS (stress periods, calm periods, hourly profile).
     Numbers are deterministic; the LLM does no arithmetic.
  2. The LLM (Ollama, fully local: health data never leaves the computer) turns those
     facts into short, warm prose.
  3. Check: does every number in the reply appear in the facts? If not, it is flagged as
     unverified (small models tend to invent numbers).

Usage:
  python host/reflect.py --date 2026-11-12            # write, store, print
  python host/reflect.py --date 2026-11-12 --facts    # only show the facts sent to the LLM
"""
import argparse
import json
import sys
from datetime import datetime

import db
from llm import DEFAULT_MODEL, chat, unverified_numbers
from metrics import compute

HIGH, CALM = 70, 35   # score thresholds: >=70 clearly above normal, <=35 clearly calm
MIN_EPISODE = 3       # minimum length of a "period" in minutes (single-minute spikes are noise)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reflections (
    date        TEXT PRIMARY KEY,   -- YYYY-MM-DD
    created_ts  TEXT NOT NULL,
    model       TEXT NOT NULL,
    facts_json  TEXT NOT NULL,      -- facts given to the LLM (so the reply can be audited later)
    text        TEXT NOT NULL,
    unverified  TEXT                -- numbers not found in the facts (empty = clean)
);
"""

SYSTEM_PROMPT = """You are Grounded, a calm, warm breathing coach. You write a short evening
reflection about the user's day from measured facts (JSON).

Rules:
- Use ONLY the facts given. Never invent numbers, times or events. Copy numbers exactly.
- Stress score: 50 = the user's personal normal, higher = more stressed than usual.
- You are not a doctor: no diagnoses, no medical advice, no judgement.
- Mention one specific stressful period and one calm period by their times.
- Suggest ONE breathing rhythm from the device: Box (4-4-4-4), 4-7-8, or Relax (4-0-6-0),
  and when to use it tomorrow (tied to when stress happened).
- End with one gentle question the user can reflect on.
- Do not guess causes of stress; describe only what was measured.
- At most 120 words. Plain text, no lists, no headings."""


# --- 1. Facts (deterministic) ---

def runs(rows, cond):
    """Consecutive minutes meeting the condition -> [(start_idx, end_idx), ...]"""
    out, start = [], None
    for i, r in enumerate(rows + [None]):
        ok = r is not None and cond(r)
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= MIN_EPISODE:
                out.append((start, i - 1))
            start = None
    return out


def describe(rows, a, b):
    seg = rows[a:b + 1]
    rates = [r["breath_rate"] for r in seg if r["breath_rate"] is not None]
    return {
        "from": seg[0]["hhmm_start"], "to": seg[-1]["hhmm"],
        "minutes": len(seg),
        "avg_stress": round(sum(r["stress"] for r in seg) / len(seg)),
        "avg_heart_rate": round(sum(r["hr_bpm"] for r in seg) / len(seg)),
        "avg_breaths_per_min": round(sum(rates) / len(rates)) if rates else None,
    }


def day_facts(conn, date):
    cur = conn.execute("""
        SELECT strftime('%H:%M', ts),
               strftime('%H:%M', datetime(ts, '-60 seconds')),
               strftime('%H', ts), stress, hr_bpm, breath_rate, holds
        FROM minute_metrics WHERE date(ts) = ? ORDER BY ts""", (date,))
    rows = [dict(zip(("hhmm", "hhmm_start", "hour", "stress", "hr_bpm", "breath_rate", "holds"), r))
            for r in cur]
    if not rows:
        return None

    n = len(rows)
    high = runs(rows, lambda r: r["stress"] >= HIGH)
    calm = runs(rows, lambda r: r["stress"] <= CALM)
    # Most important stress periods: longest x most intense
    high.sort(key=lambda ab: -sum(rows[i]["stress"] for i in range(ab[0], ab[1] + 1)))
    calm.sort(key=lambda ab: ab[0] - ab[1])   # longest calm period first

    hours = {}
    for r in rows:
        hours.setdefault(r["hour"] + ":00", []).append(r["stress"])

    # Comparison with previous days (if any): the person's own history
    prev = conn.execute("""SELECT AVG(stress) FROM minute_metrics
                           WHERE date(ts) < ? AND date(ts) >= date(?, '-7 days')""",
                        (date, date)).fetchone()[0]

    return {
        "date": date,
        "recorded": {"from": rows[0]["hhmm_start"], "to": rows[-1]["hhmm"], "minutes": n},
        "avg_stress": round(sum(r["stress"] for r in rows) / n),
        "percent_minutes_stressed": round(100 * sum(r["stress"] >= HIGH for r in rows) / n),
        "percent_minutes_calm": round(100 * sum(r["stress"] <= CALM for r in rows) / n),
        "stress_periods": [describe(rows, a, b) for a, b in high[:3]],
        "calm_periods": [describe(rows, a, b) for a, b in calm[:2]],
        "avg_stress_by_hour": {h: round(sum(v) / len(v)) for h, v in sorted(hours.items())},
        "breath_holds": sum(r["holds"] for r in rows),
        "previous_7_days_avg_stress": round(prev) if prev is not None else None,
    }


# --- Main flow ---

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--facts", action="store_true", help="only show the facts, don't call the LLM")
    args = ap.parse_args()

    conn = db.connect()
    conn.executescript(SCHEMA)
    compute(conn)                       # make sure per-minute metrics are up to date
    facts = day_facts(conn, args.date)
    if facts is None:
        print(f"No data for {args.date}.")
        return 1
    if args.facts:
        print(json.dumps(facts, indent=2, ensure_ascii=False))
        return 0

    try:
        text = chat([{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
                    model=args.model)
    except OSError as e:
        print(f"Could not reach Ollama ({e}). Is 'ollama serve' running?")
        return 1

    bad = unverified_numbers(text, facts)
    with conn:
        conn.execute("INSERT OR REPLACE INTO reflections VALUES (?, ?, ?, ?, ?, ?)",
                     (args.date, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), args.model,
                      json.dumps(facts, ensure_ascii=False), text, ",".join(bad) or None))

    print(f"--- Evening reflection, {args.date} ({args.model}) ---\n")
    print(text)
    if bad:
        print(f"\nWARNING: numbers not found in the facts: {', '.join(bad)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
