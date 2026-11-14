"""Widgets used on more than one page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from meridian.store import Store
from meridian.ui.common import chips, inr

LINE_COLS = {
    "shipment_id": "Shipment",
    "booked_on": "Booked",
    "billed_weight_kg": "Billed kg",
    "actual_weight_kg": "Actual kg",
    "weight_limit_kg": "Limit (+2%)",
    "billed_rate": "Billed rate",
    "card_rate": "Card rate",
    "billed_fuel_pct": "Billed fuel %",
    "month_fuel_pct": "Month fuel %",
    "detention": "Detention",
    "promised_on": "Promised",
    "delivered_on": "Delivered",
    "days_late": "Days late",
    "billed_inr": "Billed",
    "expected_inr": "Expected",
    "reasons": "Why",
}
# which columns to highlight for each reason
REASON_COLS = {
    "weight_over": ["Billed kg", "Actual kg", "Limit (+2%)"],
    "rate_wrong": ["Billed rate", "Card rate"],
    "surcharge_wrong": ["Billed fuel %", "Month fuel %"],
    "detention_unjustified": ["Detention", "Promised", "Delivered", "Days late"],
    "shipment_unknown": ["Shipment"],
    "duplicate_billing": ["Shipment"],
    "no_pod": ["Promised", "Delivered"],
}


def line_table(detail: dict) -> None:
    rows = detail.get("lines") or []
    if not rows:
        st.caption("No line details recorded for this invoice.")
        return
    df = pd.DataFrame(rows)
    df["reasons"] = df["reasons"].map(lambda r: ", ".join(r) if r else "ok")
    df = df[[c for c in LINE_COLS if c in df]].rename(columns=LINE_COLS)

    def hi(row):
        bad = set()
        for reason in str(row["Why"]).split(", "):
            bad.update(REASON_COLS.get(reason, []))
        return ["background-color: rgba(208,59,59,.16)" if c in bad or (c == "Why" and row["Why"] != "ok") else ""
                for c in row.index]

    money = st.column_config.NumberColumn(format="₹ %.2f")
    kg = st.column_config.NumberColumn(format="%.1f")
    pct = st.column_config.NumberColumn(format="%.1f%%")
    rate = st.column_config.NumberColumn(format="%.2f")
    st.dataframe(df.style.apply(hi, axis=1), hide_index=True, width="stretch",
                 column_config={"Billed": money, "Expected": money, "Detention": money,
                                "Billed kg": kg, "Actual kg": kg, "Limit (+2%)": kg,
                                "Billed rate": rate, "Card rate": rate,
                                "Billed fuel %": pct, "Month fuel %": pct,
                                "Days late": st.column_config.NumberColumn(format="%d")})


def invoice_header(detail: dict) -> None:
    c = st.columns(5)
    c[0].markdown(f"<div class='lbl'>Printed total</div><div class='big'>{inr(detail.get('printed_total'))}</div>"
                  f"<div class='lbl'>lines + 12% GST: {inr(detail.get('lines_plus_gst'))}</div>", unsafe_allow_html=True)
    credits = detail.get("credit_notes") or []
    c[1].markdown(f"<div class='lbl'>Credit notes</div><div class='big'>{inr(sum(credits)) if credits else '—'}</div>"
                  f"<div class='lbl'>{len(credits)} note(s)</div>", unsafe_allow_html=True)
    c[2].markdown(f"<div class='lbl'>Billed</div><div class='big'>{inr(detail.get('billed_inr'))}</div>", unsafe_allow_html=True)
    c[3].markdown(f"<div class='lbl'>Expected</div><div class='big'>{inr(detail.get('expected_inr'))}</div>", unsafe_allow_html=True)
    c[4].markdown(f"<div class='lbl'>Difference</div><div class='big'>{inr(detail.get('overcharge_inr'))}</div>"
                  f"<div class='lbl'>{'dispute already on portal' if detail.get('already_disputed') else ''}</div>",
                  unsafe_allow_html=True)
    reasons = detail.get("reasons") or []
    st.markdown(chips(reasons, "bad") if reasons else chips(["no rule fired"], "ok"), unsafe_allow_html=True)


def documents_for(store: Store, run_id: str, labels: list[str]) -> list[dict]:
    want = set(labels)
    return [d for d in store.documents(run_id) if d["label"] in want]
