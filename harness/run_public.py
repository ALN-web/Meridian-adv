"""Test harness: run every public task, score against an answer key, write the evaluation report.

Examples
    # demo portal, fully unattended (OTP and approvals auto-answered — demo only)
    python harness/run_public.py --mode demo --auto-otp --auto-approve

    # also re-run dispute tasks to prove no duplicate disputes
    python harness/run_public.py --mode demo --auto-otp --auto-approve --rerun-disputes

    # score against a key, or snapshot this run as a regression key
    python harness/run_public.py --mode demo --auto-otp --auto-approve --key harness/answer_keys/demo.json
    python harness/run_public.py --mode demo --auto-otp --auto-approve --save-key harness/answer_keys/demo.json

    # refresh the task list from the portal (TEAM_KEY from .env, never from the command line)
    python harness/run_public.py --fetch-tasks

Live mode waits for a person in the operator screen for OTPs and approvals (the brief allows
nothing else to be manual). It is enabled once the Playwright runner is wired to the portal.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meridian.agent import demo  # noqa: E402
from meridian.agent.planner import Plan, plan_task  # noqa: E402
from meridian.evaluation import TARGETS, key_from_results, score_task, summarise, to_dict  # noqa: E402
from meridian.store import Store  # noqa: E402

TASKS_FILE = ROOT / "harness" / "tasks_public.json"
PUBLISHED = ROOT / "eval_results"


def fetch_tasks() -> None:
    import httpx

    from meridian.config import get_settings

    s = get_settings()
    key = s.team_key.get_secret_value()
    if not key:
        sys.exit("TEAM_KEY missing in .env")
    r = httpx.get(f"{s.portal_base_url.rstrip('/')}/internal/tasks.json", params={"key": key}, timeout=120)
    r.raise_for_status()
    TASKS_FILE.write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
    print(f"Saved {len(r.json()['tasks'])} tasks to {TASKS_FILE.relative_to(ROOT)}")


def load_tasks(only: set[str] | None) -> list[dict]:
    tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))["tasks"]
    return [t for t in tasks if not only or t["task_id"] in only]


def plan_for(task: dict) -> Plan:
    """Use the task's structured params when given; check they agree with the planner's reading."""
    plan = plan_task(task["task"])
    if task.get("kind") and task.get("params"):
        if (plan.kind, plan.params) != (task["kind"], task["params"]):
            print(f"  ! planner read {task['task_id']} as {plan.kind} {plan.params}; using given {task['kind']} {task['params']}")
            plan = Plan(task["kind"], task["params"], plan.steps)
    return plan


class AutoHuman(threading.Thread):
    """Demo-only stand-in for the operator: answers OTPs and/or approves disputes."""

    def __init__(self, store: Store, otp: bool, approve: bool):
        super().__init__(daemon=True)
        self.store, self.otp, self.approve = store, otp, approve
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            if self.otp:
                for r in self.store.pending_human():
                    if r["kind"] == "otp":
                        self.store.answer_human(r["id"], "000000")
            if self.approve:
                for d in self.store.disputes(status="pending"):
                    self.store.decide_dispute(d["id"], True, by="harness-auto")
            time.sleep(0.05)


def run_one(store: Store, task: dict, timeout_s: float) -> dict:
    plan = plan_for(task)
    run_id = store.create_run(task["task_id"], task["task"], plan.kind, plan.params, plan.steps, "demo")
    t0 = time.time()
    demo.DemoRunner(store, run_id, plan, task["task_id"]).start()
    while time.time() - t0 < timeout_s:
        run = store.get_run(run_id)
        if run.status in ("completed", "needs_human", "failed"):
            return run.result or {"task_id": task["task_id"], "status": run.status}
        time.sleep(0.1)
    store.set_status(run_id, "failed", error="harness timeout")
    return {"task_id": task["task_id"], "status": "failed", "error": "timeout"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["demo", "live"], default="demo")
    ap.add_argument("--only", help="comma-separated task ids, e.g. T-01,T-19")
    ap.add_argument("--key", help="answer key JSON to score against")
    ap.add_argument("--save-key", help="write this run's results as a regression key")
    ap.add_argument("--auto-otp", action="store_true", help="demo only: answer OTP prompts automatically")
    ap.add_argument("--auto-approve", action="store_true", help="demo only: approve every proposed dispute")
    ap.add_argument("--rerun-disputes", action="store_true", help="run dispute tasks a second time to check duplicates")
    ap.add_argument("--label", default=None)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--fast", action="store_true", help="demo only: no artificial step delay")
    ap.add_argument("--fetch-tasks", action="store_true")
    args = ap.parse_args()

    if args.fetch_tasks:
        fetch_tasks()
        return
    if args.mode == "live":
        sys.exit("Live mode needs the Playwright runner wired to the portal (after recon). Use --mode demo for now.")
    if args.fast:
        demo.STEP_DELAY = 0.0

    label = args.label or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "runs" / "eval" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    store = Store(out_dir / "store.sqlite")
    helper = AutoHuman(store, args.auto_otp, args.auto_approve)
    helper.start()
    if not args.auto_otp:
        print("OTP prompts will wait for you in the operator screen (or pass --auto-otp in demo mode).")

    tasks = load_tasks(set(args.only.split(",")) if args.only else None)
    key = json.loads(Path(args.key).read_text(encoding="utf-8")) if args.key else {}
    results, kinds = {}, {}
    started = time.time()
    for t in tasks:
        print(f"> {t['task_id']} {t['kind']:<10} {t['task'][:80]}")
        r = run_one(store, t, args.timeout)
        results[t["task_id"]], kinds[t["task_id"]] = r, t["kind"]
        print(f"  {r.get('status')}  steps={r.get('steps')} retries={r.get('retries')} {r.get('duration_s')}s")

    rerun = {}
    if args.rerun_disputes:
        for t in [t for t in tasks if t["kind"] == "dispute"]:
            print(f"> rerun {t['task_id']} (must raise no new disputes)")
            rerun[t["task_id"]] = run_one(store, t, args.timeout)
            print(f"  new disputes on rerun: {len(rerun[t['task_id']].get('disputes') or [])}")
    helper.stop.set()

    confirmed = Counter(d["invoice_no"] for d in store.disputes() if d["status"] in ("submitted", "confirmed"))
    duplicates = sum(c - 1 for c in confirmed.values() if c > 1)
    duplicates += sum(len(r.get("disputes") or []) for r in rerun.values())

    scores = [score_task(tid, kinds[tid], results[tid], key.get(tid) if key else None) for tid in results]
    metrics = summarise(scores, duplicates)
    if not key:
        metrics["task_success"] = metrics["invoice_accuracy"] = None
        metrics["pass"]["task_success"] = metrics["pass"]["invoice_accuracy"] = None

    report = {
        "label": label,
        "mode": args.mode,
        "answer_key": args.key,
        "auto_otp": args.auto_otp,
        "auto_approve": args.auto_approve,
        "started": datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "wall_time_s": round(time.time() - started, 1),
        "targets": TARGETS,
        "metrics": metrics,
        "tasks": [to_dict(s) for s in scores],
        "reruns": {tid: {"status": r.get("status"), "new_disputes": len(r.get("disputes") or [])} for tid, r in rerun.items()},
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    PUBLISHED.mkdir(exist_ok=True)
    (PUBLISHED / "latest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (PUBLISHED / "latest_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if args.save_key:
        Path(args.save_key).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_key).write_text(json.dumps(key_from_results(results, kinds), indent=2), encoding="utf-8")
        print(f"Saved regression key to {args.save_key}")

    def pct(v):
        return "n/a (no key)" if v is None else f"{v:.0%}"

    print("\n=== Evaluation ===")
    print(f"Task success        {pct(metrics['task_success'])}  (target ≥ 80%)")
    print(f"Invoice accuracy    {pct(metrics['invoice_accuracy'])}  (target ≥ 90%)")
    print(f"Wrong disputes      {metrics['wrong_disputes']}  (target 0)")
    print(f"Duplicate disputes  {metrics['duplicate_disputes']}  (target 0)")
    print(f"Needed a human      {metrics['needs_human_tasks']} task(s); failed {metrics['failed_tasks']}")
    print(f"Avg per task        {metrics['avg_duration_s']} s, {metrics['avg_steps']} steps, ₹{metrics['avg_cost_inr']}")
    print(f"\nReport: {(out_dir / 'report.json').relative_to(ROOT)}  (copy in eval_results/latest_report.json)")


if __name__ == "__main__":
    main()
