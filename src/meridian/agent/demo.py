"""Demo runner: drives the operator screen end to end WITHOUT the real portal.

It fakes the portal side (invoices with planted errors, an OTP prompt, one session expiry)
but uses the real planner, the real reconciliation engine and the real store/approval flow.
Swap in the Playwright runner once recon has been done; the UI does not change.
"""
from __future__ import annotations

import random
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from meridian.agent.planner import Plan
from meridian.parsing import to_paise
from meridian.records import Shipment, load_shipments
from meridian.reconcile import (
    BillingRecord,
    Invoice,
    InvoiceLine,
    Pod,
    RateCardEntry,
    ReferenceData,
    missing_in_portal,
    propose_dispute,
    reconcile_invoice,
)
from meridian.reconcile.explain import explain_invoice
from meridian.store import Store


class Cancelled(Exception):
    """The operator pressed Stop."""

LANES = ("PUN-BLR", "PUN-HYD", "PUN-CHN", "PUN-DEL", "PUN-AMD")
BASE_RATE = {"PUN-BLR": Decimal("14.20"), "PUN-HYD": Decimal("13.10"), "PUN-CHN": Decimal("16.40"),
             "PUN-DEL": Decimal("21.75"), "PUN-AMD": Decimal("11.30")}
FUEL = {"2026-08": Decimal("12.5"), "2026-09": Decimal("13"), "2026-10": Decimal("14.5"), "2026-11": Decimal("14.5")}
STEP_DELAY = 0.35


# ---------------------------------------------------------------- synthetic world


def _fallback_shipments() -> dict[str, Shipment]:
    rng = random.Random(7)
    out, n = {}, 60000
    for lane in LANES:
        for month in (8, 9, 10):
            for _ in range(8):
                n += 1
                booked = date(2026, month, rng.randint(1, 27))
                sid = f"SHP-{n}"
                out[sid] = Shipment(sid, booked, lane, Decimal(str(round(rng.uniform(150, 2400), 1))),
                                    booked + timedelta(days=rng.randint(1, 5)), f"MF-{rng.randint(10000, 99999)}")
    return out


def load_world_shipments() -> dict[str, Shipment]:
    for p in (Path("data/meridian-shipments.csv"), Path("data/meridian_shipments.csv")):
        if p.exists():
            return load_shipments(p)
    return _fallback_shipments()


