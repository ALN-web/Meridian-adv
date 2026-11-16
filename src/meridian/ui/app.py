"""Operator screen for the Meridian portal agent.

Run:  streamlit run src/meridian/ui/app.py

Pages: Run a task · Needs you · Results · Documents · Disputes · Monthly summary · Evaluation · System
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402
import streamlit.components.v1  # noqa: E402,F401  (st.components.v1.html)

from meridian.config import get_settings  # noqa: E402
from meridian.ui import alerts  # noqa: E402
from meridian.ui.common import CSS, get_store, human_signature  # noqa: E402
from meridian.ui.views import disputes, documents, evaluation, needs, results, run, summary, system  # noqa: E402

st.set_page_config(page_title="Meridian Portal Agent", page_icon=":material/local_shipping:", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.logo(str(Path(__file__).with_name("logo.svg")), size="large", link=get_settings().website_url)
store = get_store()

waiting = len(store.pending_human()) + len(store.disputes(status="pending"))
PAGES = {
    "run": st.Page(run.render, title="Run a task", icon=":material/play_circle:", default=True),
    "needs": st.Page(needs.render, title=f"Needs you ({waiting})" if waiting else "Needs you", icon=":material/inbox:", url_path="needs-you"),
    "results": st.Page(results.render, title="Results", icon=":material/fact_check:", url_path="results"),
    "documents": st.Page(documents.render, title="Documents", icon=":material/description:", url_path="documents"),
    "disputes": st.Page(disputes.render, title="Disputes", icon=":material/gavel:", url_path="disputes"),
    "summary": st.Page(summary.render, title="Monthly summary", icon=":material/bar_chart:", url_path="summary"),
    "evaluation": st.Page(evaluation.render, title="Evaluation", icon=":material/target:", url_path="evaluation"),
    "system": st.Page(system.render, title="System", icon=":material/tune:", url_path="system"),
}
st.session_state["pages"] = PAGES

nav = st.navigation({
    "Operate": [PAGES[k] for k in ("run", "needs", "results", "documents", "disputes")],
    "Report": [PAGES["summary"], PAGES["evaluation"]],
    "Admin": [PAGES["system"]],
}, position="top")
st.session_state.setdefault("human_sig", human_signature(store))


@st.fragment(run_every=3)
def watch_humans():
    """When something new needs a person (OTP, approval), re-render the whole app once and show a bar.

    Inputs live outside auto-refreshing areas, so a click or half-typed code is never lost.
    """
    sig = human_signature(store)
    if sig != st.session_state.human_sig:
        st.session_state.human_sig = sig
        st.rerun(scope="app")
    ph, pd_ = store.pending_human(), store.disputes(status="pending")
    h, d = len(ph), len(pd_)
    left = alerts.otp_seconds_left(ph)
    if h or d:
        parts = ([f"{h} one-time password"] if h else []) + ([f"{d} dispute approval{'s' if d > 1 else ''}"] if d else [])
        timer = "<span id='otp-countdown' class='otp-timer'></span>" if left is not None else ""
        st.markdown(f"<div class='waitbar'><span>Waiting for you: {' · '.join(parts)} {timer}</span>"
                    f"<span><a id='alert-enable' href='#' class='alert-enable'>Turn on desktop alerts</a> "
                    f"<a href='/needs-you' target='_self'>Open Needs you →</a></span></div>", unsafe_allow_html=True)
    # Sound, desktop notification, flashing tab title, OTP countdown — attention only, never an answer.
    deadline = (max(r["created"] for r in ph if r["kind"] == "otp") + alerts.OTP_VALID_S) if left is not None else None
    st.components.v1.html(alerts.script(alerts.items(ph, pd_), deadline), height=0)


watch_humans()
nav.run()
