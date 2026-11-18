"""Whole-month run (stretch goal): every lane of one month, in parallel browser contexts.

    month = MonthRunner(settings, "2026-10", workers=4, store=store, run_id=run_id)
    report = run_async(month.run())

How it stays inside the rules
  * One browser, ``workers`` separate browser contexts (own cookies, own pages).
  * One shared RateLimiter for all of them: the portal still sees at most 2 requests a second.
    Parallel is faster because the portal is *slow*, not because we hit it harder: while one
    context waits for a page (or Tesseract reads a scan), the others use the free request slots.
  * One login and one OTP. The lead context logs in; the others start from its saved session. If
    the portal ends the session mid-run, the first context to notice logs in again (one OTP) and
    the rest adopt that session under a shared lock instead of asking for more codes.
  * Read-only. A month run never writes to the portal: it lists the disputes that *should* be
    raised; they are raised through the normal dispute task, with a person approving each one.
  * The numbers come from the same rules engine as every other task (code, not an LLM).

Work is split into three phases, each a queue shared by the contexts:
  1. read every invoice on the portal once (billing history, needed for duplicate billing and
     "missing in portal"), 2. read the delivery proof of every shipment on the month's invoices,
  3. reconcile in code. Phase 3 has no portal calls.
"""
from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from meridian.config import Settings
from meridian.portal.client import PortalClient
from meridian.portal.errors import HumanNeeded, LoginFailed
from meridian.portal.human import HumanGate
from meridian.portal.throttle import RateLimiter
from meridian.reconcile import (
    BillingRecord,
    MissingReferenceData,
    ReferenceData,
    missing_in_portal,
    propose_dispute,
    reconcile_invoice,
)
from meridian.reconcile.explain import explain_invoice

MONTH_STEPS = [
    "Log in once (one OTP from the operator)",
    "Read invoice list, rate card, fuel surcharge, dispute list",
    "Open browser contexts that share the login and the 2 requests/second limit",
    "Read every invoice once, in parallel (billing history)",
    "Read the delivery proofs for the month's shipments, in parallel",
    "Reconcile every invoice of the month in code",
    "Find shipments delivered in the month but never invoiced",
    "Write the monthly summary for the logistics manager (no disputes raised)",
]

FATAL = (HumanNeeded, LoginFailed)
IST = ZoneInfo("Asia/Kolkata")


class Cancelled(Exception):
    """The operator pressed Stop."""


