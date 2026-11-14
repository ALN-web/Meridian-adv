"""Scoring task results against an answer key — the metrics the brief grades on.

Answer key format (``harness/answer_keys/<name>.json``):

    {"T-01": {"kind": "list", "invoices": [{"invoice_no": ..., "total_inr": ..., "status": ...}]},
     "T-04": {"kind": "one", "invoices": [{"invoice_no": ..., "result": ..., "reasons": [...],
                                           "billed_inr": ..., "expected_inr": ...}],
              "disputes": []},
     "T-14": {"kind": "missing", "missing_in_portal": ["SHP-..."]},
     "T-17": {"kind": "collect", "pods": [{"shipment_id": ..., "promised_on": ..., "delivered_on": ...}]},
     "T-19": {"kind": "dispute", "invoices": [...], "disputes": ["TIR/26-27/10190", ...]}}

Comparison rules: order never matters; reasons compare as sets; amounts within ₹1.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

TOLERANCE = 1.0
TARGETS = {
    "task_success": 0.80,
    "invoice_accuracy": 0.90,
    "wrong_disputes": 0,
    "duplicate_disputes": 0,
}
INVOICE_KINDS = ("one", "lane_month", "dispute")


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOLERANCE


@dataclass
class TaskScore:
    task_id: str
    kind: str
    status: str
    success: bool
    items_correct: int
    items_total: int
    problems: list[str] = field(default_factory=list)
    wrong_disputes: int = 0
    steps: int = 0
    retries: int = 0
    duration_s: float = 0.0
    cost_inr: float = 0.0
    human_steps: list[str] = field(default_factory=list)
    trace_id: str | None = None


def _invoice_map(items: list[dict]) -> dict[str, dict]:
    return {i["invoice_no"]: i for i in items or []}


def _invoice_ok(got: dict | None, exp: dict, kind: str) -> tuple[bool, str | None]:
    no = exp["invoice_no"]
    if got is None:
        return False, f"{no}: missing from result"
    if kind == "list":
        if not _close(got.get("total_inr"), exp.get("total_inr")):
            return False, f"{no}: total {got.get('total_inr')} != {exp.get('total_inr')}"
        if (got.get("status") or "").lower() != (exp.get("status") or "").lower():
            return False, f"{no}: status {got.get('status')} != {exp.get('status')}"
        return True, None
    if got.get("result") != exp.get("result"):
        return False, f"{no}: result {got.get('result')} != {exp.get('result')}"
    if exp.get("result") == "cancelled":
        return True, None
    if set(got.get("reasons") or []) != set(exp.get("reasons") or []):
        return False, f"{no}: reasons {sorted(got.get('reasons') or [])} != {sorted(exp.get('reasons') or [])}"
    for k in ("billed_inr", "expected_inr"):
        if k in exp and not _close(got.get(k), exp.get(k)):
            return False, f"{no}: {k} {got.get(k)} != {exp.get(k)}"
    return True, None


def score_task(task_id: str, kind: str, result: dict | None, expected: dict | None) -> TaskScore:
    result = result or {}
    s = TaskScore(
        task_id=task_id, kind=kind, status=result.get("status", "failed"), success=False,
        items_correct=0, items_total=0, steps=result.get("steps", 0) or 0, retries=result.get("retries", 0) or 0,
        duration_s=result.get("duration_s", 0) or 0, cost_inr=result.get("cost_inr", 0) or 0,
        human_steps=list(result.get("human_steps") or []), trace_id=result.get("trace_id"),
    )
    if s.status == "failed":
        s.problems.append(f"task failed: {result.get('error') or 'see step log'}")
    elif s.status == "needs_human":
        s.problems.append("needs a human (unreadable proof or similar)")
    if expected is None:
        s.problems.append("no answer key for this task")
        return s

    if kind in ("list",) + INVOICE_KINDS:
        got, exp = _invoice_map(result.get("invoices")), _invoice_map(expected.get("invoices"))
        for no, e in exp.items():
            ok, why = _invoice_ok(got.get(no), e, kind)
            s.items_total += 1
            s.items_correct += ok
            if why:
                s.problems.append(why)
        for extra in sorted(set(got) - set(exp)):
            s.items_total += 1
            s.problems.append(f"{extra}: not expected")
    elif kind == "missing":
        got, exp = set(result.get("missing_in_portal") or []), set(expected.get("missing_in_portal") or [])
        s.items_total = len(exp | got)
        s.items_correct = len(exp & got)
        if exp - got:
            s.problems.append(f"not reported missing: {sorted(exp - got)}")
        if got - exp:
            s.problems.append(f"wrongly reported missing: {sorted(got - exp)}")
    elif kind == "collect":
        norm = lambda pods: {p["shipment_id"]: (p.get("promised_on"), p.get("delivered_on")) for p in pods or []}  # noqa: E731
        got, exp = norm(result.get("pods")), norm(expected.get("pods"))
        for sid, dates in exp.items():
            s.items_total += 1
            if got.get(sid) == dates:
                s.items_correct += 1
            else:
                s.problems.append(f"{sid}: {got.get(sid)} != {dates}")
        for extra in sorted(set(got) - set(exp)):
            s.items_total += 1
            s.problems.append(f"{extra}: not expected")

    if kind == "dispute":
        expected_disputes = set(expected.get("disputes") or [])
        raised = [d.get("invoice_no") for d in result.get("disputes") or []]
        wrong = [no for no in raised if no not in expected_disputes]
        s.wrong_disputes = len(wrong)
        if wrong:
            s.problems.append(f"wrong disputes raised: {wrong}")
        missed = expected_disputes - set(raised)
        if missed:
            s.problems.append(f"disputes not raised: {sorted(missed)}")

    s.success = s.status == "completed" and not s.problems
    s.items_correct = s.items_correct if s.status != "failed" else 0
    return s


def summarise(scores: list[TaskScore], duplicate_disputes: int) -> dict:
    n = len(scores) or 1
    items_total = sum(s.items_total for s in scores) or 1
    finished = [s for s in scores if s.status != "failed"]
    m = {
        "tasks": len(scores),
        "task_success": sum(s.success for s in scores) / n,
        "invoice_accuracy": sum(s.items_correct for s in scores) / items_total,
        "wrong_disputes": sum(s.wrong_disputes for s in scores),
        "duplicate_disputes": duplicate_disputes,
        "needs_human_tasks": sum(s.status == "needs_human" for s in scores),
        "human_steps_beyond_otp": sum(1 for s in scores for h in s.human_steps if h not in ("otp", "approval")),
        "failed_tasks": sum(s.status == "failed" for s in scores),
        "avg_duration_s": round(sum(s.duration_s for s in finished) / max(len(finished), 1), 1),
        "avg_steps": round(sum(s.steps for s in finished) / max(len(finished), 1), 1),
        "avg_cost_inr": round(sum(s.cost_inr for s in finished) / max(len(finished), 1), 2),
        "total_retries": sum(s.retries for s in scores),
    }
    m["pass"] = {
        "task_success": m["task_success"] >= TARGETS["task_success"],
        "invoice_accuracy": m["invoice_accuracy"] >= TARGETS["invoice_accuracy"],
        "wrong_disputes": m["wrong_disputes"] == 0,
        "duplicate_disputes": m["duplicate_disputes"] == 0,
    }
    return m


def to_dict(s: TaskScore) -> dict:
    return asdict(s)


def key_from_results(results: dict[str, dict], kinds: dict[str, str]) -> dict:
    """Snapshot results as a *regression* key (not ground truth) — useful to catch changes."""
    key = {}
    for tid, r in results.items():
        if r.get("status") == "failed":
            continue  # nothing trustworthy to snapshot
        k = kinds[tid]
        e: dict = {"kind": k}
        if k in ("list",) + INVOICE_KINDS:
            e["invoices"] = [{kk: v for kk, v in i.items() if kk != "evidence"} for i in r.get("invoices") or []]
        if k == "dispute":
            e["disputes"] = [d["invoice_no"] for d in r.get("disputes") or []]
        if k == "missing":
            e["missing_in_portal"] = r.get("missing_in_portal") or []
        if k == "collect":
            e["pods"] = r.get("pods") or []
        key[tid] = e
    return key
