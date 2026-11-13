"""Coach: watches the per-minute stress score and starts a guided breathing session on the desk LED.

Rule (v1, simple and explainable):
  trigger   stress >= 70 for 3 minutes in a row
  rhythm    Relax 4-0-6-0: 6 breaths/min with a long exhale. Slow breathing around 6/min is the
            most studied pace for calming the heart, and it's easy to follow without practice.
  length    6 cycles = 1 minute
  cooldown  no new session within 20 minutes of the previous one (a coach must not nag)
  respect   never interrupt a session the user started with the button

Every session goes into the interventions table with the stress before and after it, so we
can later measure whether guiding helps, and for whom.

Usage:
  python host/coach.py --replay 2026-11-12                 # replay a day, virtual LED, 300x speed
  python host/coach.py --replay 2026-11-12 --led /dev/tty.usbmodem1103   # real LED, real time
  python host/coach.py --report                            # list stored sessions
"""
import argparse
import sys
import time
from datetime import datetime, timedelta

import db
from led import CYCLE_S, RHYTHMS, Button, Done, Rejected, State, guide, open_led

TRIGGER_STRESS = 70
TRIGGER_MINUTES = 3
GUIDE_RHYTHM = 2          # Relax 4-0-6-0
GUIDE_CYCLES = 6
COOLDOWN = timedelta(minutes=20)
AFTER_WINDOW = timedelta(minutes=5)
TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

SCHEMA = """
CREATE TABLE IF NOT EXISTS interventions (
    ts                TEXT PRIMARY KEY,   -- when the session started
    source            TEXT NOT NULL,      -- 'coach' (automatic) or 'button' (the user)
    rhythm            INTEGER NOT NULL,   -- index into the LED's rhythm table
    cycles_requested  INTEGER,
    cycles_done       INTEGER,            -- reported by the LED when the session ends
    reason            TEXT,
    stress_before     REAL,               -- mean stress of the minutes that triggered it
    stress_after      REAL                -- mean stress of the 5 minutes after it ended
);
"""


def decide(window, last_start, now, led_busy):
    """Pure decision: (rhythm, cycles, reason) to start a session now, or None.
    window: the most recent minutes, oldest first, each a dict with 'stress'."""
    if led_busy or len(window) < TRIGGER_MINUTES:
        return None
    if any(m["stress"] < TRIGGER_STRESS for m in window[-TRIGGER_MINUTES:]):
        return None
    if last_start is not None and now - last_start < COOLDOWN:
        return None
    return GUIDE_RHYTHM, GUIDE_CYCLES, f"stress >= {TRIGGER_STRESS} for {TRIGGER_MINUTES} min"


def fill_stress_after(conn):
    """For finished sessions: mean stress in the 5 minutes after the session ended."""
    rows = conn.execute("""SELECT ts, rhythm, cycles_done FROM interventions
                           WHERE stress_after IS NULL AND cycles_done IS NOT NULL""").fetchall()
    with conn:
        for ts, rhythm, done in rows:
            end = datetime.strptime(ts, TS_FORMAT) + timedelta(seconds=done * CYCLE_S[rhythm])
            after = conn.execute(
                "SELECT AVG(stress) FROM minute_metrics WHERE ts > ? AND ts <= ?",
                (end.strftime(TS_FORMAT), (end + AFTER_WINDOW).strftime(TS_FORMAT))).fetchone()[0]
            conn.execute("UPDATE interventions SET stress_after = ? WHERE ts = ?", (after, ts))


def bar(stress):
    return "#" * int(stress / 5)


