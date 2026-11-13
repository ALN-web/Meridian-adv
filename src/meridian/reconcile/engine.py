"""Reconciliation rules — deterministic, in code. The LLM never does arithmetic or decides matches.

Per line, in this order:
    shipment_unknown -> duplicate_billing -> no_pod
If any fires, the line's expected amount is 0 and no other line rule is checked.
Otherwise weight_over, rate_wrong, surcharge_wrong, detention_unjustified are all checked.
Invoice level: math_error (billed lines + 12 % GST != invoice total).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from meridian.parsing import to_paise
from meridian.records import Shipment
from meridian.reconcile.types import BillingRecord, Invoice, InvoiceLine, ReferenceData

ZERO = Decimal("0")
GST = Decimal("1.12")
TOLERANCE = Decimal("1")  # amounts compared within ₹1
WEIGHT_ALLOWANCE = Decimal("1.02")  # billed may exceed actual by up to 2 %
DETENTION_MIN_DAYS_LATE = 2
DISPUTE_THRESHOLD = Decimal("500")  # dispute only when billed > expected + ₹500
RATE_TOLERANCE = Decimal("0.005")  # rates compared to the paisa

REASON_ORDER = (
    "shipment_unknown",
    "duplicate_billing",
    "no_pod",
    "weight_over",
    "rate_wrong",
    "surcharge_wrong",
    "detention_unjustified",
    "math_error",
)
_SHORT_CIRCUIT = {"shipment_unknown", "duplicate_billing", "no_pod"}


class MissingReferenceData(Exception):
    """A rate or surcharge needed for a check isn't available — never guess, escalate."""


@dataclass
class LineResult:
    shipment_id: str
    reasons: list[str]
    billed: Decimal
    expected: Decimal
    needs_human: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class InvoiceResult:
    invoice_no: str
    result: str  # match | mismatch | cancelled
    reasons: list[str]
    billed_inr: Decimal | None
    expected_inr: Decimal | None
    lines: list[LineResult] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    needs_human: list[str] = field(default_factory=list)
    already_disputed: bool = False

    @property
    def overcharge(self) -> Decimal:
        if self.billed_inr is None or self.expected_inr is None:
            return ZERO
        return self.billed_inr - self.expected_inr

    def to_output(self) -> dict:
        """Shape used in the task result (``invoices`` entries)."""
        out: dict = {"invoice_no": self.invoice_no, "result": self.result}
        if self.result != "cancelled":
            out.update(
                reasons=list(self.reasons),
                billed_inr=float(self.billed_inr) if self.billed_inr is not None else None,
                expected_inr=float(self.expected_inr) if self.expected_inr is not None else None,
                evidence=list(self.evidence),
            )
        return out


@dataclass(frozen=True)
class DisputeProposal:
    """Prepared by the engine; raised on the portal only after a person approves it."""

    invoice_no: str
    reasons: tuple[str, ...]
    billed_inr: Decimal
    expected_inr: Decimal

    @property
    def overcharge(self) -> Decimal:
        return self.billed_inr - self.expected_inr


# ---------------------------------------------------------------- lookups


def rate_for(ref: ReferenceData, lane: str, on: date) -> Decimal:
    """Rate effective on ``on`` for ``lane`` (latest effective_from <= on)."""
    candidates = [
        e
        for e in ref.rate_card
        if e.lane == lane and e.effective_from <= on and (e.effective_to is None or on <= e.effective_to)
    ]
    if not candidates:
        raise MissingReferenceData(f"No rate card entry for {lane} on {on.isoformat()}")
    return max(candidates, key=lambda e: e.effective_from).rate_per_kg


def surcharge_for(ref: ReferenceData, on: date) -> Decimal:
    key = on.strftime("%Y-%m")
    if key not in ref.fuel_surcharge_pct:
        raise MissingReferenceData(f"No fuel surcharge for {key}")
    return ref.fuel_surcharge_pct[key]


def _earlier_live_billing(
    history: list[BillingRecord], invoice: Invoice, shipment_id: str, line_index: int
) -> str | None:
    """Invoice number of an earlier, non-cancelled invoice that already billed this shipment."""
    for rec in sorted(history, key=lambda r: r.sort_key):
        if rec.is_cancelled or rec.invoice_no == invoice.invoice_no:
            continue
        if rec.sort_key < invoice.sort_key and shipment_id in rec.shipment_ids:
            return rec.invoice_no
    # Same shipment twice on this invoice: the second occurrence is the duplicate.
    earlier_on_same = [l.shipment_id for l in invoice.lines[:line_index]]
    if shipment_id in earlier_on_same:
        return invoice.invoice_no
    return None


# ---------------------------------------------------------------- rules


