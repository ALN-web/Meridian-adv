"""Score saved run results again, without touching the portal.

Two uses:
  * merge a full batch with a re-run of a few tasks (later runs replace earlier ones per task);
  * score live results against an answer key once it is published.

Examples
    python harness/rescore.py --runs live-full-3,live-rerun-3 --label live-final
    python harness/rescore.py --runs live-full-3,live-rerun-3 --label live-final --key harness/answer_keys/public.json

Duplicate disputes are counted from the store, over runs of the same mode only (demo disputes
on the practice portal never count against the real one).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meridian.evaluation import TARGETS, score_task, summarise, to_dict  # noqa: E402

EVAL = ROOT / "runs" / "eval"
TASKS_FILE = ROOT / "harness" / "tasks_public.json"


def duplicate_disputes(db: Path, mode: str) -> int:
    if not db.exists():
        return 0
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT d.invoice_no FROM disputes d JOIN runs r ON r.id = d.run_id "
                         "WHERE d.status IN ('submitted','confirmed') AND r.mode = ?", (mode,)).fetchall()
    return sum(n - 1 for n in Counter(r[0] for r in rows).values() if n > 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help="comma-separated run labels under runs/eval, oldest first")
    ap.add_argument("--label", required=True, help="label for the merged report")
    ap.add_argument("--key", help="answer key JSON to score against")
    args = ap.parse_args()

    labels = args.runs.split(",")
    reports = [json.loads((EVAL / lb / "report.json").read_text(encoding="utf-8")) for lb in labels]
    modes = {r["mode"] for r in reports}
    if len(modes) != 1:
        sys.exit(f"runs mix modes {sorted(modes)}; merge runs of one mode only")
    mode = modes.pop()

    results, source = {}, {}
    for lb in labels:
        for tid, r in json.loads((EVAL / lb / "results.json").read_text(encoding="utf-8")).items():
            results[tid], source[tid] = r, lb
    kinds = {t["task_id"]: t["kind"] for t in json.loads(TASKS_FILE.read_text(encoding="utf-8"))["tasks"]}
    key = json.loads(Path(args.key).read_text(encoding="utf-8")) if args.key else {}

    scores = [score_task(tid, kinds[tid], results[tid], key.get(tid) if key else None) for tid in sorted(results)]
    db = ROOT / "runs" / "meridian.sqlite" if mode == "live" else EVAL / labels[-1] / "store.sqlite"
    metrics = summarise(scores, duplicate_disputes(db, mode))
    if not key:
        metrics["task_success"] = metrics["invoice_accuracy"] = None
        metrics["pass"]["task_success"] = metrics["pass"]["invoice_accuracy"] = None

    report = {
        "label": args.label,
        "mode": mode,
        "answer_key": args.key,
        "auto_otp": any(r.get("auto_otp") for r in reports),
        "auto_approve": any(r.get("auto_approve") for r in reports),
        "started": max(r["started"] for r in reports),
        "wall_time_s": round(sum(r.get("wall_time_s", 0) for r in reports), 1),
        "merged_from": {tid: source[tid] for tid in sorted(source)},
        "targets": TARGETS,
        "metrics": metrics,
        "tasks": [to_dict(s) for s in scores],
        "reruns": {},
    }
    out = EVAL / args.label
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    m = metrics
    print(f"{args.label}: {len(results)} tasks from {', '.join(labels)}")
    print(f"  completed {sum(r.get('status') == 'completed' for r in results.values())}/{len(results)} · "
          f"wrong disputes {m['wrong_disputes']} · duplicates {m['duplicate_disputes']} · "
          f"needed a person {m['needs_human_tasks']} · {m['avg_duration_s']} s per task")
    print(f"Report: {(out / 'report.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
