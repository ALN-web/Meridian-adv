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
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, [data-testid="stMarkdownContainer"] { font-family: Manrope, system-ui, sans-serif; }
.stApp code, .mono { font-family: "IBM Plex Mono", monospace !important; }
.block-container { padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1240px; }
.stApp h1 { font-size: 2.1rem; font-weight: 600; letter-spacing: -.03em; padding: 0 0 .2rem; }
.stApp h3 { font-size: 1.15rem; font-weight: 600; letter-spacing: -.015em; padding-top: .6rem; }
[data-testid="stSidebar"] { background: #f5f5f3; border-right: 1px solid #e6e6e2; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
.stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a { border-radius: 999px; font-weight: 600; }
[data-testid="stDataFrame"] { border-radius: 10px; }
.sub { color: #8a8a84; margin: -.5rem 0 1.6rem; font-size: 1rem; }
.brand { display: flex; align-items: center; gap: 9px; font-weight: 800; letter-spacing: .04em; font-size: .95rem; margin: .2rem 0 .6rem; }
.brand i { display: inline-block; width: 6px; height: 17px; background: #f5c400; transform: skewX(-20deg); margin-right: -6px; }
.brand i + i { background: #0e0e0e; margin-right: 2px; }
.pill { display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: 999px; font-size: .78rem; font-weight: 600; margin: 0 4px 4px 0; white-space: nowrap; }
.p-ok { background: rgba(47,191,113,.14); color: #1d8a51; } .p-bad { background: rgba(229,72,77,.12); color: #c23338; }
.p-wait { background: rgba(245,196,0,.24); color: #6b5600; } .p-grey { background: #efefec; color: #44443f; }
.p-run { background: #0e0e0e; color: #fff; }
.kpi { border: 1px solid #e6e6e2; border-radius: 12px; padding: 12px 16px; height: 100%; }
.lbl { font-size: .8rem; color: #8a8a84; }
.big { font-size: 1.4rem; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; line-height: 1.35; }
.plan-row { padding: 5px 0; font-size: .92rem; display: flex; gap: 10px; align-items: center; color: #44443f; }
.plan-row b { width: 20px; height: 20px; border-radius: 50%; display: inline-grid; place-items: center; font-size: .7rem; background: #e8e8e4; color: #8a8a84; flex: none; }
.plan-row.done b { background: #0e0e0e; color: #fff; } .plan-row.now b { background: #f5c400; color: #1a1500; }
.plan-row.now { color: #0e0e0e; font-weight: 600; }
.muted { color: #8a8a84; font-size: .88rem; }
</style>
"""

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


def header(title: str, sub: str | None = None) -> None:
    st.title(title)
    if sub:
        st.markdown(f"<p class='sub'>{sub}</p>", unsafe_allow_html=True)


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
