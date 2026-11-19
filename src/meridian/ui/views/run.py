"""Command hub: 3D hero with live figures, the agent panel (conversation, actions, task box),
lane map, invoice board, and the current run's plan and log."""
from __future__ import annotations

import html
import time
from collections import defaultdict
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from meridian.agent.demo import sample_tasks
from meridian.agent.modes import portal_reachable, start_runner
from meridian.agent.planner import PlanError, plan_task
from meridian.ui.common import (REASON_LABEL, badge, get_store, inr, is_active, latest_details, plan_of,
                                 public_tasks, run_label, section)
from meridian.ui.theme import HUB_HEIGHT, hub_html, icon

MODE_LABEL = {"demo": "Demo", "fake": "Fake portal", "live": "Real portal"}
PROBLEM_OUTCOMES = {"failed", "needs_human", "session_expired", "not_found", "unreadable", "submit_error",
                    "not_confirmed", "rejected", "cancelled", "waiting_for_human", "otp_requested", "skipped"}
LOWER_H = 430          # height of the lane map and invoice board cards
PANEL_H = HUB_HEIGHT + LOWER_H + 16
COMPOSER_H = 250
E = html.escape


# ---------------------------------------------------------------- figures

def _figures(store):
    runs = store.list_runs(1000)
    details = latest_details(store)
    checked = [d for d in details if d.get("result") != "cancelled"]
    over = sum(float(d.get("overcharge_inr") or 0) for d in checked)
    live = {r.id for r in runs if r.mode == "live"}  # demo and fake-portal disputes are rehearsals
    filed = sum(d["status"] in ("submitted", "confirmed") and d["run_id"] in live for d in store.disputes())
    waiting = len(store.pending_human()) + len(store.disputes(status="pending"))
    return runs, details, checked, over, filed, waiting


def _short_inr(v: float) -> str:
    if v >= 1e5:
        return f"₹{v / 1e5:.2f} L"
    if v >= 1e3:
        return f"₹{v / 1e3:.1f} k"
    return f"₹{v:,.0f}"


# ---------------------------------------------------------------- lane map

LANE_XY = {"PUN": (150, 128), "PUN-AMD": (82, 46), "PUN-DEL": (196, 22), "PUN-HYD": (300, 104),
           "PUN-BLR": (214, 196), "PUN-CHN": (334, 186)}