class MonthRunner:
    def __init__(self, settings: Settings, month: str, *, lanes: list[str] | None = None, workers: int = 4,
                 human: HumanGate | None = None, store=None, run_id: str | None = None, headless: bool = True,
                 use_disk_cache: bool = True, out_root: str | Path = "runs"):
        if workers < 1:
            raise ValueError("workers must be at least 1")
        datetime.strptime(month, "%Y-%m")  # validate early
        self.settings, self.month, self.lanes, self.workers = settings, month, lanes, workers
        self.store, self.run_id, self.headless = store, run_id, headless
        self.use_disk_cache = use_disk_cache
        self.out_root = Path(out_root)
        if human is None and store is not None and run_id is not None:
            from meridian.portal.human import StoreHumanGate

            human = StoreHumanGate(store, run_id, on_wait=self._waiting, on_resume=self._resumed)
        if human is None:
            raise ValueError("a human gate (or store + run_id) is needed for the OTP")
        self.human = human
        self.limiter = RateLimiter(settings.max_requests_per_second)
        self.login_lock = asyncio.Lock()
        self.clients: list[PortalClient] = []
        self.human_steps: list[str] = []
        self.phase_s: dict[str, float] = {}

    # ------------------------------------------------------------------ plumbing

    def _step(self, step: str, outcome: str, detail: str = "") -> None:
        if self.store and self.run_id:
            self.store.add_step(self.run_id, step, outcome, detail)

    def _phase(self, i: int) -> None:
        if self.store and self.run_id:
            self.store.set_phase(self.run_id, i)

    def _check_cancel(self) -> None:
        if self.store and self.run_id and self.store.cancel_requested(self.run_id):
            raise Cancelled()

    def _waiting(self, kind: str) -> None:
        self.human_steps.append(kind)
        if self.store and self.run_id:
            self.store.set_status(self.run_id, "waiting_for_human")
            self.store.add_step(self.run_id, kind, "waiting_for_human", "Asked the operator — see the OTP box")

    def _resumed(self, kind: str) -> None:
        if self.store and self.run_id:
            self.store.set_status(self.run_id, "running")

    def _sink_for(self, name: str):
        def sink(step: str, outcome: str, extra: dict) -> None:
            if self.store and self.run_id:
                detail = ", ".join(f"{k}={v}" for k, v in extra.items() if k not in ("path", "page"))[:300]
                self.store.add_step(self.run_id, f"{name} · {step}", outcome, detail, page=extra.get("page"))
        return sink

    def _new_client(self, name: str) -> PortalClient:
        tag = self.run_id or f"month-{self.month}"
        c = PortalClient(self.settings, self.human, self.limiter,
                         download_dir=self.out_root / "downloads" / tag, screenshot_dir=self.out_root / "screenshots" / tag)
        c.login_lock = self.login_lock
        c.log.sink = self._sink_for(name)
        if not self.use_disk_cache:
            c._disk_cache_on = lambda: False
        return c

    def _share_with(self, lead: PortalClient, c: PortalClient) -> None:
        """What the lead already read (links, list, disk caches) is shared, so no context reads it twice.
        All contexts run on one event loop (one thread), so plain shared dicts are safe."""
        c._inv_href = lead._inv_href
        c._listed = lead._listed
        c._full_rows = lead._full_rows
        c._inv_cache = lead._inv_cache
        c.unreadable = lead.unreadable
        c._disk = lead._load_disk()
        c._disk_pods = lead._load_pods()

    async def _pool(self, label: str, items: list, fn) -> tuple[dict, dict]:
        """Run ``fn(client, item)`` for every item, spread over all contexts. A failed item is recorded
        (and goes to a person); an OTP nobody answers or a refused login stops the whole run."""
        queue: asyncio.Queue = asyncio.Queue()
        for it in items:
            queue.put_nowait(it)
        results, errors = {}, {}
        done = 0

        async def worker(c: PortalClient) -> None:
            nonlocal done
            while True:
                try:
                    it = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                self._check_cancel()
                try:
                    results[it] = await fn(c, it)
                except FATAL:
                    raise
                except Exception as exc:
                    errors[it] = f"{type(exc).__name__}: {exc}"[:240]
                done += 1
                if done == len(items) or done % 10 == 0:
                    self._step(label, "progress", f"{done} of {len(items)}")

        t0 = time.time()
        async with asyncio.TaskGroup() as tg:
            for c in self.clients:
                tg.create_task(worker(c))
        self.phase_s[label] = round(time.time() - t0, 1)
        return results, errors

    # ------------------------------------------------------------------ the run

    async def run(self) -> dict:
        from playwright.async_api import async_playwright

        from meridian.agent.live import load_meridian_records

        t0 = time.time()
        shipments = load_meridian_records(self.settings)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            try:
                return await self._run(browser, shipments, t0)
            except BaseExceptionGroup as eg:  # TaskGroup wraps the first fatal error
                raise eg.exceptions[0] from None
            finally:
                for c in self.clients:
                    try:
                        await c.close()
                    except Exception:
                        pass
                await browser.close()

    async def _run(self, browser, shipments, t0: float) -> dict:
        self._phase(0)
        lead = self._new_client("ctx-1")
        await lead.start(browser)
        self.clients.append(lead)
        await lead.login()

        self._phase(1)
        all_rows = await lead.search_invoices()
        rate_card = await lead.rate_card()
        fuel = await lead.fuel_surcharge()
        disputed = lead.disputed_invoices(await lead.dispute_list())
        lanes = self.lanes or sorted({r.lane for r in all_rows if r.lane} |
                                     {s.lane for s in shipments.values()
                                      if s.delivered_on.strftime("%Y-%m") == self.month})
        self._step("month", "ok", f"{len(all_rows)} invoices on the portal · lanes {', '.join(lanes)}")

        self._phase(2)
        for n in range(2, self.workers + 1):
            c = self._new_client(f"ctx-{n}")
            await c.start(browser)  # starts from the lead's saved session: no second OTP
            self._share_with(lead, c)
            self.clients.append(c)
        self._step("contexts", "ok", f"{len(self.clients)} browser contexts, one shared limit of "
                                     f"{self.settings.max_requests_per_second:g} requests/second")

        # 1. every invoice once -> billing history
        self._phase(3)

        async def read_invoice(c: PortalClient, no: str):
            inv, pdf = await c.open_invoice(no)
            if inv is None:
                raise RuntimeError("listed but could not be opened")
            return inv, pdf

        invoices, inv_errors = await self._pool("invoices", [r.invoice_no for r in all_rows], read_invoice)
        index: dict[str, list] = {}
        row_by_no = {r.invoice_no: r for r in all_rows}
        for no, (inv, _) in invoices.items():
            for line in inv.lines:
                index.setdefault(line.shipment_id, []).append(row_by_no[no])

        # 2. delivery proofs for the month's shipments
        self._phase(4)
        targets = [r for r in all_rows
                   if r.invoice_date is not None and r.invoice_date.strftime("%Y-%m") == self.month
                   and (r.lane in lanes or (r.lane is None and r.invoice_no in invoices
                                            and invoices[r.invoice_no][0].lane in lanes))]
        sids = sorted({l.shipment_id for r in targets if r.status.lower() != "cancelled" and r.invoice_no in invoices
                       for l in invoices[r.invoice_no][0].lines})
        pods, pod_errors = await self._pool("pods", sids, lambda c, sid: c.get_pod(sid))

        # 3. reconcile in code (no portal calls from here on)
        self._phase(5)
        lane_out: dict[str, dict] = {ln: {"invoices": [], "missing_in_portal": [], "disputes_to_raise": []} for ln in lanes}
        details: dict[str, dict] = {}
        pod_map = {s: p for s, (p, _) in pods.items() if p is not None}
        for row in sorted(targets, key=lambda r: r.invoice_no):
            out, detail, proposal = self._reconcile_row(row, invoices, inv_errors, index, pod_errors, pod_map,
                                                        shipments, rate_card, fuel, disputed)
            lane = row.lane or (invoices[row.invoice_no][0].lane if row.invoice_no in invoices else "")
            bucket = lane_out.setdefault(lane, {"invoices": [], "missing_in_portal": [], "disputes_to_raise": []})
            bucket["invoices"].append(out)
            if detail is not None:
                details[row.invoice_no] = detail
                if self.store and self.run_id:
                    self.store.save_detail(self.run_id, row.invoice_no, detail)
            if proposal is not None:
                bucket["disputes_to_raise"].append(proposal)
            self._step(f"reconcile:{row.invoice_no}", out["result"],
                       ", ".join(out.get("reasons") or []) or out.get("error", "") or out["result"])

        # missing in portal uses the DELIVERY month, against every invoice read
        self._phase(6)
        history = [BillingRecord.from_invoice(inv) for inv, _ in invoices.values()]
        for ln in lanes:
            lane_out.setdefault(ln, {"invoices": [], "missing_in_portal": [], "disputes_to_raise": []})
            lane_out[ln]["missing_in_portal"] = missing_in_portal(shipments, ln, self.month, history)
        if inv_errors:
            # an invoice we could not read might bill one of these shipments: don't call any missing on a guess
            for ln in lanes:
                if lane_out[ln]["missing_in_portal"]:
                    lane_out[ln]["missing_unsure"] = True

        self._phase(7)
        steps = sum(c.log.steps for c in self.clients)
        retries = sum(c.log.retries.retries for c in self.clients)
        wall = round(time.time() - t0, 1)
        needs = any(i.get("needs_human") for b in lane_out.values() for i in b["invoices"]) or bool(inv_errors)
        return {
            "month": self.month,
            "status": "needs_human" if needs else "completed",
            "lanes": lane_out,
            "invoices": [i for b in lane_out.values() for i in b["invoices"]],
            "missing_in_portal": sorted(s for b in lane_out.values() for s in b["missing_in_portal"]),
            "disputes": [],  # read-only: nothing is raised by a month run
            "disputes_to_raise": [d for b in lane_out.values() for d in b["disputes_to_raise"]],
            "errors": {**{f"invoice:{k}": v for k, v in inv_errors.items()}, **{f"pod:{k}": v for k, v in pod_errors.items()}},
            "workers": self.workers,
            "requests": self.limiter.count,
            "requests_per_s": round(self.limiter.count / wall, 2) if wall else 0.0,
            "phase_s": self.phase_s,
            "invoices_read": len(invoices),
            "pods_read": len(pods),
            "human_steps": self.human_steps,
            "steps": steps, "retries": retries, "duration_s": wall, "cost_inr": 0.0,
            "_details": details,
        }

    def _reconcile_row(self, row, invoices, inv_errors, index, pod_errors, pod_map, shipments, rate_card, fuel, disputed):
        """Same rules and the same billing-history view as a lane-and-month task (agent/live.py)."""
        no = row.invoice_no
        if row.status.lower() == "cancelled":
            return {"invoice_no": no, "result": "cancelled"}, None, None
        if no not in invoices:
            return ({"invoice_no": no, "result": "mismatch", "reasons": [],
                     "needs_human": [f"invoice could not be read: {inv_errors.get(no, 'unknown')}"]}, None, None)
        inv, _ = invoices[no]
        if no in self.clients[0].unreadable:
            return ({"invoice_no": no, "result": "mismatch", "reasons": [],
                     "needs_human": [f"scanned invoice unreadable: {self.clients[0].unreadable[no]}"]}, None, None)
        if not inv.lane:
            inv = replace(inv, lane=row.lane or "")
        history = [BillingRecord.from_invoice(inv)]
        for line in inv.lines:
            history += [BillingRecord(r.invoice_no, r.invoice_date, r.status, (line.shipment_id,))
                        for r in index.get(line.shipment_id, [])
                        if r.invoice_no != no and r.invoice_date is not None]
        failed_pods = [l.shipment_id for l in inv.lines if l.shipment_id in pod_errors]
        if failed_pods:
            # "no POD" must never be concluded from a download that failed
            return ({"invoice_no": no, "result": "mismatch", "reasons": [],
                     "needs_human": [f"delivery proof could not be read: {', '.join(failed_pods)}"]}, None, None)
        ref = ReferenceData(rate_card, fuel, pod_map, history, set(disputed))
        try:
            r = reconcile_invoice(inv, shipments, ref)
        except MissingReferenceData as exc:
            return {"invoice_no": no, "result": "mismatch", "reasons": [], "needs_human": [str(exc)]}, None, None
        out = r.to_output()
        if r.needs_human:
            out["needs_human"] = r.needs_human
        if r.already_disputed:
            out["existing_dispute"] = True
        d = propose_dispute(r)
        proposal = None if d is None else {
            "invoice_no": d.invoice_no, "reasons": list(d.reasons), "billed_inr": float(d.billed_inr),
            "expected_inr": float(d.expected_inr), "overcharge_inr": float(d.overcharge)}
        return out, explain_invoice(inv, r, shipments, ref), proposal


