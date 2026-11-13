"""Step 6d evaluation: how often does text-to-SQL return the right answer?

Execution accuracy: for each question we wrote the correct ("gold") SQL by hand. Both queries
run on the same database; the model passes if every value in the gold result also appears in
its result (and it doesn't just dump many rows). Comparing results instead of SQL text is
fairer: many different queries are correct.

The questions here must not overlap with FEW_SHOT in host/ask.py (that would be leakage).
Expects the simulated week (S3-S8 on 2026-11-06..11, S2 on 2026-11-12).

Usage: python research/eval_ask.py [--model llama3.2]
"""
import argparse
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))
from ask import ask, open_readonly, run_sql  # noqa: E402

TODAY = "2026-11-12"
WEEK = f"date(ts) >= date('{TODAY}', '-6 days')"

CASES = [
    ("Which day this week was the most stressful?",
     f"SELECT date(ts) FROM minute_metrics WHERE {WEEK} GROUP BY 1 ORDER BY AVG(stress) DESC LIMIT 1"),
    ("What was my average stress today?",
     f"SELECT AVG(stress) FROM minute_metrics WHERE date(ts) = '{TODAY}'"),
    ("When was my heart rate highest this week?",
     f"SELECT strftime('%Y-%m-%d %H:%M', ts) FROM minute_metrics WHERE {WEEK} "
     "ORDER BY hr_bpm DESC LIMIT 1"),
    ("How many minutes was I stressed yesterday?",
     f"SELECT COUNT(*) FROM minute_metrics WHERE date(ts) = date('{TODAY}', '-1 day') AND stress >= 70"),
    ("What was my longest breath hold?",
     "SELECT MAX(duration_s) FROM holds"),
    ("On which day did I breathe the slowest on average?",
     "SELECT date(ts) FROM minute_metrics GROUP BY 1 ORDER BY AVG(breath_rate) ASC LIMIT 1"),
    ("What was my average HRV on November 9?",
     "SELECT AVG(rmssd_ms) FROM minute_metrics WHERE date(ts) = '2026-11-09'"),
    ("How many breaths did I take today?",
     f"SELECT COUNT(*) FROM breaths WHERE date(ts) = '{TODAY}'"),
    ("What was my calmest hour today?",
     f"SELECT strftime('%H', ts) FROM minute_metrics WHERE date(ts) = '{TODAY}' "
     "GROUP BY 1 ORDER BY AVG(stress) ASC LIMIT 1"),
    ("Which day had the most breath holds?",
     "SELECT date(start_ts) FROM holds GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1"),
    ("What is my average heart rate when I'm stressed?",
     "SELECT AVG(hr_bpm) FROM minute_metrics WHERE stress >= 70"),
    ("How many days of data do I have?",
     "SELECT COUNT(DISTINCT date(ts)) FROM minute_metrics"),
]

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})")
HHMM = re.compile(r"^(\d{2}):\d{2}")


def cells(rows, expand):
    """All values in the result. With expand, a timestamp also counts as its date,
    its 'YYYY-MM-DD HH:MM' and its hour, so '2026-11-08 14:32:03' answers 'which day'."""
    out = set()
    for row in rows:
        for v in row:
            out.add(v if isinstance(v, (int, float)) else str(v))
            if expand and isinstance(v, str):
                if m := TS.match(v):
                    out |= {m.group(1), f"{m.group(1)} {m.group(2)}:{m.group(3)}", m.group(2)}
                elif m := HHMM.match(v):
                    out.add(m.group(1))
    return out


def contains(pred, gold):
    """Every gold value is in pred. Numbers match within 1% (53.46 vs ROUND(.., 1) = 53.5)."""
    nums = [p for p in pred if isinstance(p, (int, float))]
    for g in gold:
        if isinstance(g, (int, float)):
            if not any(math.isclose(g, p, rel_tol=0.01, abs_tol=0.051) for p in nums):
                return False
        elif g not in pred:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2")
    args = ap.parse_args()
    conn = open_readonly()

    passed, retries, flagged, t0 = 0, 0, 0, time.monotonic()
    for question, gold_sql in CASES:
        _, gold_rows, _ = run_sql(conn, gold_sql)
        gold = cells(gold_rows, expand=False)
        r = ask(question, conn, TODAY, args.model)
        note = ""
        if r["error"]:
            ok, got = False, f"ERROR {r['error']}"
        else:
            pred = cells(r["rows"], expand=True)
            ok = contains(pred, gold) and len(r["rows"]) <= max(3, 2 * len(gold_rows))
            got = sorted(map(str, pred))[:4]
            if r["unverified"]:
                flagged += 1
                note = f"\n      unverified numbers {r['unverified']} in: {r['answer']}"
        passed += ok
        retries += r["attempts"] - 1
        print(f"{'PASS' if ok else 'FAIL'}  {question}{note}")
        if not ok:
            print(f"      expected {sorted(map(str, gold))}, got {got}\n      SQL: {r['sql']}")

    n = len(CASES)
    print(f"\n{args.model}: {passed}/{n} correct ({passed / n:.0%}), {retries} retries, "
          f"{flagged} answers with unverified numbers, {(time.monotonic() - t0) / n:.1f} s/question")


if __name__ == "__main__":
    main()
