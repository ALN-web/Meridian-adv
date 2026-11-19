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
from datetime import date

LANES = ("PUN-BLR", "PUN-HYD", "PUN-CHN", "PUN-DEL", "PUN-AMD")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

_INVOICE = re.compile(r"\b([A-Z]{2,5}/\d{2}-\d{2}/\d{3,6})\b", re.I)
_SHIPMENT = re.compile(r"\bSHP-\d{3,6}\b", re.I)
_LANE = re.compile(r"\bPUN[\s_-]*([A-Z]{3})\b", re.I)          # PUN-BLR, pun blr, PUN_BLR (dashes normalised first)
CITIES = {"bengaluru": "BLR", "bangalore": "BLR", "hyderabad": "HYD", "chennai": "CHN", "madras": "CHN",
          "delhi": "DEL", "new delhi": "DEL", "ahmedabad": "AMD"}
_SEP = r"[\s.,'/-]*"
_MONTH = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")[a-z]*" + _SEP + r"(\d{4}|'?\d{2})\b", re.I)
_ISO_MONTH = re.compile(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b(?![-/]\d)")
_NUM_MONTH = re.compile(r"\b(0?[1-9]|1[0-2])[-/](20\d{2})\b")
_BARE_MONTH = re.compile(r"\b(january|february|march|april|june|july|august|september|october|november|december)\b", re.I)

# Writing to the portal only when clearly asked, and never when the task says not to.
_DISPUTE_YES = re.compile(r"\b(raise|file|submit|lodge|open)\b[^.;]{0,25}\bdisputes?\b"
                          r"|\bdispute\s+(any|all|the|each|every)?\s*(overcharg|invoice|wrong)", re.I)
_DISPUTE_NO = re.compile(r"\b(do not|don't|dont|without|never|no need to|not to)\b[^.;]{0,25}\b(disput|rais|fil)"
                         r"|\bno disputes?\b|\bcould dispute\b|\bwhich (ones )?(we )?(could|should|can) dispute\b", re.I)


class PlanError(ValueError):
    pass


@dataclass
class Plan:
    kind: str
    params: dict
    steps: list[str] = field(default_factory=list)


def _month(text: str, today: date | None = None) -> str | None:
    m = _ISO_MONTH.search(text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = _NUM_MONTH.search(text)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = _MONTH.search(text)
    if m:
        year = m.group(2).lstrip("'")
        year = int(year) + 2000 if len(year) == 2 else int(year)
        return f"{year:04d}-{MONTHS[m.group(1).lower()[:3] if m.group(1).lower() not in MONTHS else m.group(1).lower()]:02d}"
    m = _BARE_MONTH.search(text)  # "for August": the latest August that isn't in the future
    if m:
        today = today or date.today()
        mon = MONTHS[m.group(1).lower()]
        return f"{today.year if mon <= today.month else today.year - 1:04d}-{mon:02d}"
    return None


def _lane(text: str) -> str | None:
    m = _LANE.search(text)
    if m:
        lane = f"PUN-{m.group(1).upper()}"
        if lane not in LANES:
            raise PlanError(f"Unknown lane {lane}. Lanes: {', '.join(LANES)}.")
        return lane
    low = text.lower()
    found = {code for city, code in CITIES.items() if re.search(rf"\b{city}\b", low)}
    return f"PUN-{found.pop()}" if len(found) == 1 else None


def plan_task(text: str, today: date | None = None) -> Plan:
    t = " ".join(text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2192", " to ").split())
    low = t.lower()
    lane = _lane(t)
    month = _month(t, today)
    invoices = [m.upper() for m in _INVOICE.findall(t)]
    shipments = list(dict.fromkeys(s.upper() for s in _SHIPMENT.findall(t)))

    if shipments and re.search(r"deliver(y|ed)? proof|proofs? of delivery|\bpods?\b|download|promised|delivered date", low):
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

    if re.search(r"\blist\b|\bshow\b|\b(what|which) invoices\b|total and status", low) and not re.search(
            r"reconcile|\baudit\b|\bcheck\b", low):
        _need(lane, month, t)
        return Plan("list", {"lane": lane, "month": month}, [
            "Log in to the portal (OTP via operator if asked)",
            f"Search invoices on {lane} for {month}, every page",
            "Report invoice number, total as printed, and status",
        ])

    if len(invoices) == 1 and not re.search(r"\ball invoices|\bevery invoice", low):
        inv = invoices[0]
        return Plan("one", {"invoice_no": inv}, [
            "Log in to the portal (OTP via operator if asked)",
            f"Open invoice {inv}: lines, credit notes, PDF",
            "Collect PODs, rate card and fuel surcharge for its shipments",
            "Collect billing history to detect duplicates",
            "Apply reconciliation rules in code",
            "Report result with reasons, billed and expected amounts, and evidence",
        ])

    if re.search(r"reconcile|check|audit|verify", low) and lane and month:
        dispute = bool(_DISPUTE_YES.search(low)) and not _DISPUTE_NO.search(low)
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
