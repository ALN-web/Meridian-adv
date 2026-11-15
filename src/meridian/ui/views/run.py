"""Run a task: plain-English task -> plan, live progress, OTP box, step log, stop/resume."""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from meridian.agent.demo import sample_tasks
from meridian.agent.modes import portal_reachable, start_runner
from meridian.agent.planner import PlanError, plan_task
from meridian.ui.common import badge, get_store, header, is_active, plan_of, public_tasks, run_label

MODE_LABEL = {"demo": "Demo", "fake": "Fake portal", "live": "Real portal"}
PROBLEM_OUTCOMES = {"failed", "needs_human", "session_expired", "not_found", "unreadable", "submit_error",
                    "not_confirmed", "rejected", "cancelled", "waiting_for_human", "otp_requested", "skipped"}


def _new_task(store) -> None:
    with st.container(border=True):
        st.session_state.setdefault("task_text", "")
        pub = public_tasks()
        options = ["Choose an example…"] + [f"{t['task_id']} · {t['task']}" for t in pub] + [f"Demo · {t}" for t in sample_tasks()]
        pick = st.selectbox("Example", options, key="example", label_visibility="collapsed")
        if pick != options[0] and st.session_state.get("_last_pick") != pick:
            st.session_state.task_text = pick.split(" · ", 1)[1]
            st.session_state._last_pick = pick
        text = st.text_area("Task", key="task_text", height=76, label_visibility="collapsed",
                            placeholder="e.g. Reconcile all invoices on lane PUN-HYD dated in October 2026.")

        plan, problem = None, ""
        if text.strip():
            try:
                plan = plan_task(text)
            except PlanError as exc:
                problem = str(exc)

        c = st.columns([2.2, 1.2, 1, 1.1], vertical_alignment="center")
        mode = c[0].segmented_control("Portal", list(MODE_LABEL), format_func=MODE_LABEL.get, default="demo",
                                      key="mode", label_visibility="collapsed") or "demo"
        show_browser = c[1].toggle("Show browser", value=False, disabled=mode == "demo", key="show_browser")
        reachable, where = portal_reachable(mode) if mode == "fake" else (True, "")
        if plan:
            c[2].markdown(f"<span class='pill p-grey'>{plan.kind.replace('_', ' ')} · {len(plan.steps)} steps</span>",
                          unsafe_allow_html=True)
        if c[3].button("Run task", type="primary", disabled=plan is None or not reachable, width="stretch"):
            tid = next((t["task_id"] for t in pub if t["task"] == text.strip()), f"UI-{int(time.time()) % 100000:05d}")
            run_id = store.create_run(tid, text.strip(), plan.kind, plan.params, plan.steps, mode)
            start_runner(mode, store, run_id, plan, tid, headless=not show_browser)
            st.session_state.run_id = run_id
            st.rerun()
        if problem:
            st.error(problem)
        elif not reachable:
            st.error(where)
        elif mode == "live":
            st.caption("Real portal: selectors are unconfirmed until recon succeeds.")


def _human_inputs(store, run_id: str) -> None:
    """Rendered outside auto-refresh so typing is never interrupted."""
    for req in store.pending_human(run_id):
        with st.container(border=True):
            if req["kind"] == "otp":
                with st.form(f"otp-{req['id']}", clear_on_submit=True, border=False):
                    c = st.columns([3, 1], vertical_alignment="bottom")
                    code = c[0].text_input("One-time password from the operator inbox", type="password", max_chars=10)
                    if c[1].form_submit_button("Send", type="primary", width="stretch") and code.strip():
                        store.answer_human(req["id"], code.strip())
                        st.rerun()
            elif req["kind"] == "captcha":
                c = st.columns([3, 1], vertical_alignment="center")
                c[0].markdown("**CAPTCHA** · solve it in the agent's browser window.")
                if c[1].button("Done", key=f"cap-{req['id']}", width="stretch"):
                    store.answer_human(req["id"], "")
                    st.rerun()


