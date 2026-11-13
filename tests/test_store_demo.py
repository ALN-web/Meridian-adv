import threading
import time

import pytest

from meridian.agent import demo
from meridian.agent.planner import plan_task
from meridian.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.sqlite")


def test_one_live_dispute_per_invoice(store):
    a = store.propose_dispute("r1", "TIR/26-27/1", ["weight_over"], "1000", "400", [])
    assert a
    assert store.propose_dispute("r2", "TIR/26-27/1", ["weight_over"], "1000", "400", []) is None
    store.decide_dispute(a, approve=False)
    # a rejected proposal is not live, so a later run may propose again
    assert store.propose_dispute("r3", "TIR/26-27/1", ["weight_over"], "1000", "400", [])


def test_decision_only_once(store):
    d = store.propose_dispute("r1", "TIR/26-27/2", ["rate_wrong"], "900", "100", [])
    assert store.decide_dispute(d, True)
    assert not store.decide_dispute(d, False)
    assert store.disputes(run_id="r1")[0]["status"] == "approved"


def test_otp_answer_read_once_and_wiped(store):
    rid = store.request_human("r1", "otp")
    assert store.take_answer(rid) is None
    store.answer_human(rid, "123456")
    assert store.take_answer(rid) == "123456"
    assert store.take_answer(rid) is None
    assert store.pending_human() == []


def _auto_human(store, stop, approve=True):
    while not stop.is_set():
        for r in store.pending_human():
            store.answer_human(r["id"], "000000")
        for d in store.disputes(status="pending"):
            store.decide_dispute(d["id"], approve)
        time.sleep(0.05)


def _run(store, text, approve=True):
    demo.STEP_DELAY = 0
    plan = plan_task(text)
    run_id = store.create_run("T-X", text, plan.kind, plan.params, plan.steps, "demo")
    stop = threading.Event()
    helper = threading.Thread(target=_auto_human, args=(store, stop, approve), daemon=True)
    helper.start()
    t = demo.DemoRunner(store, run_id, plan, "T-X").start()
    t.join(timeout=30)
    stop.set()
    return store.get_run(run_id)


def test_demo_lane_month_completes_with_resume(store):
    run = _run(store, "Reconcile all invoices on lane PUN-HYD dated in October 2026. Do not raise disputes.")
    assert run.status in ("completed", "needs_human")
    assert run.result["invoices"]
    assert "otp" in run.result["human_steps"]
    assert any(s["outcome"] == "session_expired" for s in store.steps(run.id))


def test_demo_dispute_twice_raises_no_duplicates(store):
    text = "Reconcile all invoices on lane PUN-BLR dated in September 2026, and raise disputes for overcharges after approval."
    first = _run(store, text)
    raised = {d["invoice_no"] for d in first.result["disputes"]}
    second = _run(store, text)
    assert second.result["disputes"] == []
    confirmed = [d for d in store.disputes() if d["status"] == "confirmed"]
    assert len(confirmed) == len({d["invoice_no"] for d in confirmed}) == len(raised)