def _lane_card(details) -> None:
    by = defaultdict(lambda: {"n": 0, "over": 0.0, "bad": 0})
    for d in details:
        if d.get("result") == "cancelled":
            continue
        b = by[d["lane"]]
        b["n"] += 1
        b["over"] += float(d.get("overcharge_inr") or 0)
        b["bad"] += d.get("result") == "mismatch"
    worst = max(by, key=lambda k: by[k]["over"]) if by and max(v["over"] for v in by.values()) > 0 else None
    px, py = LANE_XY["PUN"]
    paths, nodes = [], []
    for lane, (x, y) in LANE_XY.items():
        if lane == "PUN":
            continue
        hot = lane == worst
        cx, cy = (px + x) / 2 + (y - py) * .18, (py + y) / 2 - (x - px) * .18
        stroke = "#f5c400" if hot else ("#0e0e0e" if lane in by else "#c9c9c3")
        width = 3.4 if hot else (1.8 if lane in by else 1.2)
        dash = "" if lane in by else " stroke-dasharray='4 5'"
        paths.append(f"<path d='M{px} {py} Q{cx:.0f} {cy:.0f} {x} {y}' fill='none' stroke='{stroke}' stroke-width='{width}' "
                     f"stroke-linecap='round'{dash}/>")
        if hot:
            paths.append(f"<path d='M{px} {py} Q{cx:.0f} {cy:.0f} {x} {y}' fill='none' stroke='#0e0e0e' stroke-width='1.2' "
                         "stroke-dasharray='2 9' stroke-linecap='round'><animate attributeName='stroke-dashoffset' from='22' to='0' "
                         "dur='1.2s' repeatCount='indefinite'/></path>")
        info = by.get(lane)
        sub = f"{info['n']} inv · {_short_inr(info['over'])}" if info else "not checked"
        fill = "#f5c400" if hot else "#ffffff"
        nodes.append(f"<circle cx='{x}' cy='{y}' r='{6 if hot else 5}' fill='{fill}' stroke='#0e0e0e' stroke-width='2'/>"
                     f"<text x='{x + 10}' y='{y - 2}' font-family='Manrope' font-size='11' font-weight='700' fill='#0e0e0e'>{lane[4:]}</text>"
                     f"<text x='{x + 10}' y='{y + 11}' font-family='IBM Plex Mono' font-size='8.5' fill='{'#6b5600' if hot else '#8a8a84'}'>{sub}</text>")
    hub = (f"<circle cx='{px}' cy='{py}' r='11' fill='#0e0e0e'/><circle cx='{px}' cy='{py}' r='4' fill='#f5c400'/>"
           f"<text x='{px - 34}' y='{py + 26}' font-family='Manrope' font-size='11' font-weight='700' fill='#0e0e0e'>Pune hub</text>")
    svg = ("<svg viewBox='0 0 420 222' xmlns='http://www.w3.org/2000/svg'><defs><pattern id='dots' width='12' height='12' "
           "patternUnits='userSpaceOnUse'><circle cx='1.2' cy='1.2' r='1.2' fill='#e3e2dc'/></pattern></defs>"
           "<rect width='420' height='222' rx='14' fill='url(#dots)'/>" + "".join(paths) + hub + "".join(nodes) + "</svg>")
    lanes_hit = sum(1 for v in by.values() if v["bad"])
    total_over = sum(v["over"] for v in by.values())
    tag = f"<span class='tag'>Most overcharged · {worst[4:]}</span>" if worst else "<span class='tag k'>No overcharges yet</span>"
    st.markdown(
        f"<div class='chead'><div class='t'><span class='ic'>{icon('route')}</span><div>Lanes from Pune"
        f"<div class='sub'>Overcharge by lane, from checked invoices</div></div></div>{tag}</div>"
        f"<div class='lanes'>{svg}</div>"
        f"<div class='stat4'><div><span>Invoices</span><b>{sum(v['n'] for v in by.values())}</b></div>"
        f"<div><span>Lanes flagged</span><b>{lanes_hit} / 5</b></div>"
        f"<div><span>Overcharge</span><b>{_short_inr(total_over)}</b></div>"
        f"<div><span>Lanes checked</span><b>{len(by)}</b></div></div>", unsafe_allow_html=True)


def _board_card(details) -> None:
    rows = sorted(details, key=lambda d: d.get("invoice_date") or "")
    cells = []
    for d in rows:
        cls = {"match": "ok", "mismatch": "bad", "cancelled": "cx"}.get(d.get("result"), "")
        tip = f"{d['invoice_no']} · {d['lane']} · {d.get('result')}"
        cells.append(f"<i class='{cls}' title='{E(tip)}'></i>")
    cells += ["<i title='Not checked yet'></i>"] * max(0, 48 - len(cells))
    worst = max((d for d in rows if d.get("result") == "mismatch"), key=lambda d: float(d.get("overcharge_inr") or 0), default=None)
    alert = ""
    if worst:
        why = ", ".join(REASON_LABEL.get(r, r) for r in worst.get("reasons", [])[:2]) or "see results"
        alert = (f"<div class='alert'><b>{E(worst['invoice_no'])} · {E(worst['lane'])} — {inr(worst.get('overcharge_inr'))} over</b>"
                 f"<span>{E(why)}. Biggest overcharge found so far.</span></div>")
    n_ok = sum(d.get("result") == "match" for d in rows)
    n_bad = sum(d.get("result") == "mismatch" for d in rows)
    st.markdown(
        f"<div class='chead'><div class='t'><span class='ic'>{icon('grid')}</span><div>Invoice board"
        f"<div class='sub'>{len(rows)} checked · {n_bad} overcharged · {n_ok} billed right</div></div></div></div>"
        f"<div class='board'>{''.join(cells)}</div>"
        "<div class='legend'><span><i style='background:#0e0e0e'></i>Billed right</span>"
        "<span><i style='background:#f5c400'></i>Overcharged</span>"
        "<span><i style='background:repeating-linear-gradient(45deg,#e6e6e2 0 3px,#f5f5f3 3px 6px)'></i>Cancelled</span>"
        "<span><i style='background:#f5f5f3;border:1px dashed #d9d9d4'></i>Not checked</span></div>" + alert,
        unsafe_allow_html=True)


