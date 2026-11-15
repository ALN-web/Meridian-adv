"""Live runner: carries out a task on a portal in a real browser (Playwright).

Works against the fake portal today and the real TransIndus portal once its selectors are
confirmed by recon. Same store, same approvals, same result format as the demo runner.

Flow per task kind
  list        search invoices (all pages) -> number, total as printed, status
  collect     each shipment's POD -> promised/delivered dates (from page or PDF; scans -> needs_human)
  missing     Meridian shipments delivered on lane in month -> search invoices by shipment -> none = missing
  one / lane_month / dispute
              rate card + fuel + dispute list once; per invoice (checkpointed): details, PODs and
              billing history of each shipment -> rules engine in code -> result
  dispute     proposals -> human approval -> re-check list -> submit once -> confirm in list
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from meridian.agent.planner import Plan
from meridian.config import Settings, get_settings
from meridian.portal.client import PortalClient
from meridian.portal.errors import HumanNeeded, LoginFailed, PortalError
from meridian.portal.human import StoreHumanGate
from meridian.portal.throttle import RateLimiter
from meridian.records import Shipment, load_shipments
from meridian.reconcile import (
    BillingRecord,
    MissingReferenceData,
    ReferenceData,
    propose_dispute,
    reconcile_invoice,
)
from meridian.reconcile.explain import explain_invoice
from meridian.telemetry import TaskTracer
from meridian.store import Store


class Cancelled(Exception):
    """The operator pressed Stop."""

APPROVAL_TIMEOUT_S = 3600


def load_meridian_records(settings: Settings) -> dict[str, Shipment]:
    """Meridian's CSV: local copy in data/ if present, else fetched with the team key (never logged)."""
    local = Path("data/meridian-shipments.csv")
    if local.exists():
        return load_shipments(local)
    import httpx

    key = settings.team_key.get_secret_value()
    if not key:
        raise RuntimeError("No data/meridian-shipments.csv and no TEAM_KEY to fetch it")
    r = httpx.get(f"{settings.portal_base_url.rstrip('/')}/internal/meridian-shipments.csv", params={"key": key}, timeout=120)
    r.raise_for_status()
    local.parent.mkdir(exist_ok=True)
    local.write_text(r.text, encoding="utf-8")
    return load_shipments(local)


