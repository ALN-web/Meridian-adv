"""Operator screen: task, plan, live step log, OTP box, disputes awaiting approval, results, evaluation.

Run:  streamlit run src/meridian/ui/app.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from meridian.agent.demo import DemoRunner, sample_tasks  # noqa: E402
from meridian.agent.planner import PlanError, plan_task  # noqa: E402
from meridian.store import RUN_ACTIVE, Store  # noqa: E402

st.set_page_config(page_title="Meridian Portal Agent", page_icon="🚚", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem; max-width: 1400px;}
.chip {display:inline-block;padding:2px 8px;margin:0 4px 4px 0;border-radius:10px;font-size:0.78rem;
       background:rgba(120,120,120,.15);border:1px solid rgba(120,120,120,.3);}
.chip.bad {background:rgba(220,60,60,.12);border-color:rgba(220,60,60,.4);}
.status {font-weight:600;padding:2px 10px;border-radius:10px;font-size:.8rem}
.s-running{background:#dbeafe;color:#1e3a8a}.s-waiting_for_human{background:#fef3c7;color:#92400e}
.s-completed{background:#dcfce7;color:#14532d}.s-needs_human{background:#ffedd5;color:#9a3412}
.s-failed{background:#fee2e2;color:#7f1d1d}.s-queued{background:#e5e7eb;color:#374151}
.amt-l {font-size:.8rem;opacity:.7} .amt {font-size:1.15rem;font-weight:600;white-space:nowrap}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_store() -> Store:
    return Store()


store = get_store()


def badge(status: str) -> str:
    label = status.replace("_", " ")
    return f"<span class='status s-{status}'>{label}</span>"


def inr(v) -> str:
    if v is None:
        return "—"
    return f"₹{Decimal(str(v)):,.2f}"


def ago(ts: float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


# ---------------------------------------------------------------- sidebar: start a task, pick a run

with st.sidebar:
    st.header("🚚 Meridian Portal Agent")
    st.caption("TransIndus invoice reconciliation · Team Delta · synthetic data only")
    mode = st.radio(
        "Portal",
        ["Demo (simulated portal)", "Live portal"],
        help="Live mode is enabled once the Playwright runner is wired to the real portal.",
    )
    live = mode.startswith("Live")
    if live:
        st.warning("Live runner not wired yet — finish portal recon first. Use Demo for now.")

    st.subheader("New task")
    if "task_text" not in st.session_state:
        st.session_state.task_text = ""
    examples = sample_tasks()
    pick = st.selectbox("Examples", ["—"] + examples, index=0)
    if pick != "—" and st.session_state.get("_last_pick") != pick:
        st.session_state.task_text = pick
        st.session_state._last_pick = pick
    text = st.text_area("Task in plain English", key="task_text", height=110,
                        placeholder="Reconcile all invoices on lane PUN-HYD dated in October 2026.")
    plan = None
    if text.strip():
        try:
            plan = plan_task(text)
            st.success(f"Understood as **{plan.kind}** · {json.dumps(plan.params)}")
        except PlanError as exc:
            st.error(str(exc))
    if st.button("▶ Run task", type="primary", disabled=plan is None or live, width="stretch"):
        task_id = f"UI-{int(time.time()) % 100000:05d}"
        run_id = store.create_run(task_id, text.strip(), plan.kind, plan.params, plan.steps, "demo")
        DemoRunner(store, run_id, plan, task_id).start()
        st.session_state.run_id = run_id
        st.rerun()

    st.subheader("Runs")
    runs = store.list_runs(30)
    if runs:
        labels = {r.id: f"{r.task_id} · {r.kind} · {r.status.replace('_', ' ')}" for r in runs}
        current = st.session_state.get("run_id") or runs[0].id
        if current not in labels:
            current = runs[0].id
        st.session_state.run_id = st.radio("Select a run", list(labels), format_func=labels.get,
                                           index=list(labels).index(current), label_visibility="collapsed")
    else:
        st.caption("No runs yet.")


# ---------------------------------------------------------------- top bar: anything waiting on a person


def human_signature() -> str:
    """What a person may need to act on. When it changes, the whole page re-renders once.

    Inputs (OTP box, Approve/Reject) live outside auto-refreshing fragments so a click or
    half-typed code is never lost to a refresh.
    """
    h = sorted(r["id"] for r in store.pending_human())
    d = sorted(r["id"] for r in store.disputes(status="pending"))
    return "|".join(h) + "#" + "|".join(d)


st.session_state.setdefault("human_sig", human_signature())


@st.fragment(run_every=3)
def human_watch():
    sig = human_signature()
    if sig != st.session_state.human_sig:
        st.session_state.human_sig = sig
        st.rerun(scope="app")
    pend_h = store.pending_human()
    pend_d = store.disputes(status="pending")
    if pend_h:
        st.warning(f"🔐 {len(pend_h)} task(s) waiting for a one-time password — see the **Task** tab.")
    if pend_d:
        st.info(f"⚖️ {len(pend_d)} dispute(s) waiting for approval — see the **Approvals** tab.")


st.session_state.human_sig = human_signature()
human_watch()

pending_count = len(store.disputes(status="pending"))
tab_task, tab_appr, tab_res, tab_eval = st.tabs(
    ["Task", f"Approvals ({pending_count})" if pending_count else "Approvals", "Results", "Evaluation"]
)

run_id = st.session_state.get("run_id")

# ---------------------------------------------------------------- Task tab: plan, OTP, live log

with tab_task:
    if not run_id:
        st.info("Start a task from the sidebar. Demo mode uses the real planner, rules engine and approval flow "
                "on a simulated portal.")
    else:

        @st.fragment(run_every=2)
        def live_view():
            run = store.get_run(run_id)
            if run is None:
                return
            top = st.columns([3, 1])
            top[0].markdown(f"#### {run.task_id} — {run.task_text}")
            top[1].markdown(f"<div style='text-align:right;padding-top:.6rem'>{badge(run.status)}</div>",
                            unsafe_allow_html=True)

            steps = store.steps(run_id)
            left, right = st.columns([2, 3])
            with left:
                st.markdown("**Plan**")
                progress = len(steps)
                mark = "✅" if run.status == "completed" else "▫️"
                st.markdown("\n".join(f"{mark} {i}. {s}  " for i, s in enumerate(run.plan, 1)))
                st.caption(f"Mode: {run.mode} · started {ago(run.created)}")

            with right:
                st.markdown(f"**Live step log** · {progress} steps")
                if steps:
                    df = pd.DataFrame(steps)[["ts", "step", "outcome", "detail", "retries"]]
                    df["ts"] = df["ts"].map(ago)
                    df = df.iloc[::-1]
                    st.dataframe(df, hide_index=True, width="stretch", height=420,
                                 column_config={"ts": "time", "retries": st.column_config.NumberColumn("retries", width="small")})
                else:
                    st.caption("Waiting for the first step…")
            if run.status not in RUN_ACTIVE:
                st.session_state[f"done-{run_id}"] = True

        # Human inputs: rendered outside the auto-refreshing fragment (see human_signature).
        for req in store.pending_human(run_id):
            if req["kind"] == "otp":
                with st.container(border=True):
                    st.markdown("🔐 **One-time password needed**")
                    st.caption("Open the operator inbox yourself and type the code here. "
                               "The agent never opens the inbox, and the code is not stored.")
                    with st.form(f"otp-{req['id']}", clear_on_submit=True):
                        code = st.text_input("OTP", type="password", max_chars=10)
                        if st.form_submit_button("Send code", type="primary"):
                            if code.strip():
                                store.answer_human(req["id"], code.strip())
                                st.rerun()
            elif req["kind"] == "captcha":
                with st.container(border=True):
                    st.markdown("🧩 **CAPTCHA shown** — solve it in the agent's browser window, then click Done.")
                    if st.button("Done", key=f"cap-{req['id']}"):
                        store.answer_human(req["id"], "")
                        st.rerun()

        live_view()

# ---------------------------------------------------------------- Approvals tab

with tab_appr:

    def approvals():
        pending = store.disputes(status="pending")
        st.markdown("Disputes are the only thing the agent writes to the portal. Each one needs your approval; "
                    "after submitting, the agent checks the portal's dispute list to confirm it was saved.")
        if not pending:
            st.success("Nothing waiting for approval.")
        for d in pending:
            billed, expected = Decimal(d["billed_inr"]), Decimal(d["expected_inr"])
            with st.container(border=True):
                c = st.columns([2.4, 1.4, 1.4, 1.4, 1.3])
                c[0].markdown(f"**{d['invoice_no']}**  \n" + "".join(f"<span class='chip bad'>{r}</span>" for r in d["reasons"]),
                              unsafe_allow_html=True)
                for col, label, val in ((c[1], "Billed", billed), (c[2], "Expected", expected),
                                        (c[3], "Overcharge", billed - expected)):
                    col.markdown(f"<div class='amt-l'>{label}</div><div class='amt'>{inr(val)}</div>",
                                 unsafe_allow_html=True)
                with c[4]:
                    if st.button("✅ Approve", key=f"ap-{d['id']}", type="primary", width="stretch"):
                        store.decide_dispute(d["id"], True)
                        st.rerun()
                    if st.button("✖ Reject", key=f"rj-{d['id']}", width="stretch"):
                        store.decide_dispute(d["id"], False)
                        st.rerun()
                if d["evidence"]:
                    st.caption("Evidence: " + " · ".join(d["evidence"]))

        st.markdown("##### Dispute history")
        hist = [d for d in store.disputes() if d["status"] != "pending"]
        if hist:
            df = pd.DataFrame(hist)[["invoice_no", "status", "reasons", "billed_inr", "expected_inr", "portal_ref", "decided_at", "note"]]
            df["reasons"] = df["reasons"].map(", ".join)
            df["decided_at"] = df["decided_at"].map(ago)
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("No decisions yet.")

    approvals()

# ---------------------------------------------------------------- Results tab

with tab_res:
    run = store.get_run(run_id) if run_id else None
    if not run:
        st.info("Select a run.")
    elif not run.result:
        st.info(f"Run is {run.status.replace('_', ' ')} — results appear when it finishes.")
    else:
        r = run.result
        m = st.columns(5)
        m[0].markdown(f"Status<br>{badge(r.get('status', run.status))}", unsafe_allow_html=True)
        m[1].metric("Steps", r.get("steps", 0))
        m[2].metric("Retries", r.get("retries", 0))
        m[3].metric("Duration", f"{r.get('duration_s', 0)} s")
        m[4].metric("Cost", inr(r.get("cost_inr", 0)))

        invs = r.get("invoices") or []
        if invs:
            st.markdown("##### Invoices")
            df = pd.DataFrame(invs)
            if "reasons" in df:
                df["reasons"] = df["reasons"].map(lambda x: ", ".join(x) if isinstance(x, list) else "")
            if "evidence" in df:
                df = df.drop(columns=["evidence"])
            counts = df["result"].value_counts().to_dict() if "result" in df else {}
            if counts:
                st.caption(" · ".join(f"{k}: {v}" for k, v in counts.items()))

            def color(row):
                res = row.get("result", "")
                col = {"match": "rgba(34,197,94,.12)", "mismatch": "rgba(239,68,68,.12)",
                       "cancelled": "rgba(156,163,175,.18)"}.get(res, "")
                return [f"background-color: {col}"] * len(row)

            money = st.column_config.NumberColumn(format="₹ %.2f")
            st.dataframe(df.style.apply(color, axis=1), hide_index=True, width="stretch",
                         column_config={"billed_inr": money, "expected_inr": money, "total_inr": money})
        if r.get("missing_in_portal") is not None and run.kind == "missing":
            st.markdown("##### Missing in portal")
            st.write(r["missing_in_portal"] or "None — every delivered shipment was invoiced.")
        if r.get("pods"):
            st.markdown("##### Delivery proofs")
            st.dataframe(pd.DataFrame(r["pods"]), hide_index=True, width="stretch")
        if r.get("disputes"):
            st.markdown("##### Disputes raised and confirmed")
            st.dataframe(pd.DataFrame(r["disputes"]), hide_index=True, width="stretch")

        with st.expander("Task result JSON (graded format)"):
            st.json(r)
        st.download_button("Download result JSON", json.dumps(r, indent=2), file_name=f"{r.get('task_id', 'result')}.json",
                           mime="application/json")

# ---------------------------------------------------------------- Evaluation tab

with tab_eval:
    runs = store.list_runs(200)
    finished = [r for r in runs if r.status not in RUN_ACTIVE]
    st.markdown("Scores against the answer key come from the test harness (`harness/run_public.py`). "
                "Until then this page summarises every run.")
    disputes = store.disputes()
    k = st.columns(6)
    k[0].metric("Runs", len(runs))
    k[1].metric("Completed", sum(r.status == "completed" for r in finished))
    k[2].metric("Needed a human", sum(r.status == "needs_human" for r in finished))
    k[3].metric("Failed", sum(r.status == "failed" for r in finished))
    k[4].metric("Disputes confirmed", sum(d["status"] == "confirmed" for d in disputes))
    k[5].metric("Duplicate disputes", 0, help="The store allows only one live dispute per invoice.")
    if finished:
        rows = []
        for r in finished:
            res = r.result or {}
            rows.append({
                "task": r.task_id, "kind": r.kind, "status": r.status, "steps": res.get("steps"),
                "retries": res.get("retries"), "duration_s": res.get("duration_s"), "cost_inr": res.get("cost_inr"),
                "human_steps": ", ".join(res.get("human_steps", [])), "mode": r.mode,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
