"""Stretch goal: whole-month run in parallel browser contexts, shared login, monthly schedule, summary."""
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from meridian.agent.month import _inr, write_summary  # noqa: E402
from meridian.config import Settings  # noqa: E402
from meridian.portal.client import PortalClient  # noqa: E402
from meridian.portal.throttle import RateLimiter  # noqa: E402


# ---------------------------------------------------------------- schedule


def test_previous_month_wraps_the_year():
    from run_month import previous_month

    assert previous_month(date(2026, 11, 18)) == "2026-10"
    assert previous_month(date(2027, 1, 2)) == "2026-12"


def test_next_fire_is_the_coming_slot_in_ist():
    from schedule_month import IST, next_fire

    assert next_fire(datetime(2026, 11, 18, 12, 0, tzinfo=IST), 2, "07:10") == datetime(2026, 12, 2, 7, 10, tzinfo=IST)
    assert next_fire(datetime(2026, 12, 2, 7, 9, tzinfo=IST), 2, "07:10") == datetime(2026, 12, 2, 7, 10, tzinfo=IST)
    assert next_fire(datetime(2026, 12, 2, 7, 10, tzinfo=IST), 2, "07:10") == datetime(2027, 1, 2, 7, 10, tzinfo=IST)


# ---------------------------------------------------------------- shared rate limit


def test_limiter_counts_requests_and_keeps_the_rate_across_contexts():
    t = [0.0]
    slept = []

    async def fake_sleep(d):
        slept.append(d)
        t[0] += d

    lim = RateLimiter(2.0, clock=lambda: t[0], sleep=fake_sleep)

    async def ctx(n):
        for _ in range(n):
            await lim.wait()

    async def main():
        await asyncio.gather(*(ctx(5) for _ in range(4)))  # four contexts, one limiter

    asyncio.run(main())
    assert lim.count == 20
    assert lim._next_slot == pytest.approx(10.0)  # 20 requests at 2/s: the last slot starts at 9.5 s


# ---------------------------------------------------------------- one OTP for all contexts


class StubCtx:
    def __init__(self):
        self.cookies = []

    async def clear_cookies(self):
        self.cookies = []

    async def add_cookies(self, cookies):
        self.cookies = list(cookies)


def _client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = PortalClient(Settings(portal_base_url="https://portal.example"), human=None)
    c._ctx = StubCtx()
    c.login_lock = asyncio.Lock()
    return c


def test_context_adopts_a_newer_session_instead_of_asking_for_an_otp(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    f = c.session_file()
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"cookies": [{"name": "ASP.NET_SessionId", "value": "new", "domain": "portal.example", "path": "/"}]}))
    c._session_seen = f.stat().st_mtime - 10  # this context loaded an older session

    real_logins = []

    async def fake_login():
        real_logins.append(1)

    c._login = fake_login
    asyncio.run(c.login())
    assert real_logins == []                      # no second login, so no second OTP
    assert c._ctx.cookies[0]["value"] == "new"
    asyncio.run(c.login())                        # same session file again -> it must log in for real
    assert real_logins == [1]


