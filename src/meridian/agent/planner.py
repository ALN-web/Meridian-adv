"""Plain English task -> (kind, params, visible plan). Code first; an LLM fallback can come later.

Handles the six task kinds in the brief, e.g.
  "List every invoice on lane PUN-DEL dated in October 2026, with its total and status."
  "Reconcile invoice TIR/26-27/10196."
  "Reconcile all invoices on lane PUN-BLR dated in August 2026. Do not raise disputes."
  "Which shipments did Meridian deliver on lane PUN-CHN in September 2026 that appear on no invoice?"
  "Download the delivery proofs for SHP-60225, SHP-60421 ... and report the promised and delivered date."
  "Reconcile all invoices on lane PUN-HYD dated in October 2026, and raise disputes for overcharges after approval."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LANES = ("PUN-BLR", "PUN-HYD", "PUN-CHN", "PUN-DEL", "PUN-AMD")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

_INVOICE = re.compile(r"\b([A-Z]{2,5}/\d{2}-\d{2}/\d{3,6})\b", re.I)
_SHIPMENT = re.compile(r"\bSHP-\d{3,6}\b", re.I)
_LANE = re.compile(r"\bPUN-[A-Z]{3}\b", re.I)
_MONTH = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")[a-z]*\.?,?\s*(\d{4}|'?\d{2})\b", re.I)
_ISO_MONTH = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b")


class PlanError(ValueError):
    pass


@dataclass
class Plan:
    kind: str
    params: dict
    steps: list[str] = field(default_factory=list)


def _month(text: str) -> str | None:
    m = _ISO_MONTH.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = _MONTH.search(text)
    if not m:
        return None
    year = m.group(2).lstrip("'")
    year = int(year) + 2000 if len(year) == 2 else int(year)
    return f"{year:04d}-{MONTHS[m.group(1).lower()]:02d}"


def plan_task(text: str) -> Plan:
    t = " ".join(text.split())
    low = t.lower()
    lane = (_LANE.search(t).group(0).upper() if _LANE.search(t) else None)
    month = _month(t)
    invoices = [m.upper() for m in _INVOICE.findall(t)]
    shipments = list(dict.fromkeys(s.upper() for s in _SHIPMENT.findall(t)))

    if shipments and re.search(r"deliver(y|ed)? proof|pod|download", low):
        return Plan("collect", {"shipment_ids": shipments}, [
            "Log in to the portal (OTP via operator if asked)",
            *[f"Open delivery proof for {s}, download it, read promised & delivered dates" for s in shipments],
            "Report dates as YYYY-MM-DD; flag any proof that can't be read confidently",
        ])

    if re.search(r"never invoiced|no invoice|not (been )?invoiced|missing|never billed|not billed", low):
        _need(lane, month, t)
        return Plan("missing", {"lane": lane, "month": month}, [
            f"Load Meridian shipments on {lane} delivered in {month}",
            "Log in to the portal (OTP via operator if asked)",
            "Collect every invoice (all statuses, all pages) and the shipments on them",
            "Report shipments that appear on no invoice (no disputes)",
        ])

    if re.search(r"\blist\b|show (me )?(all|every)", low) and not re.search(r"reconcile", low):
        _need(lane, month, t)
        return Plan("list", {"lane": lane, "month": month}, [
            "Log in to the portal (OTP via operator if asked)",
            f"Search invoices on {lane} for {month}, every page",
            "Report invoice number, total as printed, and status",
        ])

    if invoices and len(invoices) == 1 and not lane:
        inv = invoices[0]
        return Plan("one", {"invoice_no": inv}, [
            "Log in to the portal (OTP via operator if asked)",
            f"Open invoice {inv}: lines, credit notes, PDF",
            "Collect PODs, rate card and fuel surcharge for its shipments",
            "Collect billing history to detect duplicates",
            "Apply reconciliation rules in code",
            "Report result with reasons, billed and expected amounts, and evidence",
        ])

    if re.search(r"reconcile|check|audit", low) and lane and month:
        dispute = bool(re.search(r"raise (a )?disputes?|file disputes?|dispute (the )?overcharges?", low)) and not re.search(
            r"(do not|don't|without|no) (raise|rais|dispute)", low)
        kind = "dispute" if dispute else "lane_month"
        steps = [
            "Log in to the portal (OTP via operator if asked)",
            f"Search invoices on {lane} for {month}, every page",
            "For each invoice: lines, credit notes, PODs (resume from checkpoint)",
            "Load rate card, fuel surcharge and billing history",
            "Apply reconciliation rules in code",
        ]
        if dispute:
            steps += [
                "Check the portal's dispute list; skip invoices that already have one",
                "Queue disputes over ₹500 for human approval",
                "Submit approved disputes, then confirm each appears in the dispute list",
            ]
        steps.append("Report every invoice with result, reasons and amounts")
        return Plan(kind, {"lane": lane, "month": month}, steps)

    raise PlanError("Could not understand the task. Mention an invoice number, or a lane (e.g. PUN-BLR) and a month.")


def _need(lane, month, text):
    if not lane or not month:
        raise PlanError(f"Need a lane and a month in: {text!r}")
