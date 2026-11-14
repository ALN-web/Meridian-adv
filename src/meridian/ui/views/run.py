"""Run a task: plain-English task -> plan, live progress, OTP box, step log, stop/resume."""
from __future__ import annotations

import json
import time

import pandas as pd
import streamlit as st

from meridian.agent.demo import sample_tasks
from meridian.agent.modes import MODES, portal_reachable, start_runner
from meridian.agent.planner import PlanError, plan_task
from meridian.ui.common import badge, get_store, hhmm, is_active, plan_of, public_tasks, run_label

PROBLEM_OUTCOMES = {"failed", "needs_human", "session_expired", "not_found", "unreadable", "submit_error",
                    "not_confirmed", "rejected", "cancelled", "waiting_for_human", "otp_requested", "skipped"}


def _new_task(store) -> None:
    with st.container(border=True):
        st.markdown("#### New task")
        top = st.columns([2, 1])
        mode = top[0].radio("Portal", list(MODES), format_func=MODES.get, horizontal=True, key="mode",
                            help="Demo needs nothing. Fake portal: `python -m meridian.fakeportal.server`. "
                                 "Real portal: credentials in .env.")
        show_browser = top[1].checkbox("Show the browser window", value=False, disabled=mode == "demo", key="show_browser")
        reachable, where = (True, "")
        if mode != "demo":
            reachable, where = portal_reachable(mode) if mode == "fake" else (True, "")
            if mode == "fake":
                (st.caption if reachable else st.error)(f"Fake portal: {where}" if reachable else where)
            else:
                st.warning("Real portal: page selectors are unconfirmed until recon succeeds. Watch the step log.")

        st.session_state.setdefault("task_text", "")
        pub = public_tasks()
        options = ["—"] + [f"{t['task_id']} · {t['task']}" for t in pub] + [f"demo · {t}" for t in sample_tasks()]
        pick = st.selectbox("Examples (the 20 public tasks, then demo examples)", options, key="example")
        if pick != "—" and st.session_state.get("_last_pick") != pick:
            st.session_state.task_text = pick.split(" · ", 1)[1]
            st.session_state._last_pick = pick
        text = st.text_area("Task in plain English", key="task_text", height=80,
                            placeholder="Reconcile all invoices on lane PUN-HYD dated in October 2026.")
        plan = None
        if text.strip():
            try:
                plan = plan_task(text)
                st.success(f"Understood as **{plan.kind}** · `{json.dumps(plan.params)}` · {len(plan.steps)} steps")
            except PlanError as exc:
                st.error(str(exc))
        if st.button("▶ Run task", type="primary", disabled=plan is None or not reachable):
            tid = next((t["task_id"] for t in pub if t["task"] == text.strip()), f"UI-{int(time.time()) % 100000:05d}")
            run_id = store.create_run(tid, text.strip(), plan.kind, plan.params, plan.steps, mode)
            start_runner(mode, store, run_id, plan, tid, headless=not show_browser)
            st.session_state.run_id = run_id
            st.rerun()


def _human_inputs(store, run_id: str) -> None:
    """Rendered outside auto-refresh so typing is never interrupted."""
    for req in store.pending_human(run_id):
        with st.container(border=True):
            if req["kind"] == "otp":
                st.markdown("🔐 **One-time password needed**")
                st.caption("Open the operator inbox yourself and type the code here. The agent never opens the inbox, "
                           "and the code is used once and not stored.")
                with st.form(f"otp-{req['id']}", clear_on_submit=True):
                    code = st.text_input("OTP", type="password", max_chars=10)
                    if st.form_submit_button("Send code", type="primary") and code.strip():
                        store.answer_human(req["id"], code.strip())
                        st.rerun()
            elif req["kind"] == "captcha":
                st.markdown("🧩 **CAPTCHA shown** — solve it in the agent's browser window, then press Done.")
                if st.button("Done", key=f"cap-{req['id']}"):
                    store.answer_human(req["id"], "")
                    st.rerun()