class FakePortal:
    """Deterministic fake carrier data with planted errors, built from Meridian's shipments."""

    def __init__(self, shipments: dict[str, Shipment]):
        self.shipments = shipments
        rng = random.Random(42)
        self.rate_card = [RateCardEntry(l, r, date(2026, 4, 1)) for l, r in BASE_RATE.items()]
        self.rate_card.append(RateCardEntry("PUN-BLR", BASE_RATE["PUN-BLR"] + Decimal("0.60"), date(2026, 10, 15)))
        self.pods: dict[str, Pod] = {}
        self.invoices: list[Invoice] = []
        self.disputed: set[str] = set()
        serial = 10100
        by_lane_month: dict[tuple[str, str], list[Shipment]] = {}
        for s in sorted(shipments.values(), key=lambda s: (s.booked_on, s.shipment_id)):
            by_lane_month.setdefault((s.lane, s.booked_on.strftime("%Y-%m")), []).append(s)
            if rng.random() > 0.03:  # a few shipments have no POD
                promised = s.booked_on + timedelta(days=2)
                self.pods[s.shipment_id] = Pod(s.shipment_id, promised, s.delivered_on, confident=rng.random() > 0.04)

        billed_ids: list[str] = []
        for (lane, month), group in sorted(by_lane_month.items()):
            y, m = map(int, month.split("-"))
            chunks = [group[i:i + 4] for i in range(0, len(group), 4)]
            for ci, chunk in enumerate(chunks):
                if rng.random() < 0.12:
                    chunk = chunk[:-1]  # leave one shipment un-invoiced -> missing_in_portal
                if not chunk:
                    continue
                serial += 1
                inv_date = min(date(y, m, 28), max(s.delivered_on for s in chunk) + timedelta(days=1))
                if inv_date.month != m:
                    inv_date = date(y, m, 28)
                lines = []
                for s in chunk:
                    lines.append(self._line(s, rng))
                if billed_ids and rng.random() < 0.08:  # re-bill an earlier shipment -> duplicate
                    dup = shipments[rng.choice(billed_ids[-10:])]
                    if dup.lane == lane:
                        lines.append(self._line(dup, random.Random(1)))
                billed_ids.extend(s.shipment_id for s in chunk)
                if rng.random() < 0.05:
                    lines.append(InvoiceLine(f"SHP-9{serial}", Decimal("500"), BASE_RATE[lane], fuel_pct=FUEL[month]))
                subtotal = sum((l.billed_total() for l in lines), Decimal("0"))
                total = to_paise(subtotal * Decimal("1.12"))
                if rng.random() < 0.05:
                    total += Decimal("1180.00")  # math_error
                status = "Cancelled" if rng.random() < 0.06 else "Open"
                credits = (Decimal("750.00"),) if rng.random() < 0.06 else ()
                self.invoices.append(Invoice(f"TIR/26-27/{serial}", inv_date, lane, status, total, tuple(lines), credits))
        # one pre-existing dispute so "don't raise twice" is visible in demos
        mism = [i for i in self.invoices if not i.is_cancelled]
        if len(mism) > 5:
            self.disputed.add(mism[5].invoice_no)

    def _line(self, s: Shipment, rng: random.Random) -> InvoiceLine:
        month = s.booked_on.strftime("%Y-%m")
        rate = BASE_RATE[s.lane]
        if s.lane == "PUN-BLR" and s.booked_on >= date(2026, 10, 15):
            rate += Decimal("0.60")
        weight = s.actual_weight_kg
        pct = FUEL[month]
        detention = Decimal("0")
        roll = rng.random()
        if roll < 0.10:
            weight = to_paise(weight * Decimal("1.08"))  # weight_over
        elif roll < 0.16:
            rate += Decimal("1.50")  # rate_wrong
        elif roll < 0.20:
            pct += Decimal("2")  # surcharge_wrong
        if rng.random() < 0.10:
            detention = Decimal("1500.00")  # justified or not depending on POD
        return InvoiceLine(s.shipment_id, weight, rate, fuel_pct=pct, detention=detention)

    def reference(self) -> ReferenceData:
        return ReferenceData(self.rate_card, dict(FUEL), self.pods,
                             [BillingRecord.from_invoice(i) for i in self.invoices], set(self.disputed))

    def search(self, lane: str, month: str) -> list[Invoice]:
        return [i for i in self.invoices if i.lane == lane and i.invoice_date.strftime("%Y-%m") == month]

    def invoice(self, invoice_no: str) -> Invoice | None:
        return next((i for i in self.invoices if i.invoice_no == invoice_no), None)


_WORLD: FakePortal | None = None
_WORLD_LOCK = threading.Lock()


def world() -> FakePortal:
    global _WORLD
    with _WORLD_LOCK:
        if _WORLD is None:
            _WORLD = FakePortal(load_world_shipments())
        return _WORLD


def sample_tasks() -> list[str]:
    w = world()
    inv = next((i for i in w.invoices if not i.is_cancelled), w.invoices[0])
    some = [s for s in list(w.shipments)[:5]]
    return [
        f"Reconcile invoice {inv.invoice_no}.",
        "Reconcile all invoices on lane PUN-HYD dated in October 2026. Do not raise disputes.",
        "Reconcile all invoices on lane PUN-BLR dated in September 2026, and raise disputes for overcharges after approval.",
        "List every invoice on lane PUN-DEL dated in October 2026, with its total and status.",
        "Which shipments did Meridian deliver on lane PUN-CHN in September 2026 that appear on no invoice?",
        f"Download the delivery proofs for {', '.join(some)}, and report the promised and delivered date of each.",
    ]


