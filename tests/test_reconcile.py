"""Unit tests for the reconciliation rules. Synthetic numbers only.

Baseline: PUN-BLR rate ₹10.00/kg (₹11.00 from 15 Oct), fuel 15 % in Oct.
SHP-1: 1000 kg booked 10 Oct -> freight 10,000 + fuel 1,500 = 11,500; × 1.12 = 12,880.00.
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from meridian.records import Shipment
from meridian.reconcile import (
    BillingRecord,
    Invoice,
    InvoiceLine,
    MissingReferenceData,
    Pod,
    RateCardEntry,
    ReferenceData,
    missing_in_portal,
    propose_dispute,
    reconcile_invoice,
)

LANE = "PUN-BLR"


def ship(sid, kg, booked, delivered, lane=LANE):
    return Shipment(sid, booked, lane, D(kg), delivered, f"MF-{sid[-1]}")


SHIPMENTS = {
    "SHP-1": ship("SHP-1", "1000", date(2026, 10, 10), date(2026, 10, 12)),
    "SHP-2": ship("SHP-2", "500", date(2026, 10, 20), date(2026, 10, 22)),  # after rate change
    "SHP-3": ship("SHP-3", "200", date(2026, 9, 28), date(2026, 10, 1)),  # booked Sep, delivered Oct
}


def pods(**overrides):
    base = {
        "SHP-1": Pod("SHP-1", date(2026, 10, 12), date(2026, 10, 12)),
        "SHP-2": Pod("SHP-2", date(2026, 10, 22), date(2026, 10, 22)),
        "SHP-3": Pod("SHP-3", date(2026, 9, 30), date(2026, 10, 1)),
    }
    base.update(overrides)
    return base


def ref(history=(), disputed=(), pod_map=None):
    return ReferenceData(
        rate_card=[
            RateCardEntry(LANE, D("10.00"), date(2026, 8, 1)),
            RateCardEntry(LANE, D("11.00"), date(2026, 10, 15)),
        ],
        fuel_surcharge_pct={"2026-08": D("10"), "2026-09": D("12"), "2026-10": D("15")},
        pods=pod_map if pod_map is not None else pods(),
        billing_history=list(history),
        disputed_invoices=set(disputed),
    )


def good_line(**kw):
    base = dict(shipment_id="SHP-1", billed_weight_kg=D("1000"), rate_per_kg=D("10.00"), fuel_pct=D("15"))
    base.update(kw)
    return InvoiceLine(**base)


def invoice(lines, total=None, no="TIR/26-27/10200", on=date(2026, 10, 25), status="Open", credits=()):
    lines = tuple(lines)
    if total is None:
        total = (sum((l.billed_total() for l in lines), D("0")) * D("1.12")).quantize(D("0.01"))
    return Invoice(no, on, LANE, status, total, lines, tuple(credits))


# ---------------------------------------------------------------- happy path


def test_clean_invoice_matches():
    inv = invoice([good_line()])
    r = reconcile_invoice(inv, SHIPMENTS, ref([BillingRecord.from_invoice(inv)]))
    assert r.result == "match"
    assert r.reasons == []
    assert r.billed_inr == D("12880.00")
    assert r.expected_inr == D("12880.00")
    assert "pod:SHP-1" in r.evidence and "meridian:SHP-1" in r.evidence


def test_within_one_rupee_is_match():
    inv = invoice([good_line()], total=D("12880.90"))
    r = reconcile_invoice(inv, SHIPMENTS, ref())
    assert r.result == "match"


def test_cancelled_invoice_not_checked():
    inv = invoice([good_line(billed_weight_kg=D("5000"))], status="Cancelled")
    r = reconcile_invoice(inv, SHIPMENTS, ref())
    assert r.result == "cancelled"
    assert r.to_output() == {"invoice_no": inv.invoice_no, "result": "cancelled"}


# ---------------------------------------------------------------- short-circuit rules


def test_shipment_unknown_zero_expected():
    inv = invoice([good_line(shipment_id="SHP-999")])
    r = reconcile_invoice(inv, SHIPMENTS, ref())
    assert r.reasons == ["shipment_unknown"]
    assert r.expected_inr == D("0.00")


def test_no_pod_zero_expected_and_skips_other_rules():
    inv = invoice([good_line(billed_weight_kg=D("2000"))])
    p = pods()
    del p["SHP-1"]
    r = reconcile_invoice(inv, SHIPMENTS, ref(pod_map=p))
    assert r.reasons == ["no_pod"]  # weight_over not checked
    assert r.expected_inr == D("0.00")


def test_duplicate_billing_on_later_invoice():
    first = invoice([good_line()], no="TIR/26-27/10100", on=date(2026, 10, 15))
    second = invoice([good_line()], no="TIR/26-27/10200", on=date(2026, 10, 25))
    history = [BillingRecord.from_invoice(first), BillingRecord.from_invoice(second)]
    assert reconcile_invoice(first, SHIPMENTS, ref(history)).result == "match"
    r = reconcile_invoice(second, SHIPMENTS, ref(history))
    assert r.reasons == ["duplicate_billing"]
    assert r.expected_inr == D("0.00")
    assert "portal:invoice/TIR/26-27/10100" in r.evidence


def test_duplicate_same_date_ordered_by_number():
    a = invoice([good_line()], no="TIR/26-27/10150", on=date(2026, 10, 20))
    b = invoice([good_line()], no="TIR/26-27/10149", on=date(2026, 10, 20))
    history = [BillingRecord.from_invoice(a), BillingRecord.from_invoice(b)]
    assert reconcile_invoice(b, SHIPMENTS, ref(history)).result == "match"
    assert reconcile_invoice(a, SHIPMENTS, ref(history)).reasons == ["duplicate_billing"]


def test_shipment_on_cancelled_invoice_is_not_duplicate():
    cancelled = invoice([good_line()], no="TIR/26-27/10100", on=date(2026, 10, 15), status="Cancelled")
    later = invoice([good_line()], no="TIR/26-27/10200")
    history = [BillingRecord.from_invoice(cancelled), BillingRecord.from_invoice(later)]
    assert reconcile_invoice(later, SHIPMENTS, ref(history)).result == "match"


def test_rule_order_unknown_beats_duplicate():
    first = invoice([good_line(shipment_id="SHP-999")], no="TIR/26-27/10100", on=date(2026, 10, 1))
    second = invoice([good_line(shipment_id="SHP-999")])
    history = [BillingRecord.from_invoice(first), BillingRecord.from_invoice(second)]
    assert reconcile_invoice(second, SHIPMENTS, ref(history)).reasons == ["shipment_unknown"]


# ---------------------------------------------------------------- value rules


def test_weight_within_two_percent_ok():
    line = good_line(billed_weight_kg=D("1020"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert "weight_over" not in r.reasons


def test_weight_over_two_percent():
    line = good_line(billed_weight_kg=D("1020.1"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert r.reasons == ["weight_over"]
    assert r.expected_inr == D("12880.00")  # expected uses Meridian's actual weight
    assert r.billed_inr > r.expected_inr


def test_rate_wrong():
    r = reconcile_invoice(invoice([good_line(rate_per_kg=D("10.50"))]), SHIPMENTS, ref())
    assert r.reasons == ["rate_wrong"]


def test_mid_month_rate_change_uses_booking_date():
    # SHP-2 booked 20 Oct -> ₹11.00 applies
    line = InvoiceLine("SHP-2", D("500"), D("11.00"), fuel_pct=D("15"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert r.result == "match"
    old_rate = InvoiceLine("SHP-2", D("500"), D("10.00"), fuel_pct=D("15"))
    assert reconcile_invoice(invoice([old_rate]), SHIPMENTS, ref()).reasons == ["rate_wrong"]


def test_surcharge_uses_booking_month():
    # SHP-3 booked in Sep (12 %) though delivered and invoiced in Oct
    ok = InvoiceLine("SHP-3", D("200"), D("10.00"), fuel_pct=D("12"))
    assert reconcile_invoice(invoice([ok]), SHIPMENTS, ref()).result == "match"
    bad = InvoiceLine("SHP-3", D("200"), D("10.00"), fuel_pct=D("15"))
    assert reconcile_invoice(invoice([bad]), SHIPMENTS, ref()).reasons == ["surcharge_wrong"]


def test_surcharge_checked_from_amount_when_pct_not_printed():
    line = good_line(fuel_pct=None, freight=D("10000.00"), fuel_amount=D("1800.00"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert r.reasons == ["surcharge_wrong"]


def test_detention_justified_when_two_days_late():
    p = pods(**{"SHP-1": Pod("SHP-1", date(2026, 10, 12), date(2026, 10, 14))})
    line = good_line(detention=D("1000"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref(pod_map=p))
    assert r.result == "match"
    assert r.expected_inr == D("14000.00")


def test_detention_unjustified_when_less_than_two_days_late():
    p = pods(**{"SHP-1": Pod("SHP-1", date(2026, 10, 12), date(2026, 10, 13))})
    line = good_line(detention=D("1000"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref(pod_map=p))
    assert r.reasons == ["detention_unjustified"]
    assert r.expected_inr == D("12880.00")


def test_unreadable_scan_flags_human_and_blocks_dispute():
    p = pods(**{"SHP-1": Pod("SHP-1", None, None, confident=False)})
    line = good_line(detention=D("5000"), billed_weight_kg=D("1100"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref(pod_map=p))
    assert r.needs_human == ["pod_unreadable:SHP-1"]
    assert "detention_unjustified" not in r.reasons
    assert propose_dispute(r) is None


def test_multiple_reasons_fire_together_in_canonical_order():
    line = good_line(billed_weight_kg=D("1100"), rate_per_kg=D("12.00"), fuel_pct=D("20"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert r.reasons == ["weight_over", "rate_wrong", "surcharge_wrong"]


# ---------------------------------------------------------------- invoice level


def test_math_error():
    r = reconcile_invoice(invoice([good_line()], total=D("13000.00")), SHIPMENTS, ref())
    assert r.reasons == ["math_error"]


def test_credit_notes_reduce_billed_and_expected():
    inv = invoice([good_line()], credits=[D("880.00")])
    r = reconcile_invoice(inv, SHIPMENTS, ref())
    assert r.result == "match"
    assert r.billed_inr == D("12000.00")
    assert r.expected_inr == D("12000.00")


def test_mismatch_without_rule_when_amounts_differ():
    # carrier mis-multiplied freight; no listed rule fires but totals differ
    line = good_line(freight=D("10500.00"))
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert r.result == "mismatch"
    assert r.reasons == []


def test_missing_reference_data_raises():
    line = InvoiceLine("SHP-1", D("1000"), D("10.00"), fuel_pct=D("15"))
    r = ref()
    r.fuel_surcharge_pct.pop("2026-10")
    with pytest.raises(MissingReferenceData):
        reconcile_invoice(invoice([line]), SHIPMENTS, r)


# ---------------------------------------------------------------- disputes


def test_dispute_proposed_above_500():
    line = good_line(billed_weight_kg=D("1100"))  # +100 kg -> +1,150 +GST
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    d = propose_dispute(r)
    assert d is not None
    assert d.reasons == ("weight_over",)
    assert d.expected_inr == D("12880.00")
    assert d.overcharge > D("500")


def test_no_dispute_at_or_below_500():
    line = good_line(billed_weight_kg=D("1035"))  # +35 kg -> +₹450.80 incl GST
    r = reconcile_invoice(invoice([line]), SHIPMENTS, ref())
    assert r.result == "mismatch"
    assert propose_dispute(r) is None


def test_no_dispute_when_undercharged():
    r = reconcile_invoice(invoice([good_line(rate_per_kg=D("8.00"))]), SHIPMENTS, ref())
    assert r.result == "mismatch"
    assert propose_dispute(r) is None


def test_no_second_dispute_when_one_exists():
    inv = invoice([good_line(billed_weight_kg=D("1100"))])
    r = reconcile_invoice(inv, SHIPMENTS, ref(disputed=[inv.invoice_no]))
    assert r.already_disputed
    assert propose_dispute(r) is None


def test_duplicate_line_dispute_amount():
    first = invoice([good_line()], no="TIR/26-27/10100", on=date(2026, 10, 15))
    second = invoice([good_line()])
    history = [BillingRecord.from_invoice(first), BillingRecord.from_invoice(second)]
    d = propose_dispute(reconcile_invoice(second, SHIPMENTS, ref(history)))
    assert d is not None and d.expected_inr == D("0.00") and d.reasons == ("duplicate_billing",)


# ---------------------------------------------------------------- missing in portal


def test_missing_in_portal_uses_delivery_month():
    inv = invoice([good_line()])
    history = [BillingRecord.from_invoice(inv)]
    # SHP-3 booked Sep but delivered Oct -> counts for October
    assert missing_in_portal(SHIPMENTS, LANE, "2026-10", history) == ["SHP-2", "SHP-3"]
    assert missing_in_portal(SHIPMENTS, LANE, "2026-09", history) == []


def test_missing_in_portal_cancelled_option():
    cancelled = replace(invoice([good_line()]), status="Cancelled")
    history = [BillingRecord.from_invoice(cancelled)]
    assert "SHP-1" not in missing_in_portal(SHIPMENTS, LANE, "2026-10", history)
    assert "SHP-1" in missing_in_portal(SHIPMENTS, LANE, "2026-10", history, ignore_cancelled=True)