def _controls(store, run) -> None:
    c = st.columns([1, 1, 1, 3], vertical_alignment="center")
    if is_active(run):
        if c[0].button("Stop", width="stretch", help="Stops after this step. Progress is kept."):
            store.request_cancel(run.id)
            st.toast("Stopping after the current step…")
    elif run.status in ("failed", "cancelled", "needs_human"):
        if c[0].button("Resume", width="stretch", help="Finished invoices are not redone."):
            reachable, where = portal_reachable(run.mode)
            if not reachable:
                st.error(where)
            else:
                store.prepare_resume(run.id)
                start_runner(run.mode, store, run.id, plan_of(run), run.task_id,
                             headless=not st.session_state.get("show_browser", False))
                st.rerun()
    if run.result and c[1].button("Results", width="stretch"):
        st.switch_page(st.session_state["pages"]["results"])
    if run.result and run.result.get("trace_url"):
        c[2].link_button("Trace", run.result["trace_url"], width="stretch")


def render() -> None:
    store = get_store()
    header("Run a task", "Type it in plain English, or pick one of the public tasks.")
    _new_task(store)

    runs = store.list_runs(100)
    if not runs:
        return
    st.write("")
    ids = [r.id for r in runs]
    cur = st.session_state.get("run_id")
    run_id = st.selectbox("Run", ids, index=ids.index(cur) if cur in ids else 0,
                          format_func=lambda i: run_label(next(r for r in runs if r.id == i)), key="run_select")
    st.session_state.run_id = run_id
    run = store.get_run(run_id)

    st.markdown(f"### {run.task_text}")
    _controls(store, run)
    _human_inputs(store, run_id)

    st.session_state[f"status-{run_id}"] = run.status

    @st.fragment(run_every=2)
    def live():
        r = store.get_run(run_id)
        if r.status != st.session_state.get(f"status-{run_id}"):
            st.session_state[f"status-{run_id}"] = r.status
            st.rerun(scope="app")  # refresh Stop/Resume buttons and results link
        steps = store.steps(run_id)
        total = max(len(r.plan), 1)
        done_upto = total if r.status == "completed" else r.phase
        head = st.columns([1, 3], vertical_alignment="center")
        head[0].markdown(badge(r.status), unsafe_allow_html=True)
        head[1].progress(min(done_upto / total, 1.0), text=f"Step {min(r.phase + 1, total)} of {total} · {MODE_LABEL.get(r.mode, r.mode)}")
        if r.error and r.status in ("failed", "cancelled", "needs_human"):
            st.error(r.error)

        left, right = st.columns([2, 3], gap="large")
        with left:
            st.markdown("**Plan**")
            rows = []
            for i, s in enumerate(r.plan):
                if r.status == "completed" or i < r.phase:
                    cls, mark = "done", "✓"
                elif i == r.phase and st.session_state.get(f"status-{run_id}") in ("running", "waiting_for_human", "queued"):
                    cls, mark = "now", str(i + 1)
                else:
                    cls, mark = "", str(i + 1)
                rows.append(f"<div class='plan-row {cls}'><b>{mark}</b>{s}</div>")
            st.markdown("".join(rows), unsafe_allow_html=True)
        with right:
            c = st.columns([3, 2], vertical_alignment="center")
            retries = sum(s["retries"] or 0 for s in steps)
            c[0].markdown(f"**Log** <span class='muted'>· {len(steps)} steps · {retries} retries</span>", unsafe_allow_html=True)
            problems_only = c[1].toggle("Problems only", key="log_filter")
            if steps:
                df = pd.DataFrame(steps)[["ts", "step", "outcome", "detail"]]
                if problems_only:
                    keep = df["outcome"].isin(PROBLEM_OUTCOMES) | (pd.DataFrame(steps)["retries"] > 0)
                    df = df[keep]
                df["ts"] = df["ts"].map(lambda t: time.strftime("%H:%M:%S", time.localtime(t)))
                st.dataframe(df.iloc[::-1], hide_index=True, width="stretch", height=420,
                             column_config={"ts": st.column_config.TextColumn("Time", width="small"),
                                            "step": "Step", "outcome": "Outcome", "detail": "Detail"})
            else:
                st.caption("Starting…")

    live()