# ---------------------------------------------------------------- agent panel

def _say(step: dict) -> str | None:
    s, o, d = step["step"], step["outcome"], (step.get("detail") or "")
    if s == "otp":
        return {"waiting_for_human": "I need the one-time password from the operator inbox.",
                "submitted": "Code accepted. Signing in."}.get(o)
    if s == "login" and o == "ok":
        return "Signed in to the TransIndus portal."
    if s == "dismiss_notice" and o == "ok":
        return "Acknowledged the portal's maintenance notice."
    if s.startswith("search_invoices") and o == "ok":
        return "Read the invoice list, every page."
    if s.startswith("open_invoice") and o == "ok":
        return f"Opened invoice {s.split(':', 1)[1]}."
    if s == "billing_history":
        return d or "Reading every invoice once for billing history."
    if s == "runner":
        return None
    if o in PROBLEM_OUTCOMES:
        return f"{s.split(':')[0].replace('_', ' ').capitalize()}: {o.replace('_', ' ')}. {d}".strip()
    return None


def _feed(store, run) -> str:
    when = datetime.fromtimestamp(run.created).strftime("%d %b · %H:%M")
    out = [f"<div class='daystamp'>{when} · {MODE_LABEL.get(run.mode, run.mode)}</div>",
           f"<div class='msg me'>{E(run.task_text)}</div>"]
    said: list[str] = []
    for step in store.steps(run.id):
        line = _say(step)
        if line and line not in said:
            said.append(line)
    for line in said[-6:]:
        out.append(f"<div class='msg bot'>{E(line)}</div>")
    res = run.result or {}
    if run.status == "completed":
        invs = res.get("invoices") or []
        bad = [i for i in invs if float(i.get("overcharge_inr") or 0) > 0 or i.get("reasons")]
        out.append(f"<div class='msg bot'>Done. {len(invs)} invoice(s) in the result"
                   + (f", <b>{len(bad)} with problems</b>." if bad else ".") + "</div>")
        cards = []
        for i in (bad or invs)[:2]:
            over = float(i.get("overcharge_inr") or 0)
            billed = float(i.get("billed_inr") or i.get("total_inr") or 0)
            pct = min(100, int(100 * over / billed)) if billed and over else 100
            kind = "bad" if over > 0 or i.get("reasons") else "ok"
            why = REASON_LABEL.get((i.get("reasons") or [""])[0], i.get("status", ""))
            right = f"+{inr(over)}" if over > 0 else inr(billed)
            cards.append(f"<div class='mini {kind}'><div class='no'>{E(i.get('invoice_no', ''))}</div>"
                         f"<div class='k'>{E(why or 'Checked')}</div>"
                         f"<div class='v'><span>{'Overcharged' if kind == 'bad' else 'Total'}</span><span class='r'>{right}</span></div>"
                         f"<div class='bar'><i style='width:{pct}%'></i></div></div>")
        if cards:
            out.append(f"<div class='cards2'>{''.join(cards)}</div>")
    elif run.status in ("failed", "cancelled", "needs_human") and run.error:
        out.append(f"<div class='msg bot bad'>{E(run.error)}<small>Resume picks up where it stopped.</small></div>")
    elif is_active(run):
        out.append("<div class='typing'><i></i><i></i><i></i></div>")
    return "".join(out)


