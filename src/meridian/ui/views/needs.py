"""Needs you: everything waiting on a person — OTPs, CAPTCHAs, dispute approvals, items to review."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import streamlit as st

from meridian.ui.common import chips, get_store, hhmm, inr
from meridian.ui.views.widgets import documents_for, invoice_header, line_table


def _otps(store) -> int:
    reqs = store.pending_human()
    if not reqs:
        return 0
    st.subheader(f"🔐 One-time passwords and CAPTCHAs ({len(reqs)})")
    for req in reqs:
        run = store.get_run(req["run_id"])
        with st.container(border=True):
            st.markdown(f"**{req['kind'].upper()}** for {run.task_id if run else req['run_id']} — asked {hhmm(req['created'])}")
            if req["kind"] == "otp":
                st.caption("Open the operator inbox yourself and type the code. The agent never opens the inbox.")
                with st.form(f"n-otp-{req['id']}", clear_on_submit=True):
                    code = st.text_input("OTP", type="password", max_chars=10)
                    if st.form_submit_button("Send code", type="primary") and code.strip():
                        store.answer_human(req["id"], code.strip())
                        st.rerun()
            else:
                st.caption("Solve the CAPTCHA in the agent's browser window, then press Done.")
                if st.button("Done", key=f"n-cap-{req['id']}"):
                    store.answer_human(req["id"], "")
                    st.rerun()
    return len(reqs)


def _approvals(store) -> int:
    pending = store.disputes(status="pending")
    st.subheader(f"⚖️ Disputes to approve ({len(pending)})")
    st.caption("Raising a dispute is the only thing the agent writes to the portal. After you approve, it checks the "
               "portal's dispute list, submits once, then checks the list again to confirm it was saved.")
    if not pending:
        st.success("Nothing waiting for approval.")
        return 0
    if len(pending) > 1:
        c = st.columns([1, 1, 4])
        if c[0].button("Approve all", type="primary"):
            for d in pending:
                store.decide_dispute(d["id"], True)
            st.rerun()
        if c[1].button("Reject all"):
            for d in pending:
                store.decide_dispute(d["id"], False)
            st.rerun()
    for d in pending:
        billed, expected = Decimal(d["billed_inr"]), Decimal(d["expected_inr"])
        run = store.get_run(d["run_id"])
        with st.container(border=True):
            c = st.columns([2.4, 1.3, 1.3, 1.3, 1.3])
            c[0].markdown(f"**{d['invoice_no']}** <span class='muted'>· {run.task_id if run else ''}</span><br>"
                          + chips(d["reasons"], "bad"), unsafe_allow_html=True)
            for col, label, val in ((c[1], "Billed", billed), (c[2], "Correct amount", expected), (c[3], "Overcharge", billed - expected)):
                col.markdown(f"<div class='lbl'>{label}</div><div class='big'>{inr(val)}</div>", unsafe_allow_html=True)
            with c[4]:
                if st.button("✅ Approve", key=f"ap-{d['id']}", type="primary", width="stretch"):
                    store.decide_dispute(d["id"], True)
                    st.rerun()
                if st.button("✖ Reject", key=f"rj-{d['id']}", width="stretch"):
                    store.decide_dispute(d["id"], False)
                    st.rerun()
            detail = store.details(d["run_id"]).get(d["invoice_no"])
            with st.expander("Why — line by line, and the documents"):
                if detail:
                    invoice_header(detail)
                    line_table(detail)
                    labels = [f"INV_{d['invoice_no']}"] + [f"POD_{l['shipment_id']}" for l in detail.get("lines", [])]
                    docs = documents_for(store, d["run_id"], labels)
                    for doc in docs:
                        p = Path(doc["path"])
                        if p.exists():
                            st.download_button(f"⬇ {doc['label']}", p.read_bytes(), file_name=p.name, key=f"dl-{d['id']}-{doc['id']}")
                if d["evidence"]:
                    st.caption("Evidence: " + " · ".join(d["evidence"]))
    return len(pending)


def _review(store) -> int:
    """Finished runs with items a person must check (unreadable proofs, missing rates)."""
    items = []
    for r in store.list_runs(50):
        res = r.result or {}
        for inv in res.get("invoices") or []:
            for why in inv.get("needs_human") or []:
                items.append((r, inv.get("invoice_no", ""), why))
        for why in res.get("needs_human") or []:
            items.append((r, "", why))
    st.subheader(f"🔎 To review ({len(items)})")
    if not items:
        st.success("Nothing to review.")
        return 0
    st.caption("The agent stops instead of guessing. Check these by hand; no dispute was raised for them.")
    for r, inv_no, why in items[:50]:
        kind, _, ref = why.partition(":")
        with st.container(border=True):
            st.markdown(f"**{inv_no or r.task_id}** — {kind.replace('_', ' ')} <span class='chip'>{ref}</span>"
                        f" <span class='muted'>· run {r.task_id} {hhmm(r.created)}</span>", unsafe_allow_html=True)
            if ref.startswith("SHP-"):
                for doc in documents_for(store, r.id, [f"POD_{ref}"]):
                    p = Path(doc["path"])
                    if p.exists():
                        st.download_button(f"⬇ Open {doc['label']}", p.read_bytes(), file_name=p.name,
                                           key=f"rv-{r.id}-{doc['id']}")
    return len(items)


def render() -> None:
    store = get_store()
    st.title("Needs you")
    n = _otps(store)
    n += _approvals(store)
    st.divider()
    _review(store)
    if n == 0:
        st.caption("This page updates when the agent asks for something.")
