"""Recon: log in once, visit each portal area read-only, save what the pages look like.

Run it yourself (it needs the private credentials in .env):

    python harness/recon.py            # opens a visible browser
    python harness/recon.py --headless

When the portal asks for a one-time password, open the operator inbox YOURSELF and type the
code into the terminal. The script never opens the inbox and never submits any form other than
login / OTP / search. It opens one invoice, runs one POD search and, if there
is a plain link to it, opens the Raise Dispute page to read its fields (never fills or submits). Output goes to runs/recon/ (git-ignored): masked screenshots, grid headers,
a sample of rows, and the page's link/form/control inventory — enough to tune the client.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
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
      options: e.tagName === 'SELECT' ? Array.from(e.options).slice(0, 40).map(o => [o.value, o.text]) : undefined,
      value: (e.type === 'submit' || e.type === 'button') ? e.value : undefined,
    })),
  })),
  links_sample: Array.from(document.querySelectorAll('#body a')).slice(0, 30).map(a => ({text: a.innerText.trim(), href: a.getAttribute('href')})),
  buttons: Array.from(document.querySelectorAll('#body button, #body input[type=submit], #body input[type=button]'))
    .map(b => ({text: (b.innerText || b.value || '').trim(), id: b.id, name: b.name || '', onclick: (b.getAttribute('onclick') || '').slice(0, 80)})),
  headings: Array.from(document.querySelectorAll('#body h1, #body h2, #body h3, #body h4, #body legend')).map(h => h.innerText.trim()).slice(0, 20),
  text: (document.querySelector('#body') || document.body).innerText.slice(0, 1500),
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


async def capture(client: PortalClient, name: str) -> dict:
    shot = await client.screenshot(f"recon_{name}")
    grids = await client.grids()
    return {
        "screenshot": str(shot),
        "inventory": await client.page.evaluate(_INVENTORY_JS),
        "key_values": {k: ("[masked]" if PERSONAL.search(k) else v) for k, v in (await client.key_values()).items()},
        "grids": [{"id": g.id, "cls": g.cls, "headers": g.headers, "row_count": len(g.rows), "sample": g.rows[:4]} for g in grids],
    }


PERSONAL = re.compile(r"received|receiver|contact|phone|mobile|sign|driver|name", re.I)
DISPUTE_LINK = re.compile(r"raise|new dispute|create dispute|dispute this|log dispute", re.I)


async def deep(client: PortalClient, report: dict) -> None:
    """Read-only look at the pages behind the lists. Never fills or submits the dispute form."""
    inv_area = report["areas"].get("invoices", {})
    sample = next((g["sample"][0] for g in inv_area.get("grids", []) if g["sample"] and "__href" in g["sample"][0]), None)
    if sample is None:
        report["deep_error"] = "no invoice link in the list"
        return
    # 1) one invoice page
    await client.goto(sample["__href"])
    report["invoice_view"] = await capture(client, "invoice_view")
    report["invoice_view"]["opened"] = sample["__href"]
    links = report["invoice_view"]["inventory"]["links_sample"]
    # 2) one POD search, for a consignment on that invoice
    cons = None
    for g in report["invoice_view"]["grids"]:
        for row in g["sample"]:
            cons = next((v for v in row.values() if isinstance(v, str) and re.fullmatch(r"[A-Z]{2,4}-?\d{4,}", v.strip())), None)
            if cons:
                break
        if cons:
            break
    if cons:
        await client.goto("/Default.aspx")
        await client.open_menu("pods")
        await client._fill_search(shipment_id=cons)
        report["pod_result"] = await capture(client, "pod_result")
        report["pod_result"]["searched"] = cons
        report["pod_result"]["download_links"] = [l for l in report["pod_result"]["inventory"]["links_sample"]
                                                  if re.search(r"download|view|pdf|document|attach", l["text"], re.I)]
    # 3) where disputes are raised: a link on the invoice page or the dispute list. Plain GET links
    #    are opened to read the form; buttons are only listed, never clicked.
    disputes = report["areas"].get("disputes", {}).get("inventory", {})
    candidates = [l for l in links + disputes.get("links_sample", []) if l.get("href") and DISPUTE_LINK.search(l["text"] or "")]
    report["dispute_entry_points"] = {
        "links": candidates,
        "buttons_on_invoice": [b for b in report["invoice_view"]["inventory"]["buttons"] if DISPUTE_LINK.search(b["text"])],
        "buttons_on_list": [b for b in disputes.get("buttons", []) if DISPUTE_LINK.search(b["text"])],
    }
    href = next((c["href"] for c in candidates if not c["href"].lower().startswith("javascript")), None)
    if href:
        await client.goto(href)
        report["dispute_form"] = await capture(client, "dispute_form")
        report["dispute_form"]["opened"] = href
        report["dispute_form"]["note"] = "opened read-only; nothing was filled or submitted"


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
            try:
                await client.login()
            except Exception:
                path = await client.debug_dump("login_failure")
                print(f"\nLogin did not finish. Diagnostics saved to {OUT}/ ({path}). Tell Claude 'recon failed'.")
                raise
            await client.goto("/Default.aspx")
            home = {"screenshot": str(await client.screenshot("recon_home")), "inventory": await client.page.evaluate(_INVENTORY_JS)}
            report = {"home": home, "areas": {}}
            for area in MENU:
                try:
                    report["areas"][area] = await client.step(f"recon:{area}", lambda a=area: visit(client, a))
                except Exception as exc:  # keep going; record what failed
                    report["areas"][area] = {"error": f"{type(exc).__name__}: {exc}"}
            try:
                await client.step("recon:deep", lambda: deep(client, report))
            except Exception as exc:
                report["deep_error"] = f"{type(exc).__name__}: {exc}"
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
