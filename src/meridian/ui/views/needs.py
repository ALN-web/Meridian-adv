"""Needs you: everything waiting on a person — OTPs, CAPTCHAs, dispute approvals, items to review."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import streamlit as st

from meridian.ui.common import REASON_LABEL, chips, get_store, header, inr
from meridian.ui.views.widgets import documents_for, invoice_header, line_table


def _otps(store) -> int:
    reqs = store.pending_human()
    if not reqs:
        return 0
    st.subheader("Passwords")
    for req in reqs:
        run = store.get_run(req["run_id"])
        who = run.task_id if run else req["run_id"]
        with st.container(border=True):
            if req["kind"] == "otp":
                if store.otp_asked_before(req["run_id"]):
                    st.warning("The portal did not accept the previous code (invalid or expired), so the agent signed in again and the portal sent a **new** code. Use that newest code — it is valid for 5 minutes.")
                with st.form(f"n-otp-{req['id']}", clear_on_submit=True, border=False):
                    c = st.columns([3, 1], vertical_alignment="bottom")
                    code = c[0].text_input(f"One-time password · {who}", type="password", max_chars=10)
                    if c[1].form_submit_button("Send", type="primary", width="stretch") and code.strip():
                        store.answer_human(req["id"], code.strip())
                        st.rerun()
            else:
                c = st.columns([3, 1], vertical_alignment="center")
                c[0].markdown(f"**CAPTCHA · {who}** · solve it in the agent's browser.")
                if c[1].button("Done", key=f"n-cap-{req['id']}", width="stretch"):
                    store.answer_human(req["id"], "")
                    st.rerun()
    return len(reqs)


def _approvals(store) -> int:
    pending = store.disputes(status="pending")
    head = st.columns([3, 1, 1], vertical_alignment="bottom")
    head[0].subheader(f"Disputes to approve · {len(pending)}")
    if not pending:
        st.markdown("<p class='muted'>Nothing to approve.</p>", unsafe_allow_html=True)
        return 0
    if len(pending) > 1:
        if head[1].button("Approve all", type="primary", width="stretch"):
            for d in pending:
                store.decide_dispute(d["id"], True)
            st.rerun()
        if head[2].button("Reject all", width="stretch"):
            for d in pending:
                store.decide_dispute(d["id"], False)
            st.rerun()
    for d in pending:
        billed, expected = Decimal(d["billed_inr"]), Decimal(d["expected_inr"])
        with st.container(border=True):
            c = st.columns([2.2, 1.2, 1.2, 1.2, 1.4], vertical_alignment="center")
            c[0].markdown(f"**{d['invoice_no']}**<br>" + chips([REASON_LABEL.get(r, r) for r in d["reasons"]], "bad"), unsafe_allow_html=True)
            for col, label, val, color in ((c[1], "Billed", billed, ""), (c[2], "Correct", expected, ""),
                                           (c[3], "Over", billed - expected, "color:#c23338")):
                col.markdown(f"<div class='lbl'>{label}</div><div class='big' style='{color}'>{inr(val)}</div>", unsafe_allow_html=True)
            with c[4]:
                a, r = st.columns(2)
                if a.button("Approve", key=f"ap-{d['id']}", type="primary", width="stretch"):
                    store.decide_dispute(d["id"], True)
                    st.rerun()
                if r.button("Reject", key=f"rj-{d['id']}", width="stretch"):
                    store.decide_dispute(d["id"], False)
                    st.rerun()
            detail = store.details(d["run_id"]).get(d["invoice_no"])
            if detail:
                with st.expander("Why"):
                    invoice_header(detail)
                    line_table(detail)
                    labels = [f"INV_{d['invoice_no']}"] + [f"POD_{l['shipment_id']}" for l in detail.get("lines", [])]
                    docs = [x for x in documents_for(store, d["run_id"], labels) if Path(x["path"]).exists()]
                    if docs:
                        cols = st.columns(min(len(docs), 4))
                        for n, doc in enumerate(docs):
                            p = Path(doc["path"])
                            cols[n % len(cols)].download_button(doc["label"], p.read_bytes(), file_name=p.name,
                                                                key=f"dl-{d['id']}-{doc['id']}", width="stretch")
    return len(pending)


def _review(store) -> int:
    """Finished runs with items a person must check (unreadable proofs, missing rates)."""
    items, seen_tasks = [], set()
    for r in store.list_runs(50):  # newest first
        if r.status not in ("completed", "needs_human") or r.task_id in seen_tasks:
            continue  # a newer run of the same task supersedes this one's open items
        seen_tasks.add(r.task_id)
        res = r.result or {}
        for inv in res.get("invoices") or []:
            for why in inv.get("needs_human") or []:
                items.append((r, inv.get("invoice_no", ""), why))
        for why in res.get("needs_human") or []:
            items.append((r, "", why))
    st.subheader(f"To check by hand · {len(items)}")
    if not items:
        st.markdown("<p class='muted'>Nothing to check.</p>", unsafe_allow_html=True)
        return 0
    for r, inv_no, why in items[:50]:
        kind, _, ref = why.partition(":")
        with st.container(border=True):
            c = st.columns([3, 1], vertical_alignment="center")
            c[0].markdown(f"**{inv_no or r.task_id}** " + chips([kind.replace("_", " ")], "wait") + chips([ref]) if ref else
                          f"**{inv_no or r.task_id}** " + chips([kind.replace("_", " ")], "wait"), unsafe_allow_html=True)
            if ref.startswith("SHP-"):
                for doc in documents_for(store, r.id, [f"POD_{ref}"]):
                    p = Path(doc["path"])
                    if p.exists():
                        c[1].download_button("Open proof", p.read_bytes(), file_name=p.name, key=f"rv-{r.id}-{doc['id']}", width="stretch")
    return len(items)


def render() -> None:
    store = get_store()
    header("Needs you", "Passwords, approvals and anything the agent wouldn't guess.")
    _otps(store)
    _approvals(store)
    _review(store)
