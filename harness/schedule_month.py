"""Monthly schedule (stretch goal): run last month's whole-month check once a month, unattended.

    python harness/schedule_month.py                      # forever: day 2 of each month, 07:10 IST
    python harness/schedule_month.py --day 1 --at 06:40   # another slot
    python harness/schedule_month.py --next               # just print when it would fire next
    python harness/schedule_month.py --now                # run last month right away (once)

    docker compose --profile scheduler up -d              # the same, as a container

Each run calls harness/run_month.py for the previous month and writes the logistics manager's
summary to runs/month/<YYYY-MM>/summary.md (also shown on the operator screen's Monthly summary).

What still needs a person: if the saved portal session has expired, the portal asks for an OTP.
The run then waits (up to 15 minutes) in the operator screen's Needs you page, which beeps and
flashes; nobody answers -> the run ends as needs_human and the next attempt is an hour later
(max 3 attempts). A scheduled run never raises a dispute; it lists the ones to raise.

A cron line does the same job if you prefer the OS scheduler:
    10 7 2 * *  cd /path/to/Meridian-adv && python harness/run_month.py --mode live
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from run_month import previous_month  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
STATE = ROOT / "runs" / "month" / "schedule.json"


def next_fire(now: datetime, day: int, at: str) -> datetime:
    """Next `day`-of-month at `at` (HH:MM, IST) strictly after `now`."""
    hh, mm = (int(x) for x in at.split(":"))
    y, m = now.year, now.month
    for _ in range(3):
        cand = datetime(y, m, day, hh, mm, tzinfo=IST)
        if cand > now:
            return cand
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    raise AssertionError("unreachable")


def run_month(month: str, mode: str, workers: int) -> int:
    cmd = [sys.executable, str(ROOT / "harness" / "run_month.py"), "--mode", mode, "--month", month,
           "--workers", str(workers)]
    print(f"{datetime.now(IST):%Y-%m-%d %H:%M} IST · running {' '.join(cmd[1:])}", flush=True)
    return subprocess.call(cmd, cwd=ROOT)


def done_months() -> set[str]:
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")).get("done", []))
    except Exception:
        return set()


def mark_done(month: str) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"done": sorted(done_months() | {month})}, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", type=int, default=2, help="day of the month to run (1-28)")
    ap.add_argument("--at", default="07:10", help="time of day, HH:MM in IST")
    ap.add_argument("--mode", choices=["fake", "live"], default="live")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--attempts", type=int, default=3, help="tries per month, an hour apart")
    ap.add_argument("--next", action="store_true", help="print the next run time and exit")
    ap.add_argument("--now", action="store_true", help="run last month once, now, and exit")
    args = ap.parse_args()
    if not 1 <= args.day <= 28:
        sys.exit("--day must be 1-28 (every month has it)")

    if args.now:
        sys.exit(run_month(previous_month(datetime.now(IST).date()), args.mode, args.workers))
    if args.next:
        print(next_fire(datetime.now(IST), args.day, args.at).isoformat())
        return

    while True:
        fire = next_fire(datetime.now(IST), args.day, args.at)
        print(f"next whole-month run: {fire:%d %b %Y %H:%M} IST", flush=True)
        time.sleep(max(0.0, (fire - datetime.now(IST)).total_seconds()))
        month = previous_month(fire.date())
        if month in done_months():
            continue  # restarted container on the same day: don't run twice
        for attempt in range(1, args.attempts + 1):
            if run_month(month, args.mode, args.workers) == 0:
                mark_done(month)
                break
            if attempt < args.attempts:
                print(f"attempt {attempt} did not finish; retrying in an hour", flush=True)
                time.sleep(3600)


if __name__ == "__main__":
    main()