# ---------------------------------------------------------------------- summary for the manager


def _inr(v) -> str:
    """₹ with Indian digit grouping (1,71,710.58), as Meridian's staff write amounts."""
    d = Decimal(str(v or 0))
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        whole = f"{head},{tail}"
    return ("-" if d < 0 else "") + f"₹{whole}.{frac}"


def write_summary(report: dict, out_dir: str | Path, *, sequential_s: float | None = None) -> dict[str, Path]:
    """The logistics manager's monthly summary: summary.md (readable), invoices.csv, report.json."""
    import csv
    import json

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    month_name = datetime.strptime(report["month"], "%Y-%m").strftime("%B %Y")
    rows = []
    for lane, b in sorted(report["lanes"].items()):
        for i in b["invoices"]:
            billed, expected = i.get("billed_inr"), i.get("expected_inr")
            over = round(billed - expected, 2) if billed is not None and expected is not None else None
            rows.append({"lane": lane, "invoice_no": i["invoice_no"], "result": i["result"],
                         "reasons": ", ".join(i.get("reasons") or []), "billed_inr": billed, "expected_inr": expected,
                         "overcharge_inr": over, "already_disputed": bool(i.get("existing_dispute")),
                         "needs_person": "; ".join(i.get("needs_human") or [])})

    with open(out / "invoices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["lane", "invoice_no", "result"])
        w.writeheader()
        w.writerows(rows)

    checked = [r for r in rows if r["result"] != "cancelled"]
    over_total = sum(max(r["overcharge_inr"] or 0, 0) for r in checked)
    reasons = Counter(x for r in checked for x in (r["reasons"].split(", ") if r["reasons"] else []))
    to_raise = report.get("disputes_to_raise", [])
    lines = [
        f"# TransIndus billing check — {month_name}",
        "",
        f"For the logistics manager · generated {datetime.now(IST):%d %b %Y %H:%M} IST · read-only run, no disputes raised.",
        "",
        "## At a glance",
        "",
        "| | |",
        "|---|---|",
        f"| Invoices checked | {len(checked)} (+{len(rows) - len(checked)} cancelled) |",
        f"| Billed right | {sum(r['result'] == 'match' for r in checked)} |",
        f"| Overcharged / wrong | {sum(r['result'] == 'mismatch' for r in checked)} |",
        f"| Amount over-billed | {_inr(over_total)} |",
        f"| Disputes to raise (need approval) | {len(to_raise)} · {_inr(sum(d['overcharge_inr'] for d in to_raise))} |",
        f"| Already disputed | {sum(r['already_disputed'] for r in checked)} |",
        f"| Delivered but never invoiced | {len(report.get('missing_in_portal', []))} shipments |",
        f"| Needs a person | {sum(bool(r['needs_person']) for r in rows)} invoices |",
        "",
        "## By lane",
        "",
        "| Lane | Invoices | Billed right | Wrong | Over-billed | Missing invoices |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for lane, b in sorted(report["lanes"].items()):
        lr = [r for r in checked if r["lane"] == lane]
        lines.append(f"| {lane} | {len(lr)} | {sum(r['result'] == 'match' for r in lr)} | "
                     f"{sum(r['result'] == 'mismatch' for r in lr)} | "
                     f"{_inr(sum(max(r['overcharge_inr'] or 0, 0) for r in lr))} | {len(b['missing_in_portal'])} |")
    lines += ["", "## Why invoices were wrong", ""]
    lines += [f"- {k}: {v} lines/invoices" for k, v in reasons.most_common()] or ["- Nothing wrong this month."]
    lines += ["", "## Disputes to raise", "",
              "Raise these with the dispute task in the operator screen; each one needs a person to approve it.", ""]
    if to_raise:
        lines += ["| Invoice | Reasons | Billed | Correct amount | Over |", "|---|---|---:|---:|---:|"]
        lines += [f"| {d['invoice_no']} | {', '.join(d['reasons'])} | {_inr(d['billed_inr'])} | "
                  f"{_inr(d['expected_inr'])} | {_inr(d['overcharge_inr'])} |" for d in to_raise]
    else:
        lines.append("None.")
    missing = {ln: b["missing_in_portal"] for ln, b in report["lanes"].items() if b["missing_in_portal"]}
    lines += ["", "## Delivered but never invoiced (not disputed)", ""]
    lines += [f"- {ln}: {', '.join(m)}" + (" (unsure: an invoice could not be read)" if report['lanes'][ln].get('missing_unsure') else "")
              for ln, m in sorted(missing.items())] or ["- None."]
    need = [r for r in rows if r["needs_person"]]
    if need or report.get("errors"):
        lines += ["", "## Needs a person", ""]
        lines += [f"- {r['invoice_no']}: {r['needs_person']}" for r in need]
        lines += [f"- {k}: {v}" for k, v in report.get("errors", {}).items()]
    lines += ["", "## How the run went", "",
              f"- {report['workers']} parallel browser contexts, {report['requests']} portal requests at "
              f"{report['requests_per_s']} requests/second (limit 2).",
              f"- {report['duration_s']} s in total; phases: " + ", ".join(f"{k} {v} s" for k, v in report.get("phase_s", {}).items()) + ".",
              f"- {report['steps']} steps, {report['retries']} retries, human steps: {', '.join(report['human_steps']) or 'none'}."]
    if sequential_s:
        lines.append(f"- Same month one context at a time: {sequential_s} s → "
                     f"{sequential_s / report['duration_s']:.1f}× faster in parallel.")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    public = {k: v for k, v in report.items() if not k.startswith("_")}
    if sequential_s:
        public["sequential_s"] = sequential_s
    (out / "report.json").write_text(json.dumps(public, indent=2, default=str), encoding="utf-8")
    return {"summary": out / "summary.md", "csv": out / "invoices.csv", "json": out / "report.json"}