def test_without_a_shared_lock_login_is_unchanged(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.login_lock = None
    calls = []

    async def fake_login():
        calls.append(1)

    c._login = fake_login
    asyncio.run(c.login())
    assert calls == [1]


# ---------------------------------------------------------------- summary for the manager


def test_indian_grouping():
    assert _inr(171710.58) == "₹1,71,710.58"
    assert _inr(-500) == "-₹500.00"


def _report():
    lane = {"invoices": [
        {"invoice_no": "TIR/26-27/1", "result": "match", "reasons": [], "billed_inr": 1000.0, "expected_inr": 1000.0},
        {"invoice_no": "TIR/26-27/2", "result": "mismatch", "reasons": ["weight_over"], "billed_inr": 2600.0,
         "expected_inr": 2000.0},
        {"invoice_no": "TIR/26-27/3", "result": "cancelled"}],
        "missing_in_portal": ["SHP-1"],
        "disputes_to_raise": [{"invoice_no": "TIR/26-27/2", "reasons": ["weight_over"], "billed_inr": 2600.0,
                               "expected_inr": 2000.0, "overcharge_inr": 600.0}]}
    return {"month": "2026-10", "lanes": {"PUN-BLR": lane}, "invoices": lane["invoices"], "missing_in_portal": ["SHP-1"],
            "disputes": [], "disputes_to_raise": lane["disputes_to_raise"], "errors": {}, "workers": 4,
            "requests": 100, "requests_per_s": 1.9, "phase_s": {"invoices": 10.0, "pods": 20.0},
            "human_steps": ["otp"], "steps": 50, "retries": 2, "duration_s": 40.0, "cost_inr": 0.0,
            "_details": {"x": 1}}


def test_summary_files_for_the_logistics_manager(tmp_path):
    files = write_summary(_report(), tmp_path, sequential_s=100.0)
    md = files["summary"].read_text(encoding="utf-8")
    assert "October 2026" in md and "no disputes raised" in md
    assert "| PUN-BLR | 2 | 1 | 1 | ₹600.00 | 1 |" in md
    assert "TIR/26-27/2 | weight_over" in md and "SHP-1" in md
    assert "2.5× faster" in md
    csv = files["csv"].read_text(encoding="utf-8").splitlines()
    assert csv[0].startswith("lane,invoice_no,result") and len(csv) == 4
    data = json.loads(files["json"].read_text(encoding="utf-8"))
    assert "_details" not in data and data["sequential_s"] == 100.0


# ---------------------------------------------------------------- end to end on the fake portal


@pytest.mark.skipif(os.environ.get("MERIDIAN_SKIP_BROWSER") == "1", reason="browser tests switched off")
def test_month_run_in_parallel_matches_the_engine_and_writes_nothing(tmp_path, monkeypatch):
    os.environ["FAKE_CHAOS"] = "0"
    pytest.importorskip("playwright.async_api")
    import test_live_fake_portal as e2e  # reuse its fake-portal server fixture helpers

    if not e2e._chromium_ok():
        pytest.skip("Chromium not installed")
    import re
    import threading
    import time

    import httpx
    import uvicorn
    from pydantic import SecretStr

    from meridian.agent.live import run_async
    from meridian.agent.month import MonthRunner
    from meridian.fakeportal import server as fake
    from meridian.reconcile import reconcile_invoice
    from meridian.store import Store

    port = e2e._free_port()
    srv = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(base + "/Login.aspx", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    monkeypatch.chdir(tmp_path)
    store = Store(tmp_path / "s.sqlite")
    run_id = store.create_run("MONTH", "month", "month", {}, ["a"] * 8, "fake")
    stop = threading.Event()

    def operator():
        while not stop.is_set():
            for r in store.pending_human():
                codes = re.findall(r"<td>(\d{6})</td>", httpx.get(f"{base}/operator", params={"pw": fake.OPERATOR_PASSWORD}).text)
                if codes:
                    store.answer_human(r["id"], codes[0])
            time.sleep(0.2)

    threading.Thread(target=operator, daemon=True).start()
    try:
        w = fake.S.world
        lane = "PUN-HYD"
        disputes_before = len(fake.S.disputes)
        settings = Settings(portal_base_url=base, portal_user=fake.USER, portal_password=SecretStr(fake.PASSWORD))
        rep = run_async(MonthRunner(settings, "2026-10", lanes=[lane], workers=3, store=store, run_id=run_id).run())
    finally:
        stop.set()
        srv.should_exit = True

    assert rep["status"] == "completed" and rep["workers"] == 3
    assert len(fake.S.disputes) == disputes_before          # read-only: nothing written to the portal
    assert rep["requests_per_s"] <= 2.05
    want = {i.invoice_no: reconcile_invoice(i, w.shipments, w.reference()).to_output() for i in w.search(lane, "2026-10")}
    got = {i["invoice_no"]: i for i in rep["lanes"][lane]["invoices"]}
    assert set(got) == set(want)
    for no, o in want.items():
        assert (got[no]["result"], got[no].get("reasons"), got[no].get("expected_inr")) == \
               (o["result"], o.get("reasons"), o.get("expected_inr"))
