"""Line-by-line explanation of a reconciliation, for people (operator screen, demo).

Pure function of the same inputs the engine used. Not part of the graded task result.
"""
from __future__ import annotations

from decimal import Decimal

from meridian.parsing import to_paise
from meridian.records import Shipment
from meridian.reconcile.engine import GST, WEIGHT_ALLOWANCE, InvoiceResult, MissingReferenceData, rate_for, surcharge_for
from meridian.reconcile.types import Invoice, ReferenceData


def _f(v) -> float | None:
    return None if v is None else float(v)


def explain_invoice(inv: Invoice, result: InvoiceResult, shipments: dict[str, Shipment], ref: ReferenceData) -> dict:
    lines = []
    by_sid = {lr.shipment_id: lr for lr in result.lines}
    for idx, line in enumerate(inv.lines):
        lr = result.lines[idx] if idx < len(result.lines) else by_sid.get(line.shipment_id)
        s = shipments.get(line.shipment_id)
        pod = ref.pods.get(line.shipment_id)
        row = {
            "shipment_id": line.shipment_id,
            "booked_on": s.booked_on.isoformat() if s else None,
            "billed_weight_kg": _f(line.billed_weight_kg),
            "actual_weight_kg": _f(s.actual_weight_kg) if s else None,
            "weight_limit_kg": _f(to_paise(s.actual_weight_kg * WEIGHT_ALLOWANCE)) if s else None,
            "billed_rate": _f(line.rate_per_kg),
            "card_rate": None,
            "billed_fuel_pct": _f(line.fuel_pct),
            "month_fuel_pct": None,
            "detention": _f(line.detention),
            "promised_on": pod.promised_on.isoformat() if pod and pod.promised_on else None,
            "delivered_on": pod.delivered_on.isoformat() if pod and pod.delivered_on else None,
            "days_late": (pod.delivered_on - pod.promised_on).days if pod and pod.promised_on and pod.delivered_on else None,
            "pod_readable": None if pod is None else pod.confident,
            "billed_inr": _f(lr.billed) if lr else _f(line.billed_total()),
            "expected_inr": _f(lr.expected) if lr else None,
            "reasons": list(lr.reasons) if lr else [],
            "needs_human": list(lr.needs_human) if lr else [],
        }
        if s:
            try:
                row["card_rate"] = _f(rate_for(ref, inv.lane or s.lane, s.booked_on))
                row["month_fuel_pct"] = _f(surcharge_for(ref, s.booked_on))
            except MissingReferenceData:
                pass
        lines.append(row)
    billed_sum = sum((Decimal(str(l["billed_inr"])) for l in lines if l["billed_inr"] is not None), Decimal("0"))
    return {
        "invoice_no": inv.invoice_no,
        "invoice_date": inv.invoice_date.isoformat(),
        "lane": inv.lane,
        "status": inv.status,
        "printed_total": _f(inv.total),
        "lines_plus_gst": _f(to_paise(billed_sum * GST)),
        "credit_notes": [_f(c) for c in inv.credit_notes],
        "billed_inr": _f(result.billed_inr),
        "expected_inr": _f(result.expected_inr),
        "overcharge_inr": _f(result.overcharge),
        "result": result.result,
        "reasons": list(result.reasons),
        "already_disputed": result.already_disputed,
        "lines": lines,
    }
