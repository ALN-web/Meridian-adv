"""Monthly summary for the logistics manager: what the carrier billed vs what it should have."""
from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from meridian.ui.common import BLUE, big, get_store, inr

REASON_LABEL = {
    "shipment_unknown": "Not our shipment", "duplicate_billing": "Billed twice", "no_pod": "No delivery proof",
    "weight_over": "Weight over +2%", "rate_wrong": "Wrong rate", "surcharge_wrong": "Wrong fuel %",
    "detention_unjustified": "Detention not due", "math_error": "Totals don't add up",
}


def _latest_details(store) -> list[dict]:
    """Newest explanation per invoice across all runs (a re-run supersedes older ones)."""
    seen: dict[str, dict] = {}
    for run in reversed(store.list_runs(500)):  # oldest first, newer overwrite
        for no, d in store.details(run.id).items():
            seen[no] = d
    return list(seen.values())


def render() -> None:
    store = get_store()
    st.title("Monthly summary")
    st.caption("For the logistics manager. Built from every invoice the agent has checked (newest check wins). "
               "Months are invoice-date months.")
    rows = _latest_details(store)
    if not rows:
        st.info("No invoices checked yet. Run a lane-and-month task first.")
        return
    df = pd.DataFrame([{
        "invoice_no": d["invoice_no"], "month": d["invoice_date"][:7], "lane": d["lane"], "status": d["status"],
        "result": d["result"], "reasons": d["reasons"], "billed": d.get("billed_inr") or 0.0,
        "expected": d.get("expected_inr") or 0.0, "overcharge": d.get("overcharge_inr") or 0.0,
    } for d in rows])
    c = st.columns([1, 2])
    months = sorted(df["month"].unique(), reverse=True)
    month = c[0].selectbox("Month", ["All"] + months, key="sum_month")
    lanes = c[1].multiselect("Lanes", sorted(df["lane"].unique()), default=sorted(df["lane"].unique()), key="sum_lanes")
    view = df[(df["lane"].isin(lanes)) & ((df["month"] == month) if month != "All" else True)]
    if view.empty:
        st.info("Nothing for this selection.")
        return
    checked = view[view["result"] != "cancelled"]
    over = checked[checked["overcharge"] > 0]["overcharge"].sum()
    disputes = [d for d in store.disputes() if d["status"] == "confirmed" and d["invoice_no"] in set(view["invoice_no"])]
    k = st.columns(5)
    big(k[0], "Invoices checked", str(len(checked)), f"{(view['result'] == 'cancelled').sum()} cancelled")
    big(k[1], "Billed correctly", f"{(checked['result'] == 'match').mean():.0%}" if len(checked) else "—",
        f"{(checked['result'] == 'match').sum()} of {len(checked)}")
    big(k[2], "Billed (net)", inr(checked["billed"].sum()))
    big(k[3], "Overcharged", inr(over), "billed above expected")
    big(k[4], "Disputes confirmed", str(len(disputes)))

    left, right = st.columns(2)
    with left:
        st.subheader("Overcharge by lane")
        by_lane = checked.assign(o=checked["overcharge"].clip(lower=0)).groupby("lane")["o"].sum().sort_values(ascending=False)
        st.bar_chart(by_lane.rename("Overcharge (₹)"), color=BLUE, y_label="₹", x_label="lane", horizontal=False)
    with right:
        st.subheader("Why invoices were wrong")
        reasons = Counter(REASON_LABEL.get(r, r) for rs in checked["reasons"] for r in rs)
        if reasons:
            rs = pd.Series(reasons).sort_values(ascending=True).rename("Invoices")
            st.bar_chart(rs, color=BLUE, horizontal=True, x_label="invoices", y_label="")
        else:
            st.caption("No problems found.")

    st.subheader("By lane")
    table = checked.groupby("lane").agg(invoices=("invoice_no", "count"),
                                         wrong=("result", lambda s: int((s == "mismatch").sum())),
                                         billed=("billed", "sum"), expected=("expected", "sum"),
                                         overcharge=("overcharge", lambda s: s.clip(lower=0).sum())).reset_index()
    money = st.column_config.NumberColumn(format="₹ %.2f")
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"billed": money, "expected": money, "overcharge": money})

    missing = []
    for r in store.list_runs(200):
        if r.kind == "missing" and r.result and r.status == "completed":
            if r.params.get("lane") in lanes and (month == "All" or r.params.get("month") == month):
                missing += [(r.params["lane"], r.params["month"], s) for s in r.result.get("missing_in_portal") or []]
    st.subheader("Delivered but never invoiced")
    if missing:
        st.dataframe(pd.DataFrame(sorted(set(missing)), columns=["lane", "delivery month", "shipment"]),
                     hide_index=True, width="stretch")
    else:
        st.caption("No missing-invoice checks for this selection yet.")

    st.download_button("⬇ Download invoice list (CSV)",
                       view.assign(reasons=view["reasons"].map(", ".join)).to_csv(index=False),
                       file_name=f"meridian-summary-{month}.csv", mime="text/csv")
