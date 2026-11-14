"""Evaluation: run the public test set and see metrics vs targets, per task, over time."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

from meridian.ui.common import BLUE, ORANGE, ROOT, big


@st.cache_resource
def _jobs() -> dict:
    return {}


def load_reports() -> list[dict]:
    reps = []
    for p in sorted((ROOT / "runs" / "eval").glob("*/report.json")):
        try:
            reps.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    latest = ROOT / "eval_results" / "latest_report.json"
    if not reps and latest.exists():
        reps.append(json.loads(latest.read_text(encoding="utf-8")))
    return sorted(reps, key=lambda r: r.get("started", ""))


def _launcher() -> None:
    jobs = _jobs()
    running = {k: v for k, v in jobs.items() if v["proc"].poll() is None}
    with st.container(border=True):
        st.markdown("#### Run the public test set")
        c = st.columns(4)
        mode = c[0].selectbox("Portal", ["demo", "fake", "live"], key="ev_mode",
                              format_func={"demo": "Demo (fast)", "fake": "Fake portal (browser)", "live": "Real portal"}.get)
        keys = ["(none)"] + sorted(p.name for p in (ROOT / "harness" / "answer_keys").glob("*.json"))
        key = c[1].selectbox("Answer key", keys, key="ev_key")
        rerun = c[2].checkbox("Re-run dispute tasks (duplicate check)", value=True, key="ev_rerun")
        auto = c[3].checkbox("Auto-answer OTP/approvals", value=mode != "live", disabled=mode == "live", key="ev_auto",
                             help="Demo and fake portal only. On the real portal a person answers in Needs you.")
        only = st.text_input("Only these tasks (optional, e.g. T-01,T-19)", key="ev_only")
        if st.button("▶ Start test run", type="primary", disabled=bool(running)):
            label = f"ui-{mode}-{datetime.now():%Y%m%d-%H%M%S}"
            out = ROOT / "runs" / "eval" / label
            out.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, str(ROOT / "harness" / "run_public.py"), "--mode", mode, "--label", label]
            if key != "(none)":
                cmd += ["--key", str(ROOT / "harness" / "answer_keys" / key)]
            if rerun:
                cmd.append("--rerun-disputes")
            if auto and mode != "live":
                cmd += ["--auto-otp", "--auto-approve"]
            if mode == "demo":
                cmd.append("--fast")
            if only.strip():
                cmd += ["--only", only.strip()]
            log = open(out / "harness.log", "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                                    env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "PYTHONWARNINGS": "ignore"})
            jobs[label] = {"proc": proc, "log": out / "harness.log"}
            st.rerun()

    if jobs:
        @st.fragment(run_every=2)
        def progress():
            for label, job in list(jobs.items())[-1:]:
                code = job["proc"].poll()
                st.markdown(f"**{label}** — {'running…' if code is None else ('finished' if code == 0 else f'exited with {code}')}")
                try:
                    tail = job["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-14:]
                except OSError:
                    tail = []
                st.code("\n".join(tail) or "starting…", language=None)
                if code is not None and st.session_state.get("ev_seen") != label:
                    st.session_state.ev_seen = label
                    st.rerun(scope="app")

        progress()


def render() -> None:
    st.title("Evaluation")
    _launcher()
    reports = load_reports()
    if not reports:
        st.info("No test runs yet.")
        return
    labels = [f"{r['label']} · {r['mode']} · {r['started']}" for r in reports][::-1]
    pick = st.selectbox("Test run", labels, index=0, key="ev_pick")
    rep = reports[::-1][labels.index(pick)]
    m, p = rep["metrics"], rep["metrics"]["pass"]
    pct = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731
    icon = lambda ok: "—" if ok is None else ("✅" if ok else "❌")  # noqa: E731
    c = st.columns(4)
    big(c[0], "Task success", pct(m["task_success"]), f"{icon(p['task_success'])} target ≥ 80%")
    big(c[1], "Invoice accuracy", pct(m["invoice_accuracy"]), f"{icon(p['invoice_accuracy'])} target ≥ 90%")
    big(c[2], "Wrong disputes", str(m["wrong_disputes"]), f"{icon(p['wrong_disputes'])} target 0")
    big(c[3], "Duplicate disputes", str(m["duplicate_disputes"]), f"{icon(p['duplicate_disputes'])} target 0")
    st.write("")
    c = st.columns(4)
    big(c[0], "Needed a human", f"{m['needs_human_tasks']} task(s)", f"beyond OTP: {m.get('human_steps_beyond_otp', 0)}")
    big(c[1], "Avg time / task", f"{m['avg_duration_s']} s")
    big(c[2], "Avg steps / task", str(m["avg_steps"]), f"{m.get('total_retries', 0)} retries in total")
    big(c[3], "Avg cost / task", f"₹{m['avg_cost_inr']:.2f}")
    notes = [f"mode {rep['mode']}", f"key: {rep['answer_key'] or 'none'}"]
    if rep.get("auto_otp") or rep.get("auto_approve"):
        notes.append("OTP/approvals auto-answered (demo / fake portal only)")
    if rep.get("reruns"):
        notes.append("re-run: " + ", ".join(f"{k} → {v['new_disputes']} new disputes" for k, v in rep["reruns"].items()))
    st.caption(" · ".join(notes))

    tdf = pd.DataFrame(rep["tasks"])
    tdf["items"] = tdf["items_correct"].astype(str) + "/" + tdf["items_total"].astype(str)
    tdf["problems"] = tdf["problems"].map(lambda x: "; ".join(x[:3]) + (" …" if len(x) > 3 else ""))
    tdf["human_steps"] = tdf["human_steps"].map(", ".join)
    if "trace_id" not in tdf:
        tdf["trace_id"] = None
    tdf["trace_id"] = tdf["trace_id"].map(lambda t: t[:12] + "…" if isinstance(t, str) else "")
    tdf = tdf[["task_id", "kind", "status", "success", "items", "problems", "steps", "retries", "duration_s", "cost_inr",
               "human_steps", "trace_id"]]
    bg = lambda row: [("background-color: rgba(12,163,12,.12)" if row["success"] else  # noqa: E731
                       "background-color: rgba(250,178,25,.16)" if row["status"] == "needs_human" else
                       "background-color: rgba(208,59,59,.12)")] * len(row)
    st.dataframe(tdf.style.apply(bg, axis=1), hide_index=True, width="stretch",
                 column_config={"duration_s": st.column_config.NumberColumn("time (s)", format="%.1f"),
                                "cost_inr": st.column_config.NumberColumn("cost", format="₹ %.2f"),
                                "problems": st.column_config.TextColumn(width="large")})

    scored = [r for r in reports if r["metrics"].get("task_success") is not None]
    if len(scored) > 1:
        st.subheader("History")
        hist = pd.DataFrame([{"run": r["label"], "Task success": r["metrics"]["task_success"],
                              "Invoice accuracy": r["metrics"]["invoice_accuracy"]} for r in scored]).set_index("run")
        st.line_chart(hist, color=[BLUE, ORANGE], y_label="share", x_label="test run")
