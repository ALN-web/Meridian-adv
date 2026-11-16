"""Evaluation: run the public test set and see metrics vs targets, per task, over time."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

from meridian.ui.common import BLUE, ORANGE, ROOT, big, header


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
    return sorted(reps, key=lambda r: (r.get("started", ""), "merged_from" in r))  # a merged report wins a tie


def _launcher() -> None:
    jobs = _jobs()
    running = {k: v for k, v in jobs.items() if v["proc"].poll() is None}
    with st.container(border=True):
        c = st.columns([1.2, 1.4, 1], vertical_alignment="bottom")
        mode = c[0].selectbox("Portal", ["demo", "fake", "live"], key="ev_mode",
                              format_func={"demo": "Demo", "fake": "Fake portal", "live": "Real portal"}.get)
        keys = ["(none)"] + sorted(p.name for p in (ROOT / "harness" / "answer_keys").glob("*.json"))
        key = c[1].selectbox("Answer key", keys, key="ev_key")
        start = c[2].button("Run 20 public tasks", type="primary", disabled=bool(running), width="stretch")
        with st.expander("Options"):
            o = st.columns(3)
            rerun = o[0].checkbox("Re-run disputes (duplicate check)", value=True, key="ev_rerun")
            auto = o[1].checkbox("Auto-answer OTP and approvals", value=mode != "live", disabled=mode == "live", key="ev_auto",
                                 help="Demo and fake portal only.")
            only = o[2].text_input("Only these tasks", key="ev_only", placeholder="T-01,T-19")
        if start:
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
                if code is not None and st.session_state.get("ev_seen") == label:
                    continue  # finished and already shown in the report list
                st.markdown(f"**{'Running…' if code is None else ('Finished' if code == 0 else f'Exited with {code}')}** <span class='muted'>{label}</span>", unsafe_allow_html=True)
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
    header("Evaluation", "Score every run against the targets.")
    _launcher()
    reports = load_reports()
    if not reports:
        st.info("No test runs yet.")
        return
    labels = [f"{r['label']} · {r['mode']} · {r['started']}" for r in reports][::-1]
    st.write("")
    pick = st.selectbox("Test run", labels, index=0, key="ev_pick")
    rep = reports[::-1][labels.index(pick)]
    m, p = rep["metrics"], rep["metrics"]["pass"]
    pct = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731
    icon = lambda ok: "" if ok is None else ("✓ " if ok else "✕ ")  # noqa: E731
    c = st.columns(4)
    big(c[0], "Task success", pct(m["task_success"]), f"{icon(p['task_success'])}target ≥ 80%")
    big(c[1], "Invoice accuracy", pct(m["invoice_accuracy"]), f"{icon(p['invoice_accuracy'])}target ≥ 90%")
    big(c[2], "Wrong disputes", str(m["wrong_disputes"]), f"{icon(p['wrong_disputes'])}target 0")
    big(c[3], "Duplicates", str(m["duplicate_disputes"]), f"{icon(p['duplicate_disputes'])}target 0")
    st.markdown(f"<p class='muted' style='margin-top:12px'>{m['needs_human_tasks']} needed a person · "
                f"{m['avg_duration_s']} s and {m['avg_steps']} steps per task · {m.get('total_retries', 0)} retries · "
                f"₹{m['avg_cost_inr']:.2f} per task · key: {rep['answer_key'] or 'none'}</p>", unsafe_allow_html=True)

    tdf = pd.DataFrame(rep["tasks"])
    tdf["items"] = tdf["items_correct"].astype(str) + "/" + tdf["items_total"].astype(str)
    tdf["problems"] = tdf["problems"].map(lambda x: "; ".join(x[:3]) + (" …" if len(x) > 3 else ""))
    tdf["human_steps"] = tdf["human_steps"].map(", ".join)
    if "trace_id" not in tdf:
        tdf["trace_id"] = None
    tdf["trace_id"] = tdf["trace_id"].map(lambda t: t[:12] + "…" if isinstance(t, str) else "")
    tdf = tdf[["task_id", "kind", "status", "success", "items", "problems", "duration_s"]]
    scored_run = bool(rep.get("answer_key"))
    bg = lambda row: [("background-color: rgba(12,163,12,.12)" if row["success"] else  # noqa: E731
                       "background-color: rgba(250,178,25,.16)" if row["status"] == "needs_human" else
                       "" if not scored_run and row["status"] == "completed" else  # no key: not a failure
                       "background-color: rgba(208,59,59,.12)")] * len(row)
    st.dataframe(tdf.style.apply(bg, axis=1), hide_index=True, width="stretch",
                 column_config={"task_id": "Task", "kind": "Kind", "status": "Status", "success": "Pass", "items": "Items",
                                "duration_s": st.column_config.NumberColumn("Time (s)", format="%.1f"),
                                "problems": st.column_config.TextColumn("Problems", width="large")})

    scored = [r for r in reports if r["metrics"].get("task_success") is not None]
    if len(scored) > 1:
        st.markdown("**History**")
        hist = pd.DataFrame([{"run": r["label"], "Task success": r["metrics"]["task_success"],
                              "Invoice accuracy": r["metrics"]["invoice_accuracy"]} for r in scored]).set_index("run")
        st.line_chart(hist, color=[BLUE, ORANGE], y_label="share", x_label="test run")