def _actions(store, run) -> str:
    rows = []
    for req in store.pending_human():
        what = {"otp": "Enter the one-time password", "captcha": "Solve the CAPTCHA"}.get(req["kind"], req["kind"])
        rows.append(f"<a class='act hot' href='/needs-you' target='_self'>{what}<span>now</span></a>")
    for d in store.disputes(status="pending"):
        rows.append(f"<a class='act hot' href='/needs-you' target='_self'>Approve dispute · {E(d['invoice_no'])}"
                    f"<span>+{inr(float(d['billed_inr']) - float(d['expected_inr']))}</span></a>")
    if run and run.result:
        rows.append("<a class='act' href='/results' target='_self'>Open the full result<span>evidence</span></a>")
    if run and run.status in ("failed", "cancelled", "needs_human"):
        rows.append("<div class='act'>Resume this run below<span>keeps progress</span></div>")
    if not rows:
        return ""
    return "<div class='act-head'>Suggested actions</div>" + "".join(rows)


def _human_inputs(store, run_id: str) -> None:
    """OTP / CAPTCHA inputs. Outside every auto-refresh so typing is never interrupted."""
    for req in store.pending_human(run_id):
        if req["kind"] == "otp":
            if store.otp_asked_before(req["run_id"]):
                st.warning("The portal did not accept the previous code (invalid or expired), so the agent signed in again and the portal sent a **new** code. Use that newest code — it is valid for 5 minutes.")
            with st.form(f"otp-{req['id']}", clear_on_submit=True, border=True):
                c = st.columns([3, 1.3], vertical_alignment="bottom")
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


def _composer(store) -> None:
    with st.container(border=True):
        st.session_state.setdefault("task_text", "")
        pub = public_tasks()
        options = ["Pick a public task…"] + [f"{t['task_id']} · {t['task']}" for t in pub] + [f"Demo · {t}" for t in sample_tasks()]
        pick = st.selectbox("Example", options, key="example", label_visibility="collapsed")
        if pick != options[0] and st.session_state.get("_last_pick") != pick:
            st.session_state.task_text = pick.split(" · ", 1)[1]
            st.session_state._last_pick = pick
        text = st.text_area("Task", key="task_text", height=68, label_visibility="collapsed",
                            placeholder="Ask Meridian: reconcile, list, collect proofs or raise disputes…")
        plan, problem = None, ""
        if text.strip():
            try:
                plan = plan_task(text)
            except PlanError as exc:
                problem = str(exc)
        mode = st.segmented_control("Portal", list(MODE_LABEL), format_func=MODE_LABEL.get, default="demo",
                                    key="mode", label_visibility="collapsed") or "demo"
        c = st.columns([1.5, 1], vertical_alignment="center")
        show_browser = c[0].toggle("Show browser", value=False, disabled=mode == "demo", key="show_browser")
        reachable, where = portal_reachable(mode) if mode == "fake" else (True, "")
        if c[1].button("Run", type="primary", disabled=plan is None or not reachable, width="stretch", icon=":material/send:"):
            tid = next((t["task_id"] for t in pub if t["task"] == text.strip()), f"UI-{int(time.time()) % 100000:05d}")
            run_id = store.create_run(tid, text.strip(), plan.kind, plan.params, plan.steps, mode)
            start_runner(mode, store, run_id, plan, tid, headless=not show_browser)
            st.session_state.run_id = run_id
            st.rerun()
        if problem:
            st.caption(f":red[{problem}]")
        elif not reachable:
            st.caption(f":red[{where}]")
        elif plan:
            st.caption(f"{plan.kind.replace('_', ' ')} · {len(plan.steps)} steps"
                       + (" · you'll be asked for the OTP" if mode == "live" else ""))


def _panel(store, run) -> None:
    with st.container(border=True, height=PANEL_H):
        busy = bool(run and is_active(run))
        state = "Working on a task" if busy else "Online · TransIndus portal"
        tag = f"<span class='tag'>{E(run.task_id)}</span>" if run else ""
        st.markdown(f"<div class='agent-top'><div class='agent-id'><span class='av'><i></i><i></i></span>"
                    f"<div><b>Meridian agent</b><span class='{'busy' if busy else ''}'>{state}</span></div></div>{tag}</div>",
                    unsafe_allow_html=True)
        with st.container(height=PANEL_H - COMPOSER_H - 150, border=False):
            if run:
                st.markdown(_feed(store, run), unsafe_allow_html=True)
                _human_inputs(store, run.id)
                st.markdown(_actions(store, run), unsafe_allow_html=True)
            else:
                st.markdown("<div class='msg bot'>Hi. Give me a task below, for example: reconcile all invoices on "
                            "a lane for a month. I check every line against the eight rules and only raise a dispute "
                            "after you approve it.</div>", unsafe_allow_html=True)
        _composer(store)


