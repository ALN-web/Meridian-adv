"""System status: what is configured and reachable. Shows whether secrets are set, never their values."""
from __future__ import annotations

import importlib.util

import pandas as pd
import streamlit as st

from meridian.agent.modes import FAKE_BASE_URL, portal_reachable
from meridian.config import get_settings
from meridian.ui.common import ROOT, get_store


def _chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            from pathlib import Path

            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def render() -> None:
    st.title("System")
    s = get_settings()
    secret = lambda v: "set" if v.get_secret_value() else "missing"  # noqa: E731
    rows = [
        ("Portal URL", s.portal_base_url, ""),
        ("Portal user", "set" if s.portal_user else "missing", "from .env"),
        ("Portal password", secret(s.portal_password), "from .env, never shown"),
        ("Team key", secret(s.team_key), "from .env, never shown"),
        ("Rate limit", f"{s.max_requests_per_second} requests/s", "brief: at most 2"),
        ("LLM", s.llm_model or "not configured", "used only as a fallback"),
        ("Vision model", s.vision_model or "not configured", "for pages that don't match"),
        ("Langfuse", "set" if s.langfuse_public_key and s.langfuse_secret_key.get_secret_value() else "not configured", s.langfuse_host),
        ("Meridian records", "data/meridian-shipments.csv" if (ROOT / "data" / "meridian-shipments.csv").exists() else "will be fetched", ""),
        ("Playwright", "installed" if importlib.util.find_spec("playwright") else "missing", ""),
        ("Run store", str(get_store().path.relative_to(ROOT)), ""),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["item", "status", "note"]), hide_index=True, width="stretch")

    c = st.columns(3)
    if c[0].button("Check Chromium"):
        st.write("✅ Chromium installed" if _chromium() else "❌ run `playwright install chromium`")
    if c[1].button("Check fake portal"):
        ok, where = portal_reachable("fake")
        st.write(("✅ " if ok else "❌ ") + (where or FAKE_BASE_URL))
    if c[2].button("Check real portal", help="The real portal sleeps when idle; the first call can take a minute."):
        with st.spinner("Waking the portal…"):
            ok, where = portal_reachable("live")
        st.write(("✅ reachable: " if ok else "❌ ") + where)
