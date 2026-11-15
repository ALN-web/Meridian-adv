"""System status: what is configured and reachable. Shows whether secrets are set, never their values."""
from __future__ import annotations

import importlib.util

import streamlit as st

from meridian.agent.modes import FAKE_BASE_URL, portal_reachable
from meridian.config import get_settings
from meridian.ui.common import ROOT, header


def _chromium() -> bool:
    try:
        from pathlib import Path

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def _row(label: str, ok: bool | None, value: str) -> str:
    cls = "p-ok" if ok else ("p-grey" if ok is None else "p-wait")
    word = "Ready" if ok else ("Optional" if ok is None else "Missing")
    return (f"<div style='display:flex;justify-content:space-between;align-items:center;padding:10px 0;"
            f"border-top:1px solid #e6e6e2'><span><b>{label}</b> <span class='muted'>{value}</span></span>"
            f"<span class='pill {cls}'>{word}</span></div>")


def render() -> None:
    header("System", "What's set up. Secrets show as set or missing, never their values.")
    s = get_settings()
    has = lambda v: bool(v.get_secret_value())  # noqa: E731
    lf = bool(s.langfuse_public_key and has(s.langfuse_secret_key))
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Portal**")
        st.markdown("".join([
            _row("Address", True, s.portal_base_url),
            _row("User", bool(s.portal_user), ""),
            _row("Password", has(s.portal_password), ""),
            _row("Team key", has(s.team_key), ""),
            _row("Speed limit", s.max_requests_per_second <= 2, f"{s.max_requests_per_second} req/s"),
        ]), unsafe_allow_html=True)
    with right:
        st.markdown("**Services**")
        csv = (ROOT / "data" / "meridian-shipments.csv").exists()
        st.markdown("".join([
            _row("Meridian records", csv, "data/meridian-shipments.csv" if csv else "fetched on first run"),
            _row("Playwright", bool(importlib.util.find_spec("playwright")), ""),
            _row("Langfuse", lf if lf else None, "local traces only" if not lf else s.langfuse_host),
            _row("LLM fallback", bool(s.llm_model) if s.llm_model else None, s.llm_model or "not used"),
        ]), unsafe_allow_html=True)

    st.write("")
    c = st.columns(3)
    if c[0].button("Check Chromium", width="stretch"):
        (st.success if _chromium() else st.error)("Chromium ready" if _chromium() else "Run: playwright install chromium")
    if c[1].button("Check fake portal", width="stretch"):
        ok, where = portal_reachable("fake")
        (st.success if ok else st.error)(where or FAKE_BASE_URL)
    if c[2].button("Check real portal", width="stretch", help="It sleeps when idle; the first call can take a minute."):
        with st.spinner("Waking the portal…"):
            ok, where = portal_reachable("live")
        (st.success if ok else st.error)(where)
