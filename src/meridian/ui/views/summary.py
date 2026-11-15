"""Monthly summary for the logistics manager: what the carrier billed vs what it should have."""
from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from meridian.ui.common import big, get_store, header, inr

INK = "#0e0e0e"
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
    header("Monthly summary", "Overcharges by lane, and why.")
    rows = _latest_details(store)
    if not rows:
        st.info("No invoices checked yet. Run a lane-and-month task first.")
        return
    df = pd.DataFrame([{
        "invoice_no": d["invoice_no"], "month": d["invoice_date"][:7], "lane": d["lane"], "status": d["status"],
        "result": d["result"], "reasons": d["reasons"], "billed": d.get("billed_inr") or 0.0,
        "expected": d.get("expected_inr") or 0.0, "overcharge": d.get("overcharge_inr") or 0.0,
    } for d in rows])
    c = st.columns([1, 2.4, 1], vertical_alignment="bottom")
    months = sorted(df["month"].unique(), reverse=True)
    month = c[0].selectbox("Month", ["All"] + months, key="sum_month")
    lanes = c[1].multiselect("Lanes", sorted(df["lane"].unique()), default=sorted(df["lane"].unique()), key="sum_lanes")
    view = df[(df["lane"].isin(lanes)) & ((df["month"] == month) if month != "All" else True)]
    c[2].download_button("Download CSV", view.assign(reasons=view["reasons"].map(", ".join)).to_csv(index=False),
                         file_name=f"meridian-summary-{month}.csv", mime="text/csv", width="stretch", disabled=view.empty)
    if view.empty:
        st.info("Nothing for this selection.")
        return
    checked = view[view["result"] != "cancelled"]
    over = checked[checked["overcharge"] > 0]["overcharge"].sum()
    disputes = [d for d in store.disputes() if d["status"] == "confirmed" and d["invoice_no"] in set(view["invoice_no"])]
    st.write("")
    k = st.columns(4)
    big(k[0], "Invoices checked", str(len(checked)))
    big(k[1], "Billed right", f"{(checked['result'] == 'match').mean():.0%}" if len(checked) else "—")
    big(k[2], "Overcharged", inr(over))
    big(k[3], "Disputes confirmed", str(len(disputes)))

    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Overcharge by lane**")
        by_lane = checked.assign(o=checked["overcharge"].clip(lower=0)).groupby("lane")["o"].sum().sort_values(ascending=False)
        st.bar_chart(by_lane.rename("Overcharge (₹)"), color=INK, y_label="₹", x_label="", height=260)
    with right:
        st.markdown("**Why invoices were wrong**")
        reasons = Counter(REASON_LABEL.get(r, r) for rs in checked["reasons"] for r in rs)
        if reasons:
            rs = pd.Series(reasons).sort_values(ascending=True).rename("Invoices")
            st.bar_chart(rs, color=INK, horizontal=True, x_label="", y_label="", height=260)
        else:
            st.markdown("<p class='muted'>No problems found.</p>", unsafe_allow_html=True)

    st.markdown("**By lane**")
    table = checked.groupby("lane").agg(invoices=("invoice_no", "count"),
                                         wrong=("result", lambda s: int((s == "mismatch").sum())),
                                         billed=("billed", "sum"), expected=("expected", "sum"),
                                         overcharge=("overcharge", lambda s: s.clip(lower=0).sum())).reset_index()
    money = lambda t: st.column_config.NumberColumn(t, format="₹ %.2f")  # noqa: E731
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"lane": "Lane", "invoices": "Invoices", "wrong": "Wrong", "billed": money("Billed"),
                                "expected": money("Expected"), "overcharge": money("Overcharge")})

    missing = []
    for r in store.list_runs(200):
        if r.kind == "missing" and r.result and r.status == "completed":
            if r.params.get("lane") in lanes and (month == "All" or r.params.get("month") == month):
                missing += [(r.params["lane"], r.params["month"], s) for s in r.result.get("missing_in_portal") or []]
    if missing:
        st.markdown("**Delivered but never invoiced**")
        st.dataframe(pd.DataFrame(sorted(set(missing)), columns=["Lane", "Delivery month", "Shipment"]),
                     hide_index=True, width="stretch")