def check_line(
    invoice: Invoice,
    line_index: int,
    shipments: dict[str, Shipment],
    ref: ReferenceData,
) -> LineResult:
    line: InvoiceLine = invoice.lines[line_index]
    sid = line.shipment_id
    billed = line.billed_total()
    evidence = [f"portal:invoice/{invoice.invoice_no}"]

    # 1. shipment_unknown
    shipment = shipments.get(sid)
    if shipment is None:
        return LineResult(sid, ["shipment_unknown"], billed, ZERO, evidence=evidence)
    evidence.append(f"meridian:{sid}")

    # 2. duplicate_billing
    earlier = _earlier_live_billing(ref.billing_history, invoice, sid, line_index)
    if earlier is not None:
        evidence.append(f"portal:invoice/{earlier}")
        return LineResult(sid, ["duplicate_billing"], billed, ZERO, evidence=evidence)

    # 3. no_pod
    pod = ref.pods.get(sid)
    if pod is None:
        return LineResult(sid, ["no_pod"], billed, ZERO, evidence=evidence)
    evidence.append(f"pod:{sid}")

    reasons: list[str] = []
    needs_human: list[str] = []

    # weight_over
    if line.billed_weight_kg > shipment.actual_weight_kg * WEIGHT_ALLOWANCE:
        reasons.append("weight_over")

    # rate_wrong — rate effective on the booking date
    card_rate = rate_for(ref, invoice.lane if invoice.lane else shipment.lane, shipment.booked_on)
    if abs(line.rate_per_kg - card_rate) > RATE_TOLERANCE:
        reasons.append("rate_wrong")

    # surcharge_wrong — percentage for the booking month
    pct = surcharge_for(ref, shipment.booked_on)
    if line.fuel_pct is not None:
        if line.fuel_pct != pct:
            reasons.append("surcharge_wrong")
    elif line.fuel_amount is not None:
        if abs(line.fuel_amount - to_paise(line.billed_freight() * pct / 100)) > TOLERANCE:
            reasons.append("surcharge_wrong")

    # detention — justified only when delivered >= 2 days after the promised date
    justified_detention = ZERO
    if line.detention > ZERO:
        if not pod.confident or pod.promised_on is None or pod.delivered_on is None:
            needs_human.append(f"pod_unreadable:{sid}")
            justified_detention = line.detention  # unknown: don't assert it's wrong
        elif (pod.delivered_on - pod.promised_on).days >= DETENTION_MIN_DAYS_LATE:
            justified_detention = line.detention
        else:
            reasons.append("detention_unjustified")

    freight = to_paise(shipment.actual_weight_kg * card_rate)
    fuel = to_paise(freight * pct / 100)
    expected = freight + fuel + justified_detention
    return LineResult(sid, reasons, billed, expected, needs_human=needs_human, evidence=evidence)


def reconcile_invoice(
    invoice: Invoice,
    shipments: dict[str, Shipment],
    ref: ReferenceData,
) -> InvoiceResult:
    if invoice.is_cancelled:
        return InvoiceResult(invoice.invoice_no, "cancelled", [], None, None)

    lines = [check_line(invoice, i, shipments, ref) for i in range(len(invoice.lines))]

    reasons: set[str] = set()
    for lr in lines:
        reasons.update(lr.reasons)

    billed_lines_sum = sum((lr.billed for lr in lines), ZERO)
    if abs(to_paise(billed_lines_sum * GST) - invoice.total) > TOLERANCE:
        reasons.add("math_error")

    expected_lines_sum = sum((lr.expected for lr in lines), ZERO)
    expected = to_paise(expected_lines_sum * GST) - invoice.credit_total
    billed = invoice.total - invoice.credit_total

    ordered = [r for r in REASON_ORDER if r in reasons]
    is_match = not ordered and abs(billed - expected) <= TOLERANCE

    evidence: list[str] = []
    for lr in lines:
        for e in lr.evidence:
            if e not in evidence:
                evidence.append(e)

    return InvoiceResult(
        invoice_no=invoice.invoice_no,
        result="match" if is_match else "mismatch",
        reasons=ordered,
        billed_inr=to_paise(billed),
        expected_inr=to_paise(expected),
        lines=lines,
        evidence=evidence,
        needs_human=[h for lr in lines for h in lr.needs_human],
        already_disputed=invoice.invoice_no in ref.disputed_invoices,
    )


def propose_dispute(result: InvoiceResult) -> DisputeProposal | None:
    """One dispute per mismatched invoice billed > ₹500 above expected; never if one already exists
    or if any line still needs a human to read its proof."""
    if result.result != "mismatch" or result.already_disputed or result.needs_human:
        return None
    if result.billed_inr is None or result.expected_inr is None:
        return None
    if result.overcharge <= DISPUTE_THRESHOLD:
        return None
    return DisputeProposal(result.invoice_no, tuple(result.reasons), result.billed_inr, result.expected_inr)


def missing_in_portal(
    shipments: dict[str, Shipment],
    lane: str,
    delivery_month: str,
    history: list[BillingRecord],
    *,
    ignore_cancelled: bool = False,
) -> list[str]:
    """Shipments Meridian delivered on ``lane`` in ``delivery_month`` (YYYY-MM) that appear on no invoice.

    By default any invoice counts (the brief says "appears on no invoice"); pass
    ``ignore_cancelled=True`` to treat shipments only on cancelled invoices as missing.
    """
    billed: set[str] = set()
    for rec in history:
        if ignore_cancelled and rec.is_cancelled:
            continue
        billed.update(rec.shipment_ids)
    return sorted(
        s.shipment_id
        for s in shipments.values()
        if s.lane == lane and s.delivered_on.strftime("%Y-%m") == delivery_month and s.shipment_id not in billed
    )