# ---------------------------------------------------------------- runner


class DemoRunner:
    def __init__(self, store: Store, run_id: str, plan: Plan, task_id: str):
        self.store, self.run_id, self.plan, self.task_id = store, run_id, plan, task_id
        self.w = world()
        self.steps = 0
        self.retries = 0
        self.human_steps: list[str] = []
        self.t0 = time.time()

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._safe_run, daemon=True, name=f"demo-{self.run_id}")
        t.start()
        return t

    def step(self, name: str, outcome: str = "ok", detail: str = "", retries: int = 0):
        self.check_cancel()
        time.sleep(STEP_DELAY)
        self.steps += 1
        self.retries += retries
        self.store.add_step(self.run_id, name, outcome, detail, retries, int(STEP_DELAY * 1000))

    def wait_otp(self):
        rid = self.store.request_human(self.run_id, "otp")
        self.store.set_status(self.run_id, "waiting_for_human")
        self.step("login", "otp_requested", "Portal asked for a one-time password — waiting for the operator")
        while True:
            code = self.store.take_answer(rid)
            if code is not None:
                break
            self.check_cancel()
            time.sleep(0.5)
        self.human_steps.append("otp")
        self.store.set_status(self.run_id, "running")
        self.step("login", "ok", "OTP accepted (code not stored)")

    # ---- progress, stop, documents

    def phase(self, i: int) -> None:
        self.store.set_phase(self.run_id, max(0, min(i, len(self.plan.steps) - 1)))

    def check_cancel(self) -> None:
        if self.store.cancel_requested(self.run_id):
            raise Cancelled()

    def doc(self, kind: str, label: str, lines: list[str], *, scanned: bool = False) -> None:
        from meridian.fakeportal.pdf import make_pdf

        folder = Path("runs/downloads") / self.run_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (label.replace("/", "_") + ".pdf")
        path.write_bytes(make_pdf(lines, scanned=scanned))
        self.store.add_document(self.run_id, kind, label, str(path))

    def invoice_doc(self, inv: Invoice) -> None:
        self.doc("invoice_pdf", f"INV_{inv.invoice_no}", [
            f"TransIndus Roadways - Tax Invoice {inv.invoice_no} (SIMULATED)",
            f"Date {inv.invoice_date:%d-%b-%y}  Lane {inv.lane}  Status {inv.status}",
            *[f"{l.shipment_id}  {l.billed_weight_kg} kg @ {l.rate_per_kg}  line {l.billed_total()}" for l in inv.lines],
            f"Invoice total {inv.total}",
        ])

    def pod_doc(self, sid: str) -> None:
        pod = self.w.pods.get(sid)
        if pod is None or any(d["label"] == f"POD_{sid}" for d in self.store.documents(self.run_id, "pod_pdf")):
            return
        self.doc("pod_pdf", f"POD_{sid}", [f"PROOF OF DELIVERY {sid} (SIMULATED)",
                                           f"Promised Date: {pod.promised_on:%d-%b-%y}",
                                           f"Delivered Date: {pod.delivered_on:%d-%b-%y}"], scanned=not pod.confident)

    def _finish(self, status: str, result: dict, error: str | None = None) -> None:
        result.update(task_id=self.task_id, steps=self.steps, retries=self.retries,
                      duration_s=round(time.time() - self.t0, 1), cost_inr=0.0,
                      trace_id=self.tracer.trace_id, human_steps=self.human_steps)
        if self.tracer.url:
            result["trace_url"] = self.tracer.url
        result["status"] = "failed" if status == "cancelled" else status
        self.store.unsubscribe(self.run_id)
        self.tracer.finish(status, result)
        self.store.set_status(self.run_id, status, result=result, error=error)

    def _safe_run(self):
        from meridian.telemetry import TaskTracer

        run = self.store.get_run(self.run_id)
        self.tracer = TaskTracer(self.run_id, self.task_id, run.task_text if run else "", self.plan.kind, "demo")
        self.store.subscribe(self.run_id, self.tracer)
        try:
            self.store.set_status(self.run_id, "running")
            result = self._run()
            status = result.pop("_status", "completed")
            self.phase(len(self.plan.steps) - 1)
            self._finish(status, result, result.get("error"))
        except Cancelled:
            self.store.add_step(self.run_id, "runner", "cancelled", "Stopped by the operator — progress kept, can resume")
            self._finish("cancelled", {"error": "stopped by operator"}, "stopped by operator")
        except Exception as exc:  # demo: surface errors in the UI
            self.store.add_step(self.run_id, "runner", "failed", f"{type(exc).__name__}: {exc}")
            self._finish("failed", {"error": f"{type(exc).__name__}: {exc}"}, str(exc))

    def _run(self) -> dict:
        p = self.plan
        self.phase(0)
        self.step("open_portal", "ok", "Login.aspx (portal was asleep, first load slow)", retries=1)
        self.wait_otp()
        self.phase(1)
        if p.kind == "list":
            invs = self.w.search(p.params["lane"], p.params["month"])
            self.step("search_invoices", "ok", f"{len(invs)} invoices on {p.params['lane']} {p.params['month']} (2 pages)")
            return {"invoices": [{"invoice_no": i.invoice_no, "total_inr": float(i.total), "status": i.status} for i in invs]}
        if p.kind == "collect":
            pods = []
            needs = False
            for sid in p.params["shipment_ids"]:
                pod = self.w.pods.get(sid)
                if pod is None:
                    self.step(f"pod:{sid}", "not_found", "No delivery proof on the portal")
                    continue
                if not pod.confident:
                    needs = True
                    self.pod_doc(sid)
                    self.step(f"pod:{sid}", "needs_human", "Scanned proof unreadable with confidence")
                    continue
                self.pod_doc(sid)
                self.step(f"pod:{sid}", "ok", f"Downloaded POD_{sid}.pdf")
                pods.append({"shipment_id": sid, "promised_on": pod.promised_on.isoformat(),
                             "delivered_on": pod.delivered_on.isoformat()})
            out = {"pods": pods}
            if needs:
                out["_status"] = "needs_human"
            return out
        if p.kind == "missing":
            self.step("load_meridian_records", "ok", f"{len(self.w.shipments)} shipments")
            self.step("collect_billing_history", "ok", f"{len(self.w.invoices)} invoices across all lanes")
            missing = missing_in_portal(self.w.shipments, p.params["lane"], p.params["month"],
                                        [BillingRecord.from_invoice(i) for i in self.w.invoices])
            return {"missing_in_portal": missing}

        # one / lane_month / dispute
        if p.kind == "one":
            inv = self.w.invoice(p.params["invoice_no"])
            if inv is None:
                self.step("open_invoice", "not_found", p.params["invoice_no"])
                return {"invoices": [], "_status": "failed", "error": f"invoice {p.params['invoice_no']} not found on portal"}
            invs = [inv]
        else:
            invs = self.w.search(p.params["lane"], p.params["month"])
            self.step("search_invoices", "ok", f"{len(invs)} invoices on {p.params['lane']} {p.params['month']}")
        self.phase(2)
        self.step("rate_card", "ok", "Rate card loaded (incl. mid-month change on PUN-BLR)")
        self.step("fuel_surcharge", "ok", "Fuel surcharge by month loaded")
        self.step("billing_history", "ok", "All invoices indexed for duplicate check")
        ref = self.w.reference()
        done = self.store.checkpoints(self.run_id)
        results, needs = [], False
        for n, inv in enumerate(invs):
            if done.get(inv.invoice_no, {}).get("state") == "done":
                results.append(done[inv.invoice_no]["data"])
                continue
            if n == 2 and len(invs) > 3:
                self.step(f"invoice:{inv.invoice_no}", "session_expired", "Logged out mid-task — logging in again, resuming from checkpoint")
                self.wait_otp()
            self.invoice_doc(inv)
            for line in inv.lines:
                self.pod_doc(line.shipment_id)
            self.step(f"invoice:{inv.invoice_no}", "ok", f"{len(inv.lines)} lines, {len(inv.credit_notes)} credit notes, PDF saved")
            r = reconcile_invoice(inv, self.w.shipments, ref)
            self.store.save_detail(self.run_id, inv.invoice_no, explain_invoice(inv, r, self.w.shipments, ref))
            out = r.to_output()
            if r.needs_human:
                needs = True
                out["needs_human"] = r.needs_human
            if r.already_disputed:
                out["existing_dispute"] = True
            self.store.checkpoint(self.run_id, inv.invoice_no, "done", out)
            label = r.result + (f" ({', '.join(r.reasons)})" if r.reasons else "")
            self.step(f"reconcile:{inv.invoice_no}", r.result, label)
            results.append(out)
            if p.kind == "dispute":
                d = propose_dispute(r)
                if d:
                    did = self.store.propose_dispute(self.run_id, d.invoice_no, list(d.reasons), str(d.billed_inr),
                                                     str(d.expected_inr), out.get("evidence", []))
                    if did:
                        self.step(f"dispute:{inv.invoice_no}", "awaiting_approval", f"Overcharge ₹{d.overcharge:,.2f}")
                    else:
                        self.step(f"dispute:{inv.invoice_no}", "skipped", "A dispute is already queued or raised")
                elif r.already_disputed:
                    self.step(f"dispute:{inv.invoice_no}", "skipped", "Dispute already exists on the portal")

        self.phase(4)
        disputes_out = []
        if p.kind == "dispute":
            self.phase(6)
            disputes_out = self._handle_approvals()
        out = {"invoices": results, "disputes": disputes_out}
        if needs:
            out["_status"] = "needs_human"
        return out

    def _handle_approvals(self) -> list[dict]:
        pending = self.store.disputes(status="pending", run_id=self.run_id)
        if pending:
            self.store.set_status(self.run_id, "waiting_for_human")
            self.step("approvals", "waiting", f"{len(pending)} dispute(s) waiting for approval")
            self.human_steps.append("approval")
        while self.store.disputes(status="pending", run_id=self.run_id):
            self.check_cancel()
            time.sleep(0.5)
        self.store.set_status(self.run_id, "running")
        self.phase(7)
        out = []
        for d in self.store.disputes(run_id=self.run_id):
            if d["status"] == "approved":
                if d["invoice_no"] in self.w.disputed:
                    self.store.mark_dispute(d["id"], "skipped", note="already on portal at submit time")
                    self.step(f"dispute:{d['invoice_no']}", "skipped", "Re-checked list before submit: already exists")
                    continue
                self.step(f"dispute:{d['invoice_no']}", "submitted", "Form filled and submitted; receipt saved")
                self.w.disputed.add(d["invoice_no"])
                ref = f"DSP-{sum(map(ord, d['invoice_no'])) * 37 % 100000:05d}"
                self.doc("dispute_receipt", f"DISPUTE_{d['invoice_no']}", [
                    f"Dispute {ref} (SIMULATED)", f"Invoice {d['invoice_no']}", f"Reasons: {', '.join(d['reasons'])}",
                    f"Correct amount: {d['expected_inr']}", f"Approved by: {d.get('decided_by') or 'operator'}"])
                self.step(f"dispute:{d['invoice_no']}", "confirmed", f"Found in dispute list as {ref}")
                self.store.mark_dispute(d["id"], "confirmed", portal_ref=ref)
                out.append({"invoice_no": d["invoice_no"], "reasons": d["reasons"],
                            "expected_inr": float(Decimal(d["expected_inr"])), "portal_ref": ref})
            elif d["status"] == "rejected":
                self.step(f"dispute:{d['invoice_no']}", "rejected", "Operator rejected — not raised")
        return out
