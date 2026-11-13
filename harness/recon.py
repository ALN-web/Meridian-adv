"""Recon: log in once, visit each portal area read-only, save what the pages look like.

Run it yourself (it needs the private credentials in .env):

    python harness/recon.py            # opens a visible browser
    python harness/recon.py --headless

When the portal asks for a one-time password, open the operator inbox YOURSELF and type the
code into the terminal. The script never opens the inbox and never submits any form other than
login / OTP / search. Output goes to runs/recon/ (git-ignored): masked screenshots, grid headers,
a sample of rows, and the page's link/form/control inventory — enough to tune the client.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meridian.config import get_settings  # noqa: E402
from meridian.portal.client import MENU, PortalClient  # noqa: E402
from meridian.portal.human import ConsoleHumanGate  # noqa: E402

OUT = Path("runs/recon")

_INVENTORY_JS = """
() => ({
  url: location.pathname + location.search,
  title: document.title,
  menu: Array.from(document.querySelectorAll('#menu a, nav a')).map(a => ({text: a.innerText.trim(), href: a.getAttribute('href')})),
  forms: Array.from(document.forms).map(f => ({
    action: f.getAttribute('action'), method: f.method,
    controls: Array.from(f.elements).map(e => ({
      tag: e.tagName, type: e.type, name: e.name, id: e.id,
      label: (e.labels && e.labels[0] ? e.labels[0].innerText.trim() : (e.previousElementSibling ? e.previousElementSibling.innerText : '') || '').slice(0, 60),
      options: e.tagName === 'SELECT' ? Array.from(e.options).slice(0, 40).map(o => o.text) : undefined,
      value: (e.type === 'submit' || e.type === 'button') ? e.value : undefined,
    })),
  })),
  links_sample: Array.from(document.querySelectorAll('#body a')).slice(0, 30).map(a => ({text: a.innerText.trim(), href: a.getAttribute('href')})),
})
"""


async def visit(client: PortalClient, area: str) -> dict:
    await client.goto("/Default.aspx")
    await client.open_menu(area)
    shot = await client.screenshot(f"recon_{area}")
    inventory = await client.page.evaluate(_INVENTORY_JS)
    grids = await client.grids()
    return {
        "area": area,
        "screenshot": str(shot),
        "inventory": inventory,
        "grids": [{"id": g.id, "cls": g.cls, "headers": g.headers, "row_count": len(g.rows), "sample": g.rows[:3]} for g in grids],
    }


async def main(headless: bool) -> None:
    from playwright.async_api import async_playwright

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    if not settings.portal_user or not settings.portal_password.get_secret_value():
        sys.exit("Set PORTAL_USER and PORTAL_PASSWORD in .env first.")
    OUT.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        client = PortalClient(settings, ConsoleHumanGate(), screenshot_dir=OUT, download_dir=OUT / "downloads")
        await client.start(browser)
        try:
            await client.login()
            await client.goto("/Default.aspx")
            home = {"screenshot": str(await client.screenshot("recon_home")), "inventory": await client.page.evaluate(_INVENTORY_JS)}
            report = {"home": home, "areas": {}}
            for area in MENU:
                try:
                    report["areas"][area] = await client.step(f"recon:{area}", lambda a=area: visit(client, a))
                except Exception as exc:  # keep going; record what failed
                    report["areas"][area] = {"error": f"{type(exc).__name__}: {exc}"}
            report["steps"] = client.log.steps
            report["retries"] = client.log.retries.retries
            report["human_steps"] = client.log.human_steps
            (OUT / "recon.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(f"\nSaved {OUT / 'recon.json'} and screenshots in {OUT}/")
            print("Check the screenshots for any visible personal data before sharing them.")
        finally:
            await client.close()
            await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    asyncio.run(main(ap.parse_args().headless))
