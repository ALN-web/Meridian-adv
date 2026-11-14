"""Results: the graded result plus a drill-down into each invoice's lines and documents."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from meridian.ui.common import badge, big, get_store, inr, pick_run
from meridian.ui.views.widgets import documents_for, invoice_header, line_table, trace_view

ROW_BG = {"match": "rgba(12,163,12,.12)", "mismatch": "rgba(208,59,59,.12)", "cancelled": "rgba(127,127,127,.14)"}


def render() -> None:
    store = get_store()
    st.title("Results")
    run = pick_run(store, "res_run", finished_only=True, label="Finished run")
    if run is None:
        st.info("No finished runs yet.")
        return
    r = run.result or {}
    st.markdown(f"**{run.task_text}**", unsafe_allow_html=True)
    k = st.columns(6)
    k[0].markdown(f"<div class='lbl'>Status</div>{badge(run.status)}", unsafe_allow_html=True)
    big(k[1], "Steps", str(r.get("steps", 0)))
    big(k[2], "Retries", str(r.get("retries", 0)))
    big(k[3], "Duration", f"{r.get('duration_s', 0)} s")
    big(k[4], "Cost", inr(r.get("cost_inr", 0)))
    big(k[5], "Human steps", ", ".join(r.get("human_steps") or []) or "none")
    if r.get("error"):
        st.error(r["error"])

    invs = r.get("invoices") or []
    if invs:
        df = pd.DataFrame(invs)
        if "result" in df:
            counts = df["result"].value_counts().to_dict()
            st.markdown(" ".join(f"<span class='chip'>{k}: {v}</span>" for k, v in counts.items()), unsafe_allow_html=True)
        show = df.drop(columns=[c for c in ("evidence", "needs_human", "existing_dispute") if c in df])
        if "reasons" in show:
            show["reasons"] = show["reasons"].map(lambda x: ", ".join(x) if isinstance(x, list) else "")
        money = st.column_config.NumberColumn(format="₹ %.2f")
        styled = show.style.apply(lambda row: [f"background-color: {ROW_BG.get(row.get('result', ''), '')}"] * len(row), axis=1)
        st.dataframe(styled, hide_index=True, width="stretch",
                     column_config={"billed_inr": money, "expected_inr": money, "total_inr": money})

        details = store.details(run.id)
        if details:
            st.subheader("Invoice drill-down")
            nos = [i["invoice_no"] for i in invs if i["invoice_no"] in details]
            no = st.selectbox("Invoice", nos, key=f"drill-{run.id}")
            d = details[no]
            invoice_header(d)
            line_table(d)
            src = next((i for i in invs if i["invoice_no"] == no), {})
            if src.get("evidence"):
                st.caption("Evidence: " + " · ".join(src["evidence"]))
            docs = documents_for(store, run.id, [f"INV_{no}"] + [f"POD_{l['shipment_id']}" for l in d.get("lines", [])])
            if docs:
                cols = st.columns(min(len(docs), 5))
                for n, doc in enumerate(docs):
                    p = Path(doc["path"])
                    if p.exists():
                        cols[n % len(cols)].download_button(f"⬇ {doc['label']}", p.read_bytes(), file_name=p.name,
                                                            key=f"rd-{doc['id']}")

    if run.kind == "missing":
        st.subheader("Delivered but never invoiced")
        miss = r.get("missing_in_portal") or []
        st.markdown(" ".join(f"<span class='chip bad'>{m}</span>" for m in miss) or "None — every delivered shipment was invoiced.",
                    unsafe_allow_html=True)
    if r.get("pods"):
        st.subheader("Delivery proofs")
        st.dataframe(pd.DataFrame(r["pods"]), hide_index=True, width="stretch")
    if r.get("needs_human"):
        st.warning("Needs a person: " + ", ".join(r["needs_human"]))
    if run.kind == "dispute":
        st.subheader("Disputes raised and confirmed in the portal list")
        if r.get("disputes"):
            st.dataframe(pd.DataFrame(r["disputes"]), hide_index=True, width="stretch")
        else:
            st.caption("None raised in this run.")

    st.subheader("Trace")
    trace_view(r, f"tr-{run.id}")

    with st.expander("Task result JSON (graded format)"):
        st.json(r)
    st.download_button("⬇ Download result JSON", json.dumps(r, indent=2), file_name=f"{r.get('task_id', 'result')}.json",
                       mime="application/json")