def replay(conn, date, target, speed):
    minutes = [dict(zip(("ts", "stress", "hr_bpm"), r)) for r in conn.execute(
        "SELECT ts, stress, hr_bpm FROM minute_metrics WHERE date(ts) = ? ORDER BY ts", (date,))]
    if not minutes:
        print(f"No data for {date}.")
        return 1
    with conn:
        n = conn.execute("DELETE FROM interventions WHERE date(ts) = ?", (date,)).rowcount
    if n:
        print(f"(removed {n} sessions from an earlier replay of {date})")

    led = open_led(target, speed)
    sim0 = datetime.strptime(minutes[0]["ts"], TS_FORMAT)
    real0 = time.monotonic()

    def sim_now():
        return sim0 + timedelta(seconds=(time.monotonic() - real0) * speed)

    led_busy, last_start = False, None

    def handle_led():
        nonlocal led_busy
        for msg in led.poll():
            if isinstance(msg, State):
                led_busy = msg.guiding
            elif isinstance(msg, Done):
                print(f"        LED: session done, {msg.cycles_done} cycles of {RHYTHMS[msg.rhythm]}")
                with conn:
                    conn.execute("""UPDATE interventions SET cycles_done = ? WHERE ts =
                                    (SELECT MAX(ts) FROM interventions WHERE cycles_done IS NULL)""",
                                 (msg.cycles_done,))
            elif isinstance(msg, Button):
                ts = sim_now().strftime(TS_FORMAT)[:-3]
                print(f"        LED: user pressed the button -> {RHYTHMS[msg.rhythm]}")
                with conn:
                    conn.execute("INSERT OR REPLACE INTO interventions VALUES (?,?,?,?,NULL,?,NULL,NULL)",
                                 (ts, "button", msg.rhythm, 6, "user started"))
            elif isinstance(msg, Rejected):
                print(f"        LED rejected a command: {msg.message}")

    print(f"Replaying {date}: {len(minutes)} minutes at {speed:g}x, LED = {target}\n")
    for i, m in enumerate(minutes):
        now = datetime.strptime(m["ts"], TS_FORMAT)
        while sim_now() < now:                     # wait for this minute's (simulated) time
            handle_led()
            time.sleep(0.005)
        handle_led()
        print(f"{now:%H:%M}  {m['stress']:3.0f} {bar(m['stress']):<20} HR {m['hr_bpm']:3.0f}")

        window = minutes[max(0, i - TRIGGER_MINUTES + 1):i + 1]
        d = decide(window, last_start, now, led_busy)
        if d:
            rhythm, cycles, reason = d
            led.send(guide(rhythm, cycles))
            led_busy, last_start = True, now
            before = sum(w["stress"] for w in window) / len(window)
            with conn:
                conn.execute("INSERT OR REPLACE INTO interventions VALUES (?,?,?,?,NULL,?,?,NULL)",
                             (m["ts"], "coach", rhythm, cycles, reason, before))
            print(f"        COACH: {reason} -> guide {RHYTHMS[rhythm]} x {cycles}")

    deadline = time.monotonic() + 2.0              # let a running session finish
    while led_busy and time.monotonic() < deadline:
        handle_led()
        time.sleep(0.01)
    led.close()

    fill_stress_after(conn)
    report(conn, date)
    return 0


def report(conn, date=None):
    rows = conn.execute("""SELECT ts, source, rhythm, cycles_done, cycles_requested,
                                  stress_before, stress_after FROM interventions
                           WHERE ? IS NULL OR date(ts) = ? ORDER BY ts""", (date, date)).fetchall()
    print(f"\n{len(rows)} session(s){' on ' + date if date else ''}:")
    for ts, src, rhythm, done, req, before, after in rows:
        b = f"{before:.0f}" if before is not None else "-"
        a = f"{after:.0f}" if after is not None else "-"
        print(f"  {ts[:16]}  {src:<6} {RHYTHMS[rhythm]:<14} {done if done is not None else '?'}/{req}"
              f" cycles   stress before {b:>3} -> after {a:>3}")
    if any(r[5] is not None and r[6] is not None for r in rows):
        print("  Note: with replayed WESAD data the LED can't change the recorded stress, so")
        print("  'after' only tests the plumbing. With a real user this is where we see if it helps.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", metavar="DATE")
    ap.add_argument("--led", default="sim", help="'sim' or a serial port")
    ap.add_argument("--speed", type=float, default=300.0, help="replay speed (virtual LED only)")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    conn = db.connect()
    conn.executescript(SCHEMA)
    if args.report:
        report(conn)
        return 0
    if not args.replay:
        ap.error("use --replay DATE or --report")
    speed = args.speed
    if args.led != "sim" and speed != 1.0:
        print("Real LED: the pacing runs in real time, so the replay does too (speed 1).")
        speed = 1.0
    return replay(conn, args.replay, args.led, speed)


if __name__ == "__main__":
    sys.exit(main())
