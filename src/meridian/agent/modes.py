"""Which portal a run talks to, and how to start a runner for it.

  demo  in-process simulation (no browser)                       — DemoRunner
  fake  local fake portal in a real browser (python -m meridian.fakeportal.server)  — LiveRunner
  live  the real TransIndus portal in a real browser (needs .env, and recon first) — LiveRunner
"""
from __future__ import annotations

import os

from pydantic import SecretStr

from meridian.agent.planner import Plan
from meridian.config import Settings, get_settings
from meridian.store import Store

FAKE_BASE_URL = os.environ.get("FAKE_PORTAL_URL", "http://127.0.0.1:8600")
MODES = {"demo": "Demo (simulated, no browser)", "fake": "Fake portal (local, real browser)", "live": "Real TransIndus portal"}


def fake_settings() -> Settings:
    base = get_settings()
    return base.model_copy(update={
        "portal_base_url": FAKE_BASE_URL,
        "portal_user": os.environ.get("FAKE_PORTAL_USER", "meridian.ap"),
        "portal_password": SecretStr(os.environ.get("FAKE_PORTAL_PASSWORD", "fake-portal-pass")),
    })


def start_runner(mode: str, store: Store, run_id: str, plan: Plan, task_id: str, *, headless: bool = True):
    if mode == "demo":
        from meridian.agent.demo import DemoRunner

        return DemoRunner(store, run_id, plan, task_id).start()
    from meridian.agent.live import LiveRunner

    settings = fake_settings() if mode == "fake" else get_settings()
    return LiveRunner(store, run_id, plan, task_id, settings=settings, headless=headless).start()


def portal_reachable(mode: str) -> tuple[bool, str]:
    if mode == "demo":
        return True, ""
    import httpx

    url = FAKE_BASE_URL if mode == "fake" else get_settings().portal_base_url
    try:
        httpx.get(url.rstrip("/") + "/Login.aspx", timeout=5 if mode == "fake" else 75)
        return True, url
    except Exception as exc:
        hint = " Start it with: python -m meridian.fakeportal.server" if mode == "fake" else ""
        return False, f"{url} not reachable ({type(exc).__name__}).{hint}"