# ---------------------------------------------------------------- current run

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


def _current_run(store, runs, run) -> None:
    section("Current run")
    ids = [r.id for r in runs]
    st.session_state["run_select"] = run.id
    st.selectbox("Run", ids, key="run_select", label_visibility="collapsed",
                 format_func=lambda i: run_label(next(r for r in runs if r.id == i)),
                 on_change=lambda: st.session_state.update(run_id=st.session_state.run_select))
    _controls(store, run)
    run_id = run.id
    st.session_state[f"status-{run_id}"] = run.status
    st.session_state[f"human-{run_id}"] = len(store.pending_human(run_id))

    @st.fragment(run_every=2)
    def live():
        r = store.get_run(run_id)
        if r.status != st.session_state.get(f"status-{run_id}"):
            st.session_state[f"status-{run_id}"] = r.status
            st.rerun(scope="app")  # refresh the panel, buttons and figures
        if len(store.pending_human(run_id)) != st.session_state.get(f"human-{run_id}", 0):
            st.rerun(scope="app")  # show the OTP box in the panel straight away
        steps = store.steps(run_id)
        total = max(len(r.plan), 1)
        done_upto = total if r.status == "completed" else r.phase
        head = st.columns([1, 3], vertical_alignment="center")
        head[0].markdown(badge(r.status), unsafe_allow_html=True)
        head[1].progress(min(done_upto / total, 1.0), text=f"Step {min(r.phase + 1, total)} of {total} · {MODE_LABEL.get(r.mode, r.mode)}")

        left, right = st.columns([2, 3], gap="small")
        with left, st.container(border=True):
            st.markdown("**Plan**")
            rows = []
            for i, s in enumerate(r.plan):
                if r.status == "completed" or i < r.phase:
                    cls, mark = "done", "✓"
                elif i == r.phase and r.status in ("running", "waiting_for_human", "queued"):
                    cls, mark = "now", str(i + 1)
                else:
                    cls, mark = "", str(i + 1)
                rows.append(f"<div class='plan-row {cls}'><b>{mark}</b>{E(s)}</div>")
            st.markdown("".join(rows), unsafe_allow_html=True)
        with right, st.container(border=True):
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
                st.dataframe(df.iloc[::-1], hide_index=True, width="stretch", height=360,
                             column_config={"ts": st.column_config.TextColumn("Time", width="small"),
                                            "step": "Step", "outcome": "Outcome", "detail": "Detail"})
            else:
                st.caption("Starting…")

    live()


# ---------------------------------------------------------------- page

def render() -> None:
    store = get_store()
    runs, details, checked, over, filed, waiting = _figures(store)
    ids = [r.id for r in runs]
    cur = st.session_state.get("run_id")
    run = store.get_run(cur if cur in ids else ids[0]) if ids else None
    if run:
        st.session_state.run_id = run.id

    busy = bool(run and is_active(run))
    status = (f"Running {run.task_id} · {MODE_LABEL.get(run.mode, run.mode)}" if busy
              else f"Agent ready · {len(runs)} tasks run")
    chips = [("box", "Invoices checked", str(len(checked)), "", False),
             ("rupee", "Overcharge found", _short_inr(over), "", False),
             ("gavel", "Disputes filed", str(filed), "on the portal", False),
             ("bell", "Waiting for you", str(waiting), "", waiting > 0)]

    left, right = st.columns([2.05, 1], gap="small")
    with left:
        components.html(hub_html(chips, status, busy), height=HUB_HEIGHT)
        a, b = st.columns(2, gap="small")
        with a, st.container(border=True, height=LOWER_H):
            _lane_card(details)
        with b, st.container(border=True, height=LOWER_H):
            _board_card(details)
    with right:
        _panel(store, run)

    if run:
        _current_run(store, runs, run)
