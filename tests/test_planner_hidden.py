"""Hidden tasks (30 % of the score) are 'similar but not identical' to the public ones.

Each case is a rewording a grader could plausibly write. The planner must pick the same task kind
and parameters as for the public wording, and must never turn a "don't dispute" task into a write.
"""
from datetime import date

import pytest

from meridian.agent.planner import PlanError, plan_task

D = {"lane": "PUN-DEL", "month": "2026-10"}
B8 = {"lane": "PUN-BLR", "month": "2026-08"}
H10 = {"lane": "PUN-HYD", "month": "2026-10"}

CASES = [
    # list
    ("Show me all invoices for lane PUN-DEL in October 2026 with totals and status.", "list", D),
    ("List the invoices on pun-del for Oct 2026.", "list", D),
    ("List every invoice on lane PUN-DEL dated in Oct-2026.", "list", D),
    ("List every invoice on the Pune to Delhi lane dated October 2026.", "list", D),
    ("List all PUN–DEL invoices (October 2026).", "list", D),
    ("List every invoice on lane PUN DEL for 2026-10.", "list", D),
    ("List every invoice on lane PUN-DEL for 10/2026.", "list", D),
    ("What invoices are there on lane PUN-DEL for October 2026? Give total and status.", "list", D),
    # one invoice
    ("Check invoice TIR/26-27/10196.", "one", {"invoice_no": "TIR/26-27/10196"}),
    ("Audit invoice tir/26-27/10196 and tell me if it is billed right.", "one", {"invoice_no": "TIR/26-27/10196"}),
    ("Reconcile invoice TIR/26-27/10196 on lane PUN-BLR.", "one", {"invoice_no": "TIR/26-27/10196"}),
    ("Is invoice TIR/26-27/10157 correct?", "one", {"invoice_no": "TIR/26-27/10157"}),
    # lane + month, read only
    ("Reconcile every invoice on lane PUN-BLR for August 2026; don't raise any disputes.", "lane_month", B8),
    ("Check all August 2026 invoices on the Pune–Bengaluru lane. No disputes.", "lane_month", B8),
    ("Reconcile all invoices on lane PUN-BLR dated in Aug '26. Do not file disputes.", "lane_month", B8),
    ("Reconcile all invoices on lane PUN-BLR dated in August 2026 without raising disputes.", "lane_month", B8),
    ("Audit the PUN-BLR invoices for August 2026 but do not dispute anything.", "lane_month", B8),
    ("Reconcile all invoices on lane PUN-BLR dated in August 2026.", "lane_month", B8),
    # missing in portal
    ("Which shipments delivered on PUN-CHN in September 2026 were never invoiced?", "missing",
     {"lane": "PUN-CHN", "month": "2026-09"}),
    ("Find Meridian shipments on the Pune–Chennai lane delivered in Sept 2026 that TransIndus never billed.", "missing",
     {"lane": "PUN-CHN", "month": "2026-09"}),
    ("List the shipments on lane PUN-HYD delivered in August 2026 that are missing from every invoice.", "missing",
     {"lane": "PUN-HYD", "month": "2026-08"}),
    # collect proofs
    ("Fetch the proof of delivery for SHP-60225 and SHP-60421 and give promised and delivered dates.", "collect",
     {"shipment_ids": ["SHP-60225", "SHP-60421"]}),
    ("Get PODs for shp-60082, shp-60037.", "collect", {"shipment_ids": ["SHP-60082", "SHP-60037"]}),
    ("What were the promised and delivered dates for shipments SHP-60282 and SHP-60366?", "collect",
     {"shipment_ids": ["SHP-60282", "SHP-60366"]}),
    # disputes (write) — only when clearly asked
    ("Reconcile all invoices on lane PUN-HYD dated in October 2026 and dispute any overcharges once approved.",
     "dispute", H10),
    ("Reconcile PUN-HYD for October 2026, then file disputes for the overcharged invoices after my approval.",
     "dispute", H10),
    ("Check the Pune–Hyderabad invoices for Oct 2026 and raise a dispute for each overcharge (after approval).",
     "dispute", H10),
]


@pytest.mark.parametrize("text,kind,params", CASES)
def test_reworded_task(text, kind, params):
    p = plan_task(text)
    assert (p.kind, p.params) == (kind, params)


@pytest.mark.parametrize("text", [
    "Reconcile all invoices on lane PUN-HYD dated in October 2026. Do not raise disputes.",
    "Reconcile all invoices on lane PUN-HYD in October 2026 but don't file any disputes.",
    "Reconcile all invoices on lane PUN-HYD in October 2026, no need to raise disputes.",
    "Reconcile all invoices on lane PUN-HYD in October 2026 and tell me which ones we could dispute.",
    "Reconcile all invoices on lane PUN-HYD in October 2026. Never raise a dispute.",
])
def test_never_a_write_unless_asked(text):
    assert plan_task(text).kind == "lane_month"


def test_month_without_a_year_is_the_latest_one_not_in_the_future():
    assert plan_task("Reconcile all invoices on lane PUN-BLR for August.", today=date(2026, 11, 19)).params["month"] == "2026-08"
    assert plan_task("Reconcile all invoices on lane PUN-BLR for December.", today=date(2026, 11, 19)).params["month"] == "2025-12"


def test_still_refuses_what_it_cannot_do():
    with pytest.raises(PlanError):
        plan_task("Reconcile everything.")
    with pytest.raises(PlanError):
        plan_task("List invoices on lane PUN-XYZ for October 2026.")