def _controls(store, run) -> None:
    c = st.columns([1, 1, 4])
    if is_active(run):
        if c[0].button("⏹ Stop", help="Stops after the current step. Progress is kept; you can resume."):
            store.request_cancel(run.id)
            st.toast("Stopping after the current step…")
    elif run.status in ("failed", "cancelled", "needs_human"):
        if c[0].button("↻ Resume", help="Continue from the checkpoint: finished invoices are not redone."):
            reachable, where = portal_reachable(run.mode)
            if not reachable:
                st.error(where)
            else:
                store.prepare_resume(run.id)
                start_runner(run.mode, store, run.id, plan_of(run), run.task_id,
                             headless=not st.session_state.get("show_browser", False))
                st.rerun()
    if run.result and c[1].button("📋 Results"):
        st.switch_page(st.session_state["pages"]["results"])
    if run.result and run.result.get("trace_url"):
        c[2].markdown(f"[🔭 Open trace in Langfuse]({run.result['trace_url']})")
    elif run.result and run.result.get("trace_id"):
        c[2].caption(f"Trace {run.result['trace_id'][:12]}… (local copy — see Results)")


def render() -> None:
    store = get_store()
    st.title("Run a task")
    _new_task(store)

    runs = store.list_runs(100)
    if not runs:
        st.info("No runs yet. Pick an example above and press Run.")
        return
    ids = [r.id for r in runs]
    cur = st.session_state.get("run_id")
    run_id = st.selectbox("Current run", ids, index=ids.index(cur) if cur in ids else 0,
                          format_func=lambda i: run_label(next(r for r in runs if r.id == i)), key="run_select")
    st.session_state.run_id = run_id
    run = store.get_run(run_id)

    st.markdown(f"### {run.task_id} — {run.task_text}")
    _controls(store, run)
    _human_inputs(store, run_id)
    problems_only = st.toggle("Show only problems, retries and human steps in the log", key="log_filter")

    st.session_state[f"status-{run_id}"] = run.status

    @st.fragment(run_every=2)
    def live():
        r = store.get_run(run_id)
        if r.status != st.session_state.get(f"status-{run_id}"):
            st.session_state[f"status-{run_id}"] = r.status
            st.rerun(scope="app")  # refresh Stop/Resume buttons and results link
        steps = store.steps(run_id)
        head = st.columns([3, 1])
        head[0].markdown(f"{badge(r.status)} &nbsp; <span class='muted'>mode {r.mode} · started {hhmm(r.created)}"
                         + (f" · finished {hhmm(r.finished)}" if r.finished else "") + "</span>", unsafe_allow_html=True)
        total = max(len(r.plan), 1)
        done_upto = total if r.status == "completed" else r.phase
        head[1].progress(min(done_upto / total, 1.0), text=f"step {min(r.phase + 1, total)} of {total}")
        if r.error and r.status in ("failed", "cancelled", "needs_human"):
            st.error(r.error)
        left, right = st.columns([2, 3])
        with left:
            st.markdown("**Plan**")
            rows = []
            for i, s in enumerate(r.plan):
                if r.status == "completed" or i < r.phase:
                    icon, cls = "✅", ""
                elif i == r.phase and is_active(r):
                    icon, cls = "▶️", "plan-now"
                else:
                    icon, cls = "◻️", "muted"
                rows.append(f"<div class='plan-row {cls}'>{icon} {i + 1}. {s}</div>")
            st.markdown("".join(rows), unsafe_allow_html=True)
        with right:
            retries = sum(s["retries"] or 0 for s in steps)
            st.markdown(f"**Live step log** · {len(steps)} steps · {retries} retries")
            if steps:
                df = pd.DataFrame(steps)[["ts", "step", "outcome", "detail", "retries"]]
                if problems_only:
                    df = df[df["outcome"].isin(PROBLEM_OUTCOMES) | (df["retries"] > 0)]
                df["ts"] = df["ts"].map(lambda t: time.strftime("%H:%M:%S", time.localtime(t)))
                st.dataframe(df.iloc[::-1], hide_index=True, width="stretch", height=430,
                             column_config={"ts": "time", "retries": st.column_config.NumberColumn(width="small")})
            else:
                st.caption("Waiting for the first step…")

    live()
