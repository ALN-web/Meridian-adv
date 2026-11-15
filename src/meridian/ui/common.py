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

from meridian.ui.theme import CSS, PAGE_HEIGHT, page_html  # noqa: E402  (CSS re-exported for app.py)

STATUS = {  # status -> (pill class, label)
    "running": ("p-run", "Running"), "waiting_for_human": ("p-wait", "Waiting for you"), "completed": ("p-ok", "Completed"),
    "needs_human": ("p-wait", "Needs a person"), "failed": ("p-bad", "Failed"), "cancelled": ("p-grey", "Stopped"),
    "queued": ("p-grey", "Queued"),
}
STATUS_ICON = {"running": "●", "waiting_for_human": "●", "completed": "✓", "needs_human": "!", "failed": "✕",
               "cancelled": "■", "queued": "…"}


@st.cache_resource
def get_store() -> Store:
    return Store(ROOT / "runs" / "meridian.sqlite")


def badge(status: str) -> str:
    cls, label = STATUS.get(status, ("p-grey", status.replace("_", " ")))
    return f"<span class='pill {cls}'>{label}</span>"


def chips(items, kind: str = "") -> str:
    cls = {"bad": "p-bad", "ok": "p-ok", "wait": "p-wait"}.get(kind, "p-grey")
    return "".join(f"<span class='pill {cls}'>{i}</span>" for i in items)


LABEL = {"Run a task": "Operate", "Needs you": "Operate", "Results": "Operate", "Documents": "Operate",
         "Disputes": "Operate", "Monthly summary": "Report", "Evaluation": "Report", "System": "Admin"}


def header(title: str, sub: str | None = None) -> None:
    """Compact 3D page header: the hub's container scene, framed to the right of the title."""
    import streamlit.components.v1 as components

    components.html(page_html(LABEL.get(title, "Meridian"), title, sub), height=PAGE_HEIGHT)


def section(label: str) -> None:
    """Small yellow-dot label above a block, like the home page's section labels."""
    st.markdown(f"<span class='label sec-label'>{label}</span>", unsafe_allow_html=True)


def latest_details(store: Store) -> list[dict]:
    """Newest explanation per invoice across all runs (a re-run supersedes older ones)."""
    seen: dict[str, dict] = {}
    for run in reversed(store.list_runs(500)):  # oldest first, newer overwrite
        for no, d in store.details(run.id).items():
            seen[no] = d
    return list(seen.values())


def inr(v) -> str:
    if v is None or v == "":
        return "—"
    d = Decimal(str(v))
    sign = "-" if d < 0 else ""
    return f"{sign}₹{abs(d):,.2f}"


def hhmm(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %H:%M:%S") if ts else ""


def big(col, label: str, value: str, note: str = "") -> None:
    col.markdown(f"<div class='kpi'><div class='lbl'>{label}</div><div class='big'>{value}</div>"
                 + (f"<div class='lbl'>{note}</div>" if note else "") + "</div>", unsafe_allow_html=True)


def run_label(r: Run) -> str:
    when = datetime.fromtimestamp(r.created).strftime("%d %b %H:%M") if r.created else ""
    return f"{STATUS_ICON.get(r.status, '')}  {r.task_id} · {r.kind.replace('_', ' ')} · {when}"


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
