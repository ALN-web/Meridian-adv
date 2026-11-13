import pytest

from meridian.agent.planner import PlanError, plan_task

PUBLIC = [
    ("List every invoice on lane PUN-DEL dated in October 2026, with its total and status.",
     "list", {"lane": "PUN-DEL", "month": "2026-10"}),
    ("Reconcile invoice TIR/26-27/10196.", "one", {"invoice_no": "TIR/26-27/10196"}),
    ("Reconcile all invoices on lane PUN-BLR dated in August 2026. Do not raise disputes.",
     "lane_month", {"lane": "PUN-BLR", "month": "2026-08"}),
    ("Which shipments did Meridian deliver on lane PUN-CHN in September 2026 that appear on no invoice?",
     "missing", {"lane": "PUN-CHN", "month": "2026-09"}),
    ("Download the delivery proofs for SHP-60225, SHP-60421, SHP-60384, SHP-60468, SHP-60188, "
     "and report the promised and delivered date of each.",
     "collect", {"shipment_ids": ["SHP-60225", "SHP-60421", "SHP-60384", "SHP-60468", "SHP-60188"]}),
    ("Reconcile all invoices on lane PUN-HYD dated in October 2026, and raise disputes for overcharges after approval.",
     "dispute", {"lane": "PUN-HYD", "month": "2026-10"}),
]


@pytest.mark.parametrize("text,kind,params", PUBLIC)
def test_public_task_wording(text, kind, params):
    p = plan_task(text)
    assert p.kind == kind
    assert p.params == params
    assert p.steps


@pytest.mark.parametrize(
    "text,kind,params",
    [
        ("reconcile october invoices on pun-blr", None, None),  # no year -> error
        ("Reconcile Oct 2026 on lane pun-hyd", "lane_month", {"lane": "PUN-HYD", "month": "2026-10"}),
        ("Reconcile 2026-09 on PUN-AMD and dispute overcharges", "dispute", {"lane": "PUN-AMD", "month": "2026-09"}),
        ("Which PUN-HYD shipments delivered in Aug '26 were never invoiced?", "missing", {"lane": "PUN-HYD", "month": "2026-08"}),
    ],
)
def test_other_wordings(text, kind, params):
    if kind is None:
        with pytest.raises(PlanError):
            plan_task(text)
    else:
        p = plan_task(text)
        assert (p.kind, p.params) == (kind, params)


def test_gibberish_rejected():
    with pytest.raises(PlanError):
        plan_task("make me a sandwich")
