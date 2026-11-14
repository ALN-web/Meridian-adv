"""Shared pieces for the operator screen: store, styling, formatting, run selection."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

from meridian.agent.planner import Plan
from meridian.store import RUN_ACTIVE, Run, Store

ROOT = Path(__file__).resolve().parents[3]
BLUE, ORANGE = "#2a78d6", "#eb6834"  # categorical slots 1-2 of the validated default palette
FINISHED = ("completed", "needs_human", "failed", "cancelled")

CSS = """
<style>
.block-container {padding-top: 1.4rem; max-width: 1400px;}
.chip {display:inline-block;padding:1px 8px;margin:0 4px 4px 0;border-radius:10px;font-size:.78rem;
       background:rgba(127,127,127,.14);border:1px solid rgba(127,127,127,.3);}
.chip.bad {background:rgba(208,59,59,.12);border-color:rgba(208,59,59,.45);}
.chip.ok {background:rgba(12,163,12,.12);border-color:rgba(12,163,12,.45);}
.status {font-weight:600;padding:2px 10px;border-radius:10px;font-size:.8rem;border:1px solid transparent}
.s-running{background:rgba(42,120,214,.15);border-color:rgba(42,120,214,.45)}
.s-waiting_for_human{background:rgba(250,178,25,.18);border-color:rgba(250,178,25,.6)}
.s-completed{background:rgba(12,163,12,.14);border-color:rgba(12,163,12,.5)}
.s-needs_human{background:rgba(236,131,90,.18);border-color:rgba(236,131,90,.6)}
.s-failed{background:rgba(208,59,59,.14);border-color:rgba(208,59,59,.5)}
.s-cancelled,.s-queued{background:rgba(127,127,127,.14);border-color:rgba(127,127,127,.4)}
.lbl {font-size:.78rem;opacity:.72} .big {font-size:1.25rem;font-weight:650;white-space:nowrap}
.plan-row {padding:3px 0;font-size:.92rem} .plan-now {font-weight:650}
.muted {opacity:.65;font-size:.85rem}
</style>
"""

STATUS_ICON = {"running": "⏳", "waiting_for_human": "✋", "completed": "✅", "needs_human": "🟠",
               "failed": "❌", "cancelled": "⏹", "queued": "…"}


@st.cache_resource
def get_store() -> Store:
    return Store(ROOT / "runs" / "meridian.sqlite")


def badge(status: str) -> str:
    return f"<span class='status s-{status}'>{STATUS_ICON.get(status, '')} {status.replace('_', ' ')}</span>"


def chips(items, kind: str = "") -> str:
    return "".join(f"<span class='chip {kind}'>{i}</span>" for i in items)


def inr(v) -> str:
    if v is None or v == "":
        return "—"
    d = Decimal(str(v))
    sign = "-" if d < 0 else ""
    return f"{sign}₹{abs(d):,.2f}"


def hhmm(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %H:%M:%S") if ts else ""


def big(col, label: str, value: str, note: str = "") -> None:
    col.markdown(f"<div class='lbl'>{label}</div><div class='big'>{value}</div>"
                 + (f"<div class='lbl'>{note}</div>" if note else ""), unsafe_allow_html=True)


def run_label(r: Run) -> str:
    return f"{STATUS_ICON.get(r.status, '')} {r.task_id} · {r.kind} · {r.mode} · {hhmm(r.created)}"


def plan_of(r: Run) -> Plan:
    return Plan(r.kind, r.params, r.plan)


def pick_run(store: Store, key: str, *, finished_only: bool = False, label: str = "Run") -> Run | None:
    """Run picker shared across pages; follows the run selected elsewhere."""
    runs = store.list_runs(100)
    if finished_only:
        runs = [r for r in runs if r.status in FINISHED]
    if not runs:
        return None
    ids = [r.id for r in runs]
    current = st.session_state.get("run_id")
    idx = ids.index(current) if current in ids else 0
    chosen = st.selectbox(label, ids, index=idx, format_func=lambda i: run_label(next(r for r in runs if r.id == i)), key=key)
    st.session_state.run_id = chosen
    return next(r for r in runs if r.id == chosen)


def public_tasks() -> list[dict]:
    p = ROOT / "harness" / "tasks_public.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))["tasks"]
    except (OSError, ValueError, KeyError):
        return []


def human_signature(store: Store) -> str:
    h = sorted(r["id"] for r in store.pending_human())
    d = sorted(r["id"] for r in store.disputes(status="pending"))
    return "|".join(h) + "#" + "|".join(d)


def is_active(r: Run) -> bool:
    return r.status in RUN_ACTIVE
