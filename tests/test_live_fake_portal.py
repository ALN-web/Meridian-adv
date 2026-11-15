"""End-to-end: LiveRunner in real Chromium against the fake portal (chaos off), vs the rules engine.

Skipped when Chromium isn't installed. A helper plays the operator (reads the fake OTP inbox,
approves disputes) — the agent itself never opens the inbox.
"""
import os
import re
import socket
import threading
import time

import pytest

os.environ["FAKE_CHAOS"] = "0"
pytest.importorskip("playwright.async_api")
httpx = pytest.importorskip("httpx")
uvicorn = pytest.importorskip("uvicorn")

from pydantic import SecretStr  # noqa: E402

from meridian.agent.live import LiveRunner  # noqa: E402
from meridian.agent.planner import plan_task  # noqa: E402
from meridian.config import Settings  # noqa: E402
from meridian.fakeportal import server as fake  # noqa: E402
from meridian.reconcile import reconcile_invoice  # noqa: E402
from meridian.store import Store  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def portal():
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(base + "/Login.aspx", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield base
    srv.should_exit = True


def _chromium_ok() -> bool:
    import asyncio

    from playwright.async_api import async_playwright

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch()
            await b.close()

    try:
        asyncio.run(go())
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_ok(), reason="Chromium not installed")


def run_task(base, store, text):
    settings = Settings(portal_base_url=base, portal_user=fake.USER, portal_password=SecretStr(fake.PASSWORD))
    stop = threading.Event()

    def operator():
        while not stop.is_set():
            for r in store.pending_human():
                codes = re.findall(r"<td>(\d{6})</td>", httpx.get(f"{base}/operator", params={"pw": fake.OPERATOR_PASSWORD}).text)
                if codes:
                    store.answer_human(r["id"], codes[0])
            for d in store.disputes(status="pending"):
                store.decide_dispute(d["id"], True)
            time.sleep(0.2)

    threading.Thread(target=operator, daemon=True).start()
    plan = plan_task(text)
    run_id = store.create_run("E2E", text, plan.kind, plan.params, plan.steps, "fake")
    LiveRunner(store, run_id, plan, "E2E", settings=settings).start().join(timeout=300)
    stop.set()
    return store.get_run(run_id)


def test_one_invoice_matches_engine(portal, tmp_path):
    w = fake.S.world
    inv = next(i for i in w.invoices if not i.is_cancelled and len(i.lines) <= 3)
    run = run_task(portal, Store(tmp_path / "s.sqlite"), f"Reconcile invoice {inv.invoice_no}.")
    assert run.status in ("completed", "needs_human"), run.error
    got = run.result["invoices"][0]
    want = reconcile_invoice(inv, w.shipments, w.reference())
    assert got["result"] == want.result
    assert set(got["reasons"]) == set(want.reasons)
    assert abs(got["billed_inr"] - float(want.billed_inr)) <= 1
    assert abs(got["expected_inr"] - float(want.expected_inr)) <= 1
    assert "otp" in run.result["human_steps"]


def test_collect_reads_page_and_pdf_dates(portal, tmp_path):
    w = fake.S.world
    attached = sorted(s for s in fake.S.pod_attached_only if w.pods[s].confident)[:1]
    plain = sorted(s for s in w.pods if s not in fake.S.pod_attached_only and w.pods[s].confident)[:1]
    sids = attached + plain
    run = run_task(portal, Store(tmp_path / "s.sqlite"),
                   f"Download the delivery proofs for {', '.join(sids)}, and report the promised and delivered date of each.")
    assert run.status == "completed", run.error
    got = {p["shipment_id"]: (p["promised_on"], p["delivered_on"]) for p in run.result["pods"]}
    for s in sids:
        assert got[s] == (w.pods[s].promised_on.isoformat(), w.pods[s].delivered_on.isoformat())


def test_dispute_flow_matches_engine_and_never_duplicates(portal, tmp_path):
    """Full write path on the real form layout: approve -> submit once -> confirm in list; rerun adds nothing."""
    from collections import defaultdict
    from datetime import date

    from meridian.reconcile import propose_dispute

    w = fake.S.world
    groups = defaultdict(list)
    for i in w.invoices:
        groups[(i.lane, i.invoice_date.strftime("%Y-%m"))].append(i)
    candidates = []
    for (lane, month), invs in groups.items():
        props = {}
        for i in invs:
            if i.invoice_no in w.disputed:
                continue
            d = propose_dispute(reconcile_invoice(i, w.shipments, w.reference()))
            if d:
                props[i.invoice_no] = d
        if props:
            candidates.append((len(invs), lane, month, props))
    assert candidates, "fake world has no disputable lane-month"
    _, lane, month, props = min(candidates)
    month_name = date(int(month[:4]), int(month[5:]), 1).strftime("%B %Y")
    text = f"Reconcile all invoices on lane {lane} dated in {month_name}, and raise disputes for overcharges after approval."

    before = len(fake.S.disputes)
    store = Store(tmp_path / "s.sqlite")
    run = run_task(portal, store, text)
    assert run.status in ("completed", "needs_human"), run.error
    new = fake.S.disputes[before:]
    assert sorted(x.invoice_no for x in new) == sorted(props)          # exactly the right invoices, once each
    for x in new:
        d = props[x.invoice_no]
        assert set(x.reasons) == set(d.reasons)
        assert abs(x.amount - d.expected_inr) <= 1

    again = run_task(portal, store, text)                               # same task again: nothing new
    assert again.status in ("completed", "needs_human"), again.error
    assert len(fake.S.disputes) == before + len(props)