class LiveRunner:
    def __init__(self, store: Store, run_id: str, plan: Plan, task_id: str, *,
                 settings: Settings | None = None, headless: bool = True, limiter: RateLimiter | None = None):
        self.store, self.run_id, self.plan, self.task_id = store, run_id, plan, task_id
        self.settings = settings or get_settings()
        self.headless = headless
        self.limiter = limiter
        self.t0 = time.time()
        self.human_steps: list[str] = []

    # ------------------------------------------------------------------ plumbing

    def start(self) -> threading.Thread:
        t = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True, name=f"live-{self.run_id}")
        t.start()
        return t

    def phase(self, i: int) -> None:
        self.store.set_phase(self.run_id, max(0, min(i, len(self.plan.steps) - 1)))

    def doc(self, kind: str, label: str, path) -> None:
        if path:
            self.store.add_document(self.run_id, kind, label, str(path))

    def check_cancel(self) -> None:
        if self.store.cancel_requested(self.run_id):
            raise Cancelled()

    def _sink(self, step: str, outcome: str, extra: dict) -> None:
        detail = ", ".join(f"{k}={v}" for k, v in extra.items() if k not in ("path", "page"))[:300]
        self.store.add_step(self.run_id, step, outcome, detail, page=extra.get("page"))

    def _waiting(self, kind: str) -> None:
        self.human_steps.append(kind)
        self.store.set_status(self.run_id, "waiting_for_human")
        self.store.add_step(self.run_id, kind, "waiting_for_human", "Asked the operator — see the OTP box")

    def _resumed(self, kind: str) -> None:
        self.store.set_status(self.run_id, "running")

    async def _main(self) -> None:
        from playwright.async_api import async_playwright

        self.store.set_status(self.run_id, "running")
        tracer = TaskTracer(self.run_id, self.task_id, self.store.get_run(self.run_id).task_text, self.plan.kind,
                            "live", settings=self.settings)
        self.store.subscribe(self.run_id, tracer)
        client = None
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.headless)
                gate = StoreHumanGate(self.store, self.run_id, on_wait=self._waiting, on_resume=self._resumed)
                client = PortalClient(self.settings, gate, self.limiter,
                                      download_dir=f"runs/downloads/{self.run_id}", screenshot_dir=f"runs/screenshots/{self.run_id}")
                client.log.sink = self._sink
                await client.start(browser)
                try:
                    self.phase(0)
                    await client.login()
                    self.phase(1)
                    result = await self._run(client)
                finally:
                    await client.close()
                    await browser.close()
            status = result.pop("_status", "completed")
            self.phase(len(self.plan.steps) - 1)
        except Cancelled:
            self.store.add_step(self.run_id, "runner", "cancelled", "Stopped by the operator — progress kept, can resume")
            result, status = {"error": "stopped by operator"}, "cancelled"
        except (HumanNeeded, LoginFailed) as exc:
            self.store.add_step(self.run_id, "runner", "needs_human", str(exc))
            result, status = {"error": str(exc)}, "needs_human"
        except Exception as exc:
            self.store.add_step(self.run_id, "runner", "failed", f"{type(exc).__name__}: {exc}"[:300])
            result, status = {"error": f"{type(exc).__name__}: {exc}"[:300]}, "failed"
        log = client.log if client else None
        result.update(
            task_id=self.task_id, status="failed" if status == "cancelled" else status,
            steps=log.steps if log else 0, retries=log.retries.retries if log else 0,
            duration_s=round(time.time() - self.t0, 1), cost_inr=0.0, trace_id=tracer.trace_id,
            human_steps=self.human_steps,
        )
        if tracer.url:
            result["trace_url"] = tracer.url
        self.store.unsubscribe(self.run_id)
        tracer.finish(status, result)
        self.store.set_status(self.run_id, status, result=result, error=result.get("error"))

    # ------------------------------------------------------------------ task kinds

    async def _run(self, c: PortalClient) -> dict:
        k, p = self.plan.kind, self.plan.params
        if k == "list":
            rows = await c.search_invoices(p["lane"], p["month"])
            return {"invoices": [{"invoice_no": r.invoice_no, "total_inr": float(r.total), "status": r.status} for r in rows]}
        if k == "collect":
            return await self._collect(c, p["shipment_ids"])
        if k == "missing":
            return await self._missing(c, p["lane"], p["month"])
        return await self._reconcile(c)

    async def _collect(self, c: PortalClient, sids: list[str]) -> dict:
        pods, unreadable = [], []
        for sid in sids:
            self.check_cancel()
            pod, pdf = await c.get_pod(sid)
            self.doc("pod_pdf", f"POD_{sid}", pdf)
            if pod is None:
                continue
            if not pod.confident:
                unreadable.append(sid)
                continue
            pods.append({"shipment_id": sid, "promised_on": pod.promised_on.isoformat(), "delivered_on": pod.delivered_on.isoformat()})
        out = {"pods": pods}
        if unreadable:
            out["needs_human"] = [f"pod_unreadable:{s}" for s in unreadable]
            out["_status"] = "needs_human"
        return out

    async def _missing(self, c: PortalClient, lane: str, month: str) -> dict:
        shipments = load_meridian_records(self.settings)
        delivered = sorted(s.shipment_id for s in shipments.values()
                           if s.lane == lane and s.delivered_on.strftime("%Y-%m") == month)
        done = self.store.checkpoints(self.run_id)
        missing = []
        for sid in delivered:
            self.check_cancel()
            key = f"missing:{sid}"
            if key in done:
                billed = done[key]["data"]["billed"]
            else:
                billed = bool(await c.invoices_billing(sid))
                self.store.checkpoint(self.run_id, key, "done", {"billed": billed})
            if not billed:
                missing.append(sid)
        return {"missing_in_portal": missing}

    async def _reconcile(self, c: PortalClient) -> dict:
        k, p = self.plan.kind, self.plan.params
        shipments = load_meridian_records(self.settings)
        if k == "one":
            rows = await c.search_invoices(invoice_no=p["invoice_no"])
            if not rows:
                return {"invoices": [], "_status": "failed", "error": f"invoice {p['invoice_no']} not found on portal"}
        else:
            rows = await c.search_invoices(p["lane"], p["month"])
        self.phase(2)
        rate_card = await c.rate_card()
        fuel = await c.fuel_surcharge()
        disputed = c.disputed_invoices(await c.dispute_list())

        pod_cache: dict = {}
        history_cache: dict[str, list[BillingRecord]] = {}
        done = self.store.checkpoints(self.run_id)
        results, needs = [], False
        for row in rows:
            self.check_cancel()
            if done.get(row.invoice_no, {}).get("state") == "done":
                results.append(done[row.invoice_no]["data"])
                self.store.add_step(self.run_id, f"invoice:{row.invoice_no}", "skipped", "already done (resumed from checkpoint)")
                continue
            if row.status.lower() == "cancelled":
                out = {"invoice_no": row.invoice_no, "result": "cancelled"}
                self.store.checkpoint(self.run_id, row.invoice_no, "done", out)
                results.append(out)
                continue
            inv, inv_pdf = await c.open_invoice(row.invoice_no)
            self.doc("invoice_pdf", f"INV_{row.invoice_no}", inv_pdf)
            if inv is None:
                results.append({"invoice_no": row.invoice_no, "result": "mismatch", "reasons": [], "error": "not found"})
                continue
            if not inv.lane:
                inv = replace(inv, lane=row.lane or "")
            history: list[BillingRecord] = [BillingRecord.from_invoice(inv)]
            for line in inv.lines:
                self.check_cancel()
                sid = line.shipment_id
                if sid not in pod_cache:
                    pod_cache[sid], pod_pdf = await c.get_pod(sid)
                    self.doc("pod_pdf", f"POD_{sid}", pod_pdf)
                if sid not in history_cache:
                    found = await c.invoices_billing(sid)
                    history_cache[sid] = [BillingRecord(r.invoice_no, r.invoice_date, r.status, (sid,))
                                          for r in found if r.invoice_date is not None]
                history += [h for h in history_cache[sid] if h.invoice_no != inv.invoice_no]
            ref = ReferenceData(rate_card, fuel, {s: v for s, v in pod_cache.items() if v is not None},
                                history, set(disputed))
            try:
                r = reconcile_invoice(inv, shipments, ref)
            except MissingReferenceData as exc:
                needs = True
                out = {"invoice_no": inv.invoice_no, "result": "mismatch", "reasons": [], "needs_human": [str(exc)]}
                self.store.add_step(self.run_id, f"reconcile:{inv.invoice_no}", "needs_human", str(exc))
                results.append(out)
                continue
            self.store.save_detail(self.run_id, inv.invoice_no, explain_invoice(inv, r, shipments, ref))
            out = r.to_output()
            if r.needs_human:
                needs = True
                out["needs_human"] = r.needs_human
            if r.already_disputed:
                out["existing_dispute"] = True
            self.store.checkpoint(self.run_id, inv.invoice_no, "done", out)
            self.store.add_step(self.run_id, f"reconcile:{inv.invoice_no}", r.result,
                                (", ".join(r.reasons) or r.result) + f" · billed ₹{r.billed_inr} expected ₹{r.expected_inr}")
            results.append(out)
            if k == "dispute":
                d = propose_dispute(r)
                if d:
                    if self.store.propose_dispute(self.run_id, d.invoice_no, list(d.reasons), str(d.billed_inr),
                                                  str(d.expected_inr), out.get("evidence", [])):
                        self.store.add_step(self.run_id, f"dispute:{d.invoice_no}", "awaiting_approval", f"overcharge ₹{d.overcharge}")
                    else:
                        self.store.add_step(self.run_id, f"dispute:{d.invoice_no}", "skipped", "already queued or raised")
                elif r.already_disputed:
                    self.store.add_step(self.run_id, f"dispute:{inv.invoice_no}", "skipped", "dispute already exists on portal")

        self.phase(4)
        out = {"invoices": results, "disputes": []}
        if k == "dispute":
            self.phase(6)
            out["disputes"] = await self._approvals(c)
        if needs:
            out["_status"] = "needs_human"
        return out

    async def _approvals(self, c: PortalClient) -> list[dict]:
        if self.store.disputes(status="pending", run_id=self.run_id):
            self._waiting("approval")
            waited = 0.0
            while self.store.disputes(status="pending", run_id=self.run_id):
                if self.store.cancel_requested(self.run_id):
                    raise Cancelled()
                await asyncio.sleep(0.5)
                waited += 0.5
                if waited > APPROVAL_TIMEOUT_S:
                    raise HumanNeeded("approval", "disputes not approved in time")
            self._resumed("approval")
        self.phase(7)
        raised = []
        for d in self.store.disputes(run_id=self.run_id):
            if d["status"] == "rejected":
                self.store.add_step(self.run_id, f"dispute:{d['invoice_no']}", "rejected", "operator rejected — not raised")
                continue
            if d["status"] != "approved":
                continue
            raised_one = await self._raise_one(c, d)
            if raised_one:
                raised.append(raised_one)
        return raised

    async def _raise_one(self, c: PortalClient, d: dict) -> dict | None:
        """Never write twice: check list -> submit once -> confirm in list. One careful retry if lost."""
        no = d["invoice_no"]
        expected = Decimal(d["expected_inr"])
        for attempt in (1, 2):
            if no in c.disputed_invoices(await c.dispute_list()):
                if attempt == 1:
                    self.store.mark_dispute(d["id"], "skipped", note="already on portal before submit")
                    self.store.add_step(self.run_id, f"dispute:{no}", "skipped", "found in dispute list before submitting")
                    return None
                break
            self.store.mark_dispute(d["id"], "submitted")
            try:
                await c.submit_dispute(no, d["reasons"], expected)
            except PortalError as exc:
                self.store.add_step(self.run_id, f"dispute:{no}", "submit_error", str(exc)[:200])
            if no in c.disputed_invoices(await c.dispute_list()):
                break
            self.store.add_step(self.run_id, f"dispute:{no}", "not_confirmed",
                                "success message but not in dispute list" + (" — retrying once" if attempt == 1 else ""))
        else:
            self.store.mark_dispute(d["id"], "failed", note="not confirmed in dispute list")
            return None
        rows = await c.dispute_list()
        ref = next((v for r in rows if any(x == no for x in r.values())
                    for h, v in r.items() if "dispute" in h.lower() and "no" in h.lower()), None)
        for shot in sorted(Path(c.screenshot_dir).glob(f"dispute_*{no.replace('/', '_')}*.png")):
            self.doc("screenshot", shot.stem, shot)
        self.store.mark_dispute(d["id"], "confirmed", portal_ref=ref)
        self.store.add_step(self.run_id, f"dispute:{no}", "confirmed", f"in dispute list as {ref}")
        return {"invoice_no": no, "reasons": d["reasons"], "expected_inr": float(expected), "portal_ref": ref}
