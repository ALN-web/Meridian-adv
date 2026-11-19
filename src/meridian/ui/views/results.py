"""Results: the graded result plus a drill-down into each invoice's lines and documents."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from meridian.ui.common import (RESULT_LABEL, badge, big, chips, get_store, header, humans_text, money_table,
                                 pick_run, reasons_text)
from meridian.ui.views.widgets import documents_for, invoice_header, line_table, trace_view

ROW_BG = {"match": "rgba(47,191,113,.10)", "mismatch": "rgba(229,72,77,.08)", "cancelled": "rgba(127,127,127,.08)"}


def _invoices(store, run, r) -> None:
    invs = r.get("invoices") or []
    if run.kind == "missing":
        miss = r.get("missing_in_portal") or []
        st.markdown("**Delivered but never invoiced**")
        st.markdown(chips(miss, "bad") if miss else "<p class='muted'>None. Every delivered shipment was invoiced.</p>",
                    unsafe_allow_html=True)
    if r.get("pods"):
        st.markdown("**Delivery proofs**")
        st.dataframe(pd.DataFrame(r["pods"]), hide_index=True, width="stretch",
                     column_config={"shipment_id": "Shipment", "promised_on": "Promised", "delivered_on": "Delivered"})
    if not invs:
        if run.kind not in ("missing", "collect"):
            st.markdown("<p class='muted'>No invoices in this result.</p>", unsafe_allow_html=True)
        return
    df = pd.DataFrame(invs)
    if "result" in df:
        counts = df["result"].value_counts().to_dict()
        kind = {"match": "ok", "mismatch": "bad"}
        st.markdown("".join(chips([f"{v} {RESULT_LABEL.get(k, k).lower()}"], kind.get(k, "")) for k, v in counts.items()),
                    unsafe_allow_html=True)
    show = df.drop(columns=[c for c in ("evidence", "needs_human", "existing_dispute") if c in df])
    if "reasons" in show:
        show["reasons"] = show["reasons"].map(reasons_text)
    if {"billed_inr", "expected_inr"} <= set(show.columns):
        # what a manager reads first: how much over, biggest first
        show.insert(show.columns.get_loc("expected_inr") + 1, "over_inr",
                    (show["billed_inr"] - show["expected_inr"]).round(2).where(show["result"] != "cancelled"))
        show = show.sort_values(["over_inr", "invoice_no"], ascending=[False, True], na_position="last")
    results = show["result"].copy() if "result" in show else None
    if results is not None:
        show["result"] = show["result"].map(lambda x: RESULT_LABEL.get(x, x))

    def tint(sty):
        if results is None:
            return sty
        return sty.apply(lambda row: [f"background-color: {ROW_BG.get(results[row.name], '')}"] * len(row), axis=1)

    money_table(show, ["billed_inr", "expected_inr", "over_inr", "total_inr"], style=tint, hide_index=True,
                width="stretch",
                column_config={"invoice_no": "Invoice", "result": "Result", "reasons": "Why", "status": "Status",
                               "billed_inr": "Billed", "expected_inr": "Correct amount", "over_inr": "Over by",
                               "total_inr": "Total"})
    if run.kind == "dispute":
        st.markdown("**Disputes confirmed on the portal**")
        if r.get("disputes"):
            st.dataframe(pd.DataFrame(r["disputes"]), hide_index=True, width="stretch")
        else:
            st.markdown("<p class='muted'>None raised in this run.</p>", unsafe_allow_html=True)


def _drill(store, run, r) -> None:
    invs = r.get("invoices") or []
    details = store.details(run.id)
    nos = [i["invoice_no"] for i in invs if i["invoice_no"] in details]
    if not nos:
        st.markdown("<p class='muted'>No line detail for this run.</p>", unsafe_allow_html=True)
        return
    no = st.selectbox("Invoice", nos, key=f"drill-{run.id}")
    d = details[no]
    invoice_header(d)
    st.write("")
    line_table(d)
    docs = [x for x in documents_for(store, run.id, [f"INV_{no}"] + [f"POD_{l['shipment_id']}" for l in d.get("lines", [])])
            if Path(x["path"]).exists()]
    if docs:
        cols = st.columns(min(len(docs), 5))
        for n, doc in enumerate(docs):
            p = Path(doc["path"])
            cols[n % len(cols)].download_button(doc["label"], p.read_bytes(), file_name=p.name, key=f"rd-{doc['id']}", width="stretch")


def render() -> None:
    store = get_store()
    header("Results")
    run = pick_run(store, "res_run", finished_only=True, label="Run")
    if run is None:
        st.info("No finished runs yet.")
        return
    r = run.result or {}
    st.markdown(f"### {run.task_text}")
    k = st.columns(5)
    k[0].markdown(f"<div class='kpi'><div class='lbl'>Status</div><div style='padding-top:6px'>{badge(run.status)}</div></div>",
                  unsafe_allow_html=True)
    big(k[1], "Steps", str(r.get("steps", 0)))
    big(k[2], "Retries", str(r.get("retries", 0)))
    big(k[3], "Time", f"{r.get('duration_s', 0)} s")
    big(k[4], "Person asked for", humans_text(r.get("human_steps")))
    if r.get("error"):
        st.error(r["error"])
    st.write("")

    t1, t2, t3, t4 = st.tabs(["Overview", "Invoice detail", "Trace", "Raw result"])
    with t1:
        _invoices(store, run, r)
    with t2:
        _drill(store, run, r)
    with t3:
        trace_view(r, f"tr-{run.id}")
    with t4:
        st.json(r)
        st.download_button("Download JSON", json.dumps(r, indent=2), file_name=f"{r.get('task_id', 'result')}.json",
                           mime="application/json")
