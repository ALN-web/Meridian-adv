"""Stretch goal: reconcile a whole month (every lane) in parallel browser contexts.

Examples
    # local fake portal (start it first: python -m meridian.fakeportal.server); OTP read from the
    # fake inbox by the harness, as the test operator would
    python harness/run_month.py --mode fake --month 2026-10 --workers 4 --compare

    # real portal: a person types the OTP in the operator screen (Needs you), or in this terminal
    python harness/run_month.py --mode live --month 2026-10 --workers 4
    python harness/run_month.py --mode live --month 2026-10 --workers 4 --console-otp

--compare first runs the same month with ONE context (the sequential baseline), then with
--workers contexts, both without the disk caches so neither gets a head start, and puts both
times in the summary.

Output: runs/month/<YYYY-MM>/summary.md (for the logistics manager), invoices.csv, report.json.
The run is also stored like any task, so it shows in the operator screen (Results, Monthly summary).
A month run never raises a dispute: it lists the ones to raise, each still needing approval.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "harness"))

from meridian.agent.live import run_async  # noqa: E402
from meridian.agent.modes import fake_settings, portal_reachable  # noqa: E402
from meridian.agent.month import MONTH_STEPS, Cancelled, MonthRunner, write_summary  # noqa: E402
from meridian.config import get_settings  # noqa: E402
from meridian.portal.errors import HumanNeeded, LoginFailed  # noqa: E402
from meridian.store import Store  # noqa: E402
from meridian.telemetry import TaskTracer  # noqa: E402


def previous_month(today: date | None = None) -> str:
    today = today or date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def run_once(store: Store, settings, args, workers: int, *, cache: bool, label: str) -> dict:
    text = f"Reconcile every lane for {args.month} in parallel ({workers} browser contexts). Do not raise disputes."
    run_id = store.create_run(f"MONTH-{args.month}", text, "month",
                              {"month": args.month, "lanes": args.lanes, "workers": workers}, MONTH_STEPS, args.mode)
    store.set_status(run_id, "running")
    tracer = TaskTracer(run_id, f"MONTH-{args.month}", text, "month", args.mode, settings=settings)
    store.subscribe(run_id, tracer)
    human = None
    if args.console_otp:
        from meridian.portal.human import ConsoleHumanGate

        human = ConsoleHumanGate()
    runner = MonthRunner(settings, args.month, lanes=args.lanes, workers=workers, human=human, store=store,
                         run_id=run_id, headless=not args.headed, use_disk_cache=cache)
    print(f"[{label}] {workers} context(s) · run {run_id}")
    try:
        result = run_async(runner.run())
        status = result["status"]
    except Cancelled:
        result, status = {"error": "stopped by operator"}, "failed"
    except (HumanNeeded, LoginFailed) as exc:
        result, status = {"error": str(exc)}, "needs_human"
    except Exception as exc:
        result, status = {"error": f"{type(exc).__name__}: {exc}"[:300]}, "failed"
    details = result.pop("_details", {})
    result.update(task_id=f"MONTH-{args.month}", trace_id=tracer.trace_id)
    if tracer.url:
        result["trace_url"] = tracer.url
    store.unsubscribe(run_id)
    tracer.finish(status, result)
    store.set_status(run_id, status, result=result, error=result.get("error"))
    result["_details"] = details
    print(f"[{label}] {status} in {result.get('duration_s', '?')} s · {result.get('requests', '?')} requests "
          f"at {result.get('requests_per_s', '?')}/s · {len(result.get('invoices', []))} invoices")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["fake", "live"], default="fake")
    ap.add_argument("--month", default=None, help="YYYY-MM (invoice-date month); default: last month")
    ap.add_argument("--lanes", default=None, help="comma-separated, e.g. PUN-BLR,PUN-HYD; default: every lane")
    ap.add_argument("--workers", type=int, default=4, help="parallel browser contexts (one shared 2 req/s limit)")
    ap.add_argument("--compare", action="store_true", help="also run with 1 context first, for the speed-up")
    ap.add_argument("--console-otp", action="store_true", help="ask for the OTP in this terminal instead of the operator screen")
    ap.add_argument("--headed", action="store_true", help="show the browser windows")
    ap.add_argument("--out", default=None, help="output folder; default runs/month/<month>")
    args = ap.parse_args()
    args.month = args.month or previous_month()
    args.lanes = [x.strip() for x in args.lanes.split(",")] if args.lanes else None

    ok, msg = portal_reachable(args.mode)
    if not ok:
        sys.exit(msg)
    settings = fake_settings() if args.mode == "fake" else get_settings()
    if args.mode == "live" and not settings.portal_password.get_secret_value():
        sys.exit("PORTAL_PASSWORD missing in .env")
    store = Store()

    auto = None
    if args.mode == "fake" and not args.console_otp:
        from run_public import AutoHuman  # reads the FAKE portal's inbox only, as its test operator

        auto = AutoHuman(store, otp=True, approve=False, mode="fake")
        auto.start()
    try:
        sequential_s = None
        if args.compare:
            # a fresh login for the baseline too, so both runs pay the same start-up
            shutil.rmtree(ROOT / ".auth", ignore_errors=True) if args.mode == "fake" else None
            base = run_once(store, settings, args, 1, cache=False, label="sequential")
            sequential_s = base.get("duration_s")
        report = run_once(store, settings, args, args.workers, cache=not args.compare, label="parallel")
    finally:
        if auto:
            auto.stop.set()
    if "lanes" not in report:
        sys.exit(f"month run did not finish: {report.get('error')}")
    files = write_summary(report, args.out or f"runs/month/{args.month}", sequential_s=sequential_s)
    print(f"Summary for the logistics manager: {files['summary']}")
    if sequential_s:
        print(f"Sequential {sequential_s} s -> parallel {report['duration_s']} s "
              f"({sequential_s / report['duration_s']:.1f}x faster)")


if __name__ == "__main__":
    main()
