"""Operator screen for the Meridian portal agent.

Run:  streamlit run src/meridian/ui/app.py

Pages: Run a task · Needs you · Results · Documents · Disputes · Monthly summary · Evaluation · System
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from meridian.config import get_settings  # noqa: E402
from meridian.ui.common import CSS, get_store, human_signature  # noqa: E402
from meridian.ui.views import disputes, documents, evaluation, needs, results, run, summary, system  # noqa: E402

st.set_page_config(page_title="Meridian Portal Agent", page_icon=":material/local_shipping:", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.logo(str(Path(__file__).with_name("logo.svg")), size="large",
        icon_image=str(Path(__file__).with_name("logo_dark.svg")))
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
})

with st.sidebar:
    st.session_state.human_sig = human_signature(store)

    @st.fragment(run_every=3)
    def watch_humans():
        """When something new needs a person (OTP, approval), re-render the whole app once.

        Inputs live outside auto-refreshing areas, so a click or half-typed code is never lost.
        """
        sig = human_signature(store)
        if sig != st.session_state.human_sig:
            st.session_state.human_sig = sig
            st.rerun(scope="app")
        h, d = len(store.pending_human()), len(store.disputes(status="pending"))
        if h or d:
            parts = ([f"{h} password"] if h else []) + ([f"{d} approval{'s' if d > 1 else ''}"] if d else [])
            st.warning("Waiting: " + " · ".join(parts))
            st.page_link(PAGES["needs"], label="Open Needs you", icon=":material/arrow_forward:")

    watch_humans()
    _portal = get_settings().portal_base_url.split("//")[-1].split("/")[0]
    st.markdown(f"<div class='side-foot'><b><i></i>Meridian Freight · AP</b><span>{_portal}</span></div>",
                unsafe_allow_html=True)

nav.run()
