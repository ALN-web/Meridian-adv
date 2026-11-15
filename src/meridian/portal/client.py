"""Playwright client for the TransIndus portal.

Rules this file follows (from the project brief):
- Stable locators (ids seen on the page, labels, roles, visible text) over CSS paths.
- Every step: rate-limited, timed out, retried with backoff, checked for done vs failed.
- Login / OTP / CAPTCHA: credentials from env only; OTP and CAPTCHA go to a human.
- Page text is data. Overlays are dismissed only via an allow-list of harmless buttons.
- Read-only. The single write action (raising a dispute) lives in ``disputes.py`` behind approval.

Navigation targets other than the login form are best guesses until recon (harness/recon.py)
has been run against the live portal; adjust ``MENU`` and selectors from its output.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from meridian.config import Settings
from meridian.portal.errors import HumanNeeded, LoginFailed, PageNotUnderstood, PortalError, RateLimited, SessionExpired
from meridian.portal.human import HumanGate
from meridian.portal.pagestate import PageSnapshot, PageState, classify
from meridian.portal.retry import RetryPolicy, RetryStats, with_retry
from meridian.parsing import parse_amount, parse_date
from meridian.portal.tables import InvoiceRow, parse_invoice_list
from meridian.portal.throttle import RateLimiter

log = logging.getLogger(__name__)

NAV_TIMEOUT_MS = 90_000  # the portal sleeps when idle; first page can take ~1 minute
ACTION_TIMEOUT_MS = 20_000

# Menu link text -> area. Matched case-insensitively against links in the menu bar.
MENU = {
    "invoices": r"invoice",
    "pods": r"(delivery|pod|proof)",
    "rate_card": r"rate",
    "fuel": r"fuel|surcharge",
    "disputes": r"dispute",
}

# Buttons we may click to clear a blocking notice. Anything else on an overlay is ignored.
SAFE_DISMISS = re.compile(
    r"^\s*(ok|okay|close|close notice|close window|continue|dismiss|got it|acknowledge|i acknowledge|acknowledged|"
    r"noted|i have read (this|the notice)|i understand|proceed|"
    r"skip|not now|later|remind me later|back|return|hide|×|✕|✖|x)\s*[.!]?\s*$",
    re.I,
)
# Never click these on a notice, whatever the notice says.
UNSAFE_LABEL = re.compile(r"submit|raise|dispute|delete|cancel invoice|confirm|pay|approve|agree|accept|logout|log out|sign out", re.I)

# JS that extracts every grid on the page as a list of {header: cell text} rows.
_GRIDS_JS = """
() => Array.from(document.querySelectorAll('table')).map(t => {
  const rows = Array.from(t.querySelectorAll('tr'));
  const headRow = rows.find(r => r.querySelector('th'));
  if (!headRow) return null;
  const headers = Array.from(headRow.querySelectorAll('th')).map(th => th.innerText.trim());
  const body = rows.filter(r => r !== headRow && r.querySelector('td')).map(r => {
    const cells = Array.from(r.querySelectorAll('td'));
    const o = {};
    headers.forEach((h, i) => { o[h || ('col' + i)] = cells[i] ? cells[i].innerText.trim() : ''; });
    const a = r.querySelector('a[href]');
    if (a) o['__href'] = a.getAttribute('href');
    return o;
  });
  return {id: t.id || '', cls: t.className || '', headers, rows: body};
}).filter(Boolean)
"""

OVERLAY_SELECTOR = "#ovl, .modal, [role=dialog], [role=alertdialog]"

# A hidden overlay (display:none, zero size, transparent) must not count as blocking.
_IS_SHOWN_JS = """
const isShown = (e) => {
  for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
    const cs = getComputedStyle(n);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
  }
  const r = e.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
"""

_SNAPSHOT_JS = "() => { const OVERLAY_SEL = '" + OVERLAY_SELECTOR + "';" + _IS_SHOWN_JS + " return (" + """{
  title: document.title || '',
  text: (document.body ? document.body.innerText : '').slice(0, 5000),
  has_overlay: !!Array.from(document.querySelectorAll(OVERLAY_SEL)).find(isShown),
  has_password_field: !!document.querySelector('input[type=password]'),
  has_otp_field: !!document.querySelector('input[name*=otp i], input[id*=otp i], input[autocomplete=one-time-code]'),
  has_captcha: !!document.querySelector('[class*=captcha i], [id*=captcha i], iframe[src*=captcha i], img[src*=captcha i]'),
}); }
"""

# Everything clickable inside visible overlays, with the label a person would read.
_OVERLAY_INFO_JS = "() => { const OVERLAY_SEL = '" + OVERLAY_SELECTOR + "';" + _IS_SHOWN_JS + """
  const shown = Array.from(document.querySelectorAll(OVERLAY_SEL)).filter(isShown);
  const clickSel = 'button, a, input[type=button], input[type=submit], [role=button], [onclick], [aria-label], [title], [class*=close i], [id*=close i]';
  return shown.map((o, oi) => ({
    text: (o.innerText || '').slice(0, 400),
    controls: Array.from(o.querySelectorAll(clickSel)).filter(isShown).map((c, ci) => {
      c.setAttribute('data-meridian-ctl', oi + '-' + ci);
      return {
        key: oi + '-' + ci,
        tag: c.tagName,
        label: ((c.tagName === 'INPUT' ? c.value : c.innerText) || c.getAttribute('aria-label') || c.getAttribute('title') || '').trim().slice(0, 60),
        cls: (c.className && c.className.baseVal === undefined ? c.className : '').toString().slice(0, 60),
        id: c.id || '',
        type: c.type || '',
      };
    }),
  }));
}"""


# Mark cells that hold a person's name or phone so screenshots can mask them.
_MARK_PII_JS = r"""
() => {
  const phone = /(\+91[\s-]?)?[6-9]\d{9}\b|\b\d{3}[\s-]\d{3}[\s-]\d{4}\b/;
  const personLabel = /received\s*by|receiver|contact|signed\s*by|driver|name|mobile|phone|email/i;
  const cells = Array.from(document.querySelectorAll('td, span, div, p'));
  for (const el of cells) {
    if (el.children.length === 0 && phone.test(el.innerText || '')) el.setAttribute('data-meridian-mask', '1');
  }
  for (const tbl of document.querySelectorAll('table')) {
    const head = Array.from(tbl.querySelectorAll('th')).map(th => personLabel.test(th.innerText));
    if (head.some(Boolean)) {
      for (const tr of tbl.querySelectorAll('tr')) {
        Array.from(tr.querySelectorAll('td')).forEach((td, i) => { if (head[i]) td.setAttribute('data-meridian-mask', '1'); });
      }
    }
    for (const tr of tbl.querySelectorAll('tr')) {
      const tds = Array.from(tr.children);
      tds.forEach((c, i) => { if (personLabel.test(c.innerText || '') && tds[i + 1]) tds[i + 1].setAttribute('data-meridian-mask', '1'); });
    }
  }
}
"""


@dataclass
class Grid:
    id: str
    cls: str
    headers: list[str]
    rows: list[dict[str, str]]


@dataclass
class StepLog:
    steps: int = 0
    retries: RetryStats = field(default_factory=RetryStats)
    human_steps: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    sink: object = None  # optional callable(step, outcome, extra) — e.g. the run store

    page_fn: object = None  # optional callable() -> current page path

    def add(self, step: str, outcome: str, **extra) -> None:
        if callable(self.page_fn) and "page" not in extra:
            try:
                extra["page"] = self.page_fn()
            except Exception:
                pass
        self.steps += 1
        self.events.append({"step": step, "outcome": outcome, **extra})
        if callable(self.sink):
            try:
                self.sink(step, outcome, extra)
            except Exception:
                pass


class PortalClient:
    """One logged-in browser context. Create several (sharing one RateLimiter) for parallel runs."""

    def __init__(
        self,
        settings: Settings,
        human: HumanGate,
        limiter: RateLimiter | None = None,
        *,
        download_dir: str | Path = "runs/downloads",
        screenshot_dir: str | Path = "runs/screenshots",
        policy: RetryPolicy | None = None,
    ):
        self.settings = settings
        self.human = human
        self.limiter = limiter or RateLimiter(settings.max_requests_per_second)
        self.download_dir = Path(download_dir)
        self.screenshot_dir = Path(screenshot_dir)
        self.policy = policy or RetryPolicy()
        self.log = StepLog()
        self.page = None
        self._ctx = None
        self._login_failures = 0
        self.notice_wait_s = 15  # how long to wait for a notice that hides itself
        # Per-session caches. The real portal has no invoice-number or shipment search, so invoice
        # links are remembered from the list, and "which invoices bill shipment X" is answered by
        # reading every invoice once (shipment_index).
        self._inv_href: dict[str, str] = {}
        self._inv_cache: dict[str, tuple] = {}
        self._shipment_index: dict[str, list[InvoiceRow]] | None = None

    # ------------------------------------------------------------------ lifecycle

    async def start(self, browser) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._ctx = await browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 900})
        self._ctx.set_default_timeout(ACTION_TIMEOUT_MS)
        self._ctx.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        self.page = await self._ctx.new_page()
        from urllib.parse import urlparse

        self.log.page_fn = lambda: urlparse(self.page.url).path.lstrip("/") or "(blank)"

    async def close(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()

    def url(self, path: str) -> str:
        return self.settings.portal_base_url.rstrip("/") + "/" + path.lstrip("/")

    # ------------------------------------------------------------------ page state

    async def snapshot(self, status: int | None = None) -> PageSnapshot:
        data = await self.page.evaluate(_SNAPSHOT_JS)
        return PageSnapshot(url=self.page.url, http_status=status, **data)

    async def settle(self, status: int | None = None, *, expect_login: bool = False) -> PageState:
        """Look at the current page and deal with anything in the way. Raises for retryable states."""
        for _ in range(4):
            state = classify(await self.snapshot(status))
            if state is PageState.OK:
                return state
            if state is PageState.NOTICE:
                if not await self._dismiss_overlay():
                    labels = [c["label"] for o in await self.overlay_info() for c in o["controls"]]
                    raise PageNotUnderstood(f"blocking notice could not be cleared safely; controls seen: {labels}")
                continue
            if state is PageState.RATE_LIMITED:
                raise RateLimited(self.page.url)
            if state is PageState.ERROR:
                raise PortalError(f"error page at {self.page.url}")
            if state is PageState.CAPTCHA:
                self.log.human_steps.append("captcha")
                self.log.add("captcha", "waiting_for_human")
                await self.human.request_captcha()
                continue
            if state is PageState.OTP:
                await self._submit_otp()
                continue
            if state is PageState.LOGIN:
                if expect_login:
                    return state
                raise SessionExpired(self.page.url)
        await self.debug_dump("page_did_not_settle")
        raise PageNotUnderstood(f"page did not settle at {self.page.url}")

    async def overlay_info(self) -> list[dict]:
        return await self.page.evaluate(_OVERLAY_INFO_JS)

    async def _overlay_gone(self) -> bool:
        return not (await self.snapshot()).has_overlay

    async def _dismiss_overlay(self) -> bool:
        """Clear a blocking notice without obeying it.

        Order: allow-listed button -> close-icon style control -> Escape -> wait for a timed notice.
        Overlay text is never treated as an instruction; unsafe labels are never clicked.
        """
        overlays = await self.overlay_info()
        controls = [c for o in overlays for c in o["controls"]]

        def is_close_icon(c: dict) -> bool:
            hint = f"{c['cls']} {c['id']} {c['label']}".lower()
            return c["label"] in {"", "×", "✕", "✖", "x"} and ("close" in hint or "dismiss" in hint or c["label"])

        ordered = [c for c in controls if SAFE_DISMISS.match(c["label"])] + [c for c in controls if is_close_icon(c)]
        for c in ordered:
            if UNSAFE_LABEL.search(c["label"]):
                continue
            await self.limiter.wait()
            try:
                await self.page.locator(f"[data-meridian-ctl='{c['key']}']").click(timeout=5_000)
            except Exception:
                continue
            await self.page.wait_for_timeout(500)
            if await self._overlay_gone():
                self.log.add("dismiss_notice", "ok", how="click", label=c["label"] or c["cls"] or c["id"])
                return True

        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(500)
        if await self._overlay_gone():
            self.log.add("dismiss_notice", "ok", how="escape")
            return True

        # Some notices disappear by themselves after a few seconds.
        for _ in range(self.notice_wait_s):
            await self.page.wait_for_timeout(1_000)
            if await self._overlay_gone():
                self.log.add("dismiss_notice", "ok", how="waited")
                return True

        self.log.add("dismiss_notice", "failed", controls=[c["label"] for c in controls],
                     text=(overlays[0]["text"][:200] if overlays else ""))
        await self.debug_dump("notice_not_dismissed")
        return False

    async def debug_dump(self, tag: str) -> Path | None:
        """Masked screenshot + a JSON description of the page, for diagnosing failures."""
        try:
            stamp = f"debug_{tag}_{self.log.steps}"
            shot = await self.screenshot(stamp)
            info = {
                "url": self.page.url,
                "title": await self.page.title(),
                "snapshot": (await self.snapshot()).__dict__,
                "overlays": await self.overlay_info(),
                "forms": await self.page.evaluate(
                    "() => Array.from(document.querySelectorAll('input, select, button, a')).slice(0, 60).map(e => "
                    "({tag: e.tagName, type: e.type || '', id: e.id, name: e.name || '', "
                    "label: ((e.tagName === 'INPUT' ? (e.type === 'password' ? '' : e.value) : e.innerText) || '').trim().slice(0, 60)}))"
                ),
            }
            info["snapshot"]["text"] = info["snapshot"]["text"][:1500]
            path = self.screenshot_dir / f"{stamp}.json"
            path.write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
            log.info("debug snapshot saved: %s and %s", shot, path)
            return path
        except Exception as exc:  # diagnostics must never mask the real failure
            log.warning("debug dump failed: %s", exc)
            return None

    # ------------------------------------------------------------------ login

    async def login(self) -> None:
        async def attempt():
            await self.limiter.wait()
            resp = await self.page.goto(self.url("/Login.aspx"), wait_until="domcontentloaded")
            state = await self.settle(resp.status if resp else None, expect_login=True)
            if state is PageState.OK:
                return  # already logged in
            await self.page.locator("#txtUser").fill(self.settings.portal_user)
            await self.page.locator("#txtPass").fill(self.settings.portal_password.get_secret_value())
            await self.limiter.wait()
            await self.page.locator("#btnLogin").click()
            await self.page.wait_for_load_state("domcontentloaded")
            state = await self.settle(expect_login=True)
            if state is PageState.LOGIN:
                self._login_failures += 1
                if self._login_failures >= 2:
                    # Repeated failures trigger a CAPTCHA; stop and ask a human instead.
                    raise LoginFailed("login rejected twice; check credentials in .env")
                raise PortalError("login did not complete")
            self._login_failures = 0

        await with_retry("login", attempt, policy=self.policy, stats=self.log.retries)
        self.log.add("login", "ok")

    async def _submit_otp(self) -> None:
        self.log.human_steps.append("otp")
        self.log.add("otp", "waiting_for_human")
        await self.debug_dump("otp_page")          # record what the OTP page looks like (masked)
        code = await self.human.request_otp()
        if not code:
            raise HumanNeeded("otp", "no code provided")
        # The person may take a while; the page can move on meanwhile (e.g. straight to the home page).
        if classify(await self.snapshot()) is not PageState.OTP:
            self.log.add("otp", "not_needed", detail="page moved on before the code was entered")
            return
        field_ = self.page.locator("input[name*=otp i], input[id*=otp i], input[autocomplete=one-time-code]")
        if await field_.count() == 0:
            field_ = self.page.locator("input[type=text]:visible, input[type=number]:visible, input[type=password]:visible")
        try:
            await field_.first.wait_for(state="visible", timeout=10_000)
        except Exception:
            pass
        if await field_.count() == 0:
            if classify(await self.snapshot()) is not PageState.OTP:
                self.log.add("otp", "not_needed", detail="no OTP box; already past the OTP step")
                return
            await self.debug_dump("otp_field_not_found")
            raise PageNotUnderstood("OTP page without an input field")
        field_ = field_.first
        await field_.fill(code)
        await self.limiter.wait()
        form = field_.locator("xpath=ancestor::form[1]")
        scope = form if await form.count() else self.page
        submit = scope.locator("input[type=submit], button[type=submit], button")
        await self.limiter.wait()
        async with self.page.expect_navigation(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS):
            if await submit.count():
                await submit.first.click()
            else:
                await field_.press("Enter")
        self.log.add("otp", "submitted")

    # ------------------------------------------------------------------ navigation + reading

    async def step(self, name: str, fn):
        """Run a read step with rate limiting, retries and re-login on session expiry."""

        async def guarded():
            await self.limiter.wait()
            return await fn()

        result = await with_retry(
            name,
            guarded,
            policy=self.policy,
            stats=self.log.retries,
            on_session_expired=self.login,
            on_rate_limited=self.limiter.back_off,
        )
        self.log.add(name, "ok")
        return result

    async def goto(self, path_or_url: str) -> None:
        url = path_or_url if path_or_url.startswith("http") else self.url(path_or_url)
        await self.limiter.wait()  # every page load counts against the 2 requests/second limit
        resp = await self.page.goto(url, wait_until="domcontentloaded")
        await self.settle(resp.status if resp else None)

    async def open_menu(self, area: str) -> None:
        if self.page.url in ("", "about:blank") or await self.page.locator("#menu a, nav a").count() == 0:
            await self.goto("/Default.aspx")
        pattern = re.compile(MENU[area], re.I)
        link = self.page.locator("#menu a").filter(has_text=pattern).first
        if await link.count() == 0:
            link = self.page.get_by_role("link", name=pattern).first
        if await link.count() == 0:
            raise PageNotUnderstood(f"menu link for {area!r} not found")
        await self.limiter.wait()
        await link.click()
        await self.page.wait_for_load_state("domcontentloaded")
        await self.settle()

    async def grids(self) -> list[Grid]:
        return [Grid(**g) for g in await self.page.evaluate(_GRIDS_JS)]

    async def main_grid(self, must_have: str) -> Grid:
        """The grid whose headers mention ``must_have`` (regex)."""
        pat = re.compile(must_have, re.I)
        for g in await self.grids():
            if any(pat.search(h) for h in g.headers):
                return g
        raise PageNotUnderstood(f"no grid with a column like {must_have!r}")

    async def _next_page(self, current: int | None = None) -> bool:
        """Go to the next page of a grid. Handles 'Next', 'Next >', '>' and numbered pagers (1 2 3)."""
        nxt = self.page.get_by_role("link", name=re.compile(r"^\s*(next\s*(page)?\s*[>»›]*|[>»›]{1,2})\s*$", re.I))
        if await nxt.count() == 0:
            nxt = self.page.locator("input[type=submit][value*=Next i], input[type=button][value*=Next i]")
        if await nxt.count() == 0 and current is not None:
            nxt = self.page.locator("table a, .pager a, tr.pager a").filter(
                has_text=re.compile(rf"^\s*{current + 1}\s*$"))
        if await nxt.count() == 0 or not await nxt.first.is_enabled():
            return False
        before = await self.page.evaluate("() => document.body.innerText.length + location.href")
        await self.limiter.wait()
        await nxt.first.click()
        await self.page.wait_for_load_state("domcontentloaded")
        await self.settle()
        after = await self.page.evaluate("() => document.body.innerText.length + location.href")
        return after != before

    # ------------------------------------------------------------------ invoices

    async def search_invoices(self, lane: str | None = None, month: str | None = None, status: str | None = None,
                              *, invoice_no: str | None = None) -> list[InvoiceRow]:
        """Invoice list with pagination. ``month`` is YYYY-MM (invoice-date month).

        Filters the portal doesn't offer (the real one has no invoice-number box) are applied in
        code, so the answer is the same either way.
        """

        async def run():
            await self.open_menu("invoices")
            await self._fill_search(lane=lane, month=month, status=status, invoice_no=invoice_no)
            rows: list[InvoiceRow] = []
            seen: set[str] = set()
            for page_no in range(1, 201):  # hard stop against pagination loops
                if re.search(r"no records found|no invoices found", await self.page.inner_text("body"), re.I):
                    break
                grid = await self.main_grid(r"invoice")
                for r in parse_invoice_list(grid.rows):
                    if r.invoice_no not in seen:
                        seen.add(r.invoice_no)
                        rows.append(r)
                self._remember_links(grid.rows)
                if not await self._next_page(page_no):
                    break
            return rows

        rows = await self.step(f"search_invoices:{lane or ''}:{month or ''}:{invoice_no or ''}", run)
        # Filter again in code — never trust the portal's filter alone.
        if lane:
            rows = [r for r in rows if r.lane is None or r.lane == lane]
        if month:
            rows = [r for r in rows if r.invoice_date is None or r.invoice_date.strftime("%Y-%m") == month]
        if invoice_no:
            rows = [r for r in rows if r.invoice_no == invoice_no]
        return rows

    def _remember_links(self, grid_rows: list[dict[str, str]]) -> None:
        for r in grid_rows:
            href = r.get("__href")
            no = next((v.strip() for h, v in r.items() if re.search(r"invoice\s*(no|number|#)", h, re.I) and v), None)
            if href and no:
                self._inv_href[no] = href

    async def _set_control(self, label_pat: str, name_hint: str, value: str) -> bool:
        pat = re.compile(label_pat, re.I)
        ctl = self.page.get_by_label(pat)
        if await ctl.count() == 0:
            ctl = self.page.locator(f"select[name*={name_hint} i], input[name*={name_hint} i], "
                                    f"select[id*={name_hint} i], input[id*={name_hint} i]")
        if await ctl.count() == 0:
            return False
        ctl = ctl.first
        tag = await ctl.evaluate("e => e.tagName")
        if tag == "SELECT":
            options = await ctl.evaluate("e => Array.from(e.options).map(o => [o.value, o.text])")
            v = value.lower()
            match = next((val for val, t in options if v in (val.lower(), t.strip().lower())), None)
            if match is None:
                match = next((val for val, t in options if val and v in t.lower()), None)
            if match is None:
                return False
            await ctl.select_option(match)
        else:
            await ctl.fill(value)
        return True

    async def _click_search(self) -> None:
        button = self.page.get_by_role("button", name=re.compile(r"^\s*(search|go|find|show)\b", re.I))
        if await button.count() == 0:
            button = self.page.locator("input[type=submit][value*=Search i], input[type=submit][value*=Go i]")
        if await button.count():
            await self.limiter.wait()
            await button.first.click()
            await self.page.wait_for_load_state("domcontentloaded")
            await self.settle()

    async def _fill_search(self, *, lane=None, month=None, status=None, invoice_no=None, shipment_id=None) -> set[str]:
        """Fill whatever search controls exist (labels first, then name/id hints).
        Returns the filters that were actually set; results are always re-filtered in code."""
        applied: set[str] = set()
        if lane and await self._set_control(r"\blane\b|route", "lane", lane):
            applied.add("lane")
        if month:
            from datetime import date as _d

            y, m = map(int, month.split("-"))
            first = _d(y, m, 1)
            # The real portal lists "October 2026"; older builds used "Oct-26".
            for v in (month, first.strftime("%B %Y"), first.strftime("%b-%y"), first.strftime("%b %Y")):
                if await self._set_control(r"month|period", "month", v):
                    applied.add("month")
                    break
        if status and await self._set_control(r"status", "status", status):
            applied.add("status")
        if invoice_no and await self._set_control(r"invoice\s*(no|number|#)", "invoice", invoice_no):
            applied.add("invoice_no")
        if shipment_id:
            # The real POD page names its box txtCons (consignment).
            for hint in ("shipment", "cons", "docket"):
                if await self._set_control(r"shipment|consignment|docket", hint, shipment_id):
                    applied.add("shipment_id")
                    break
        await self._click_search()
        return applied

    async def key_values(self) -> dict[str, str]:
        """Label/value pairs from two-cell rows (``<th>Label</th><td>value</td>``)."""
        return await self.page.evaluate(
            """() => { const o = {}; document.querySelectorAll('tr').forEach(tr => {
                 const c = tr.children; if (c.length === 2 && c[0].tagName === 'TH' && c[1].tagName === 'TD')
                   o[c[0].innerText.trim().replace(/:$/, '')] = c[1].innerText.trim(); }); return o; }"""
        )

    async def open_invoice(self, invoice_no: str):
        """Invoice header, lines and credit notes (and its PDF) as an engine ``Invoice``."""
        from meridian.portal.tables import parse_invoice_lines
        from meridian.reconcile.types import Invoice

        if invoice_no in self._inv_cache:
            return self._inv_cache[invoice_no]
        if invoice_no not in self._inv_href:
            await self.search_invoices(invoice_no=invoice_no)  # fills the link cache
        href = self._inv_href.get(invoice_no)
        if href is None:
            return None, None

        async def run():
            await self.goto(href)
            if re.search(r"invoice .{0,40}not found", await self.page.inner_text("body"), re.I):
                return None
            kv = {k.lower(): v for k, v in (await self.key_values()).items()}
            grids = await self.grids()
            lines_grid = next((g for g in grids if any(re.search(r"shipment|consignment", h, re.I) for h in g.headers)), None)
            credit_grid = next((g for g in grids if any(re.search(r"credit", h, re.I) for h in g.headers)), None)
            if lines_grid is None:
                raise PageNotUnderstood(f"no lines grid on invoice {invoice_no}")
            lines = parse_invoice_lines(lines_grid.rows)
            credits = []
            if credit_grid is not None:
                amt_col = next((h for h in credit_grid.headers if re.search(r"amount", h, re.I)), None)
                credits = [parse_amount(r[amt_col]) for r in credit_grid.rows if amt_col and r.get(amt_col)]
            total_txt = next((v for k, v in kv.items() if re.search(r"invoice total|grand total|net amount", k)), None)
            if total_txt is None:
                raise PageNotUnderstood(f"no invoice total on {invoice_no}")
            return Invoice(
                invoice_no=invoice_no,
                invoice_date=parse_date(next(v for k, v in kv.items() if "date" in k)),
                lane=next((v for k, v in kv.items() if k in ("lane", "route")), ""),
                status=next((v for k, v in kv.items() if "status" in k), "Open").title(),
                total=parse_amount(total_txt),
                lines=tuple(lines),
                credit_notes=tuple(credits),
            )

        inv = await self.step(f"open_invoice:{invoice_no}", run)
        if inv is None:
            return None, None
        pdf = None
        link = self.page.get_by_role("link", name=re.compile(r"download.*pdf|pdf|print", re.I))
        if await link.count():
            try:
                pdf = await self.download(link.first, f"INV_{invoice_no}")
                self.log.add(f"invoice_pdf:{invoice_no}", "ok", path=str(pdf))
            except Exception as exc:  # the PDF is evidence, not required for the numbers
                self.log.add(f"invoice_pdf:{invoice_no}", "failed", error=type(exc).__name__)
        self._inv_cache[invoice_no] = (inv, pdf)
        return inv, pdf

    async def shipment_index(self, on_progress=None) -> dict[str, list[InvoiceRow]]:
        """shipment id -> every invoice row (any status) that bills it.

        The portal can't search invoices by shipment, so this reads each invoice once per session.
        Invoices are cached, so a reconcile run that follows pays nothing extra for them.
        """
        if self._shipment_index is not None:
            return self._shipment_index
        rows = await self.search_invoices()
        index: dict[str, list[InvoiceRow]] = {}
        for n, row in enumerate(rows, 1):
            inv, _ = await self.open_invoice(row.invoice_no)
            if on_progress:
                on_progress(n, len(rows))
            if inv is None:
                raise PageNotUnderstood(f"invoice {row.invoice_no} listed but could not be opened")
            for line in inv.lines:
                index.setdefault(line.shipment_id, []).append(row)
        self.log.add("shipment_index", "ok", invoices=len(rows), shipments=len(index))
        self._shipment_index = index
        return index

    async def invoices_billing(self, shipment_id: str) -> list[InvoiceRow]:
        """Every invoice (any status) with a line for this shipment."""
        return list((await self.shipment_index()).get(shipment_id, []))

    async def get_pod(self, shipment_id: str):
        """Delivery proof for one shipment -> (Pod | None, pdf path | None).

        Dates come from the page; if the page only says "see attached", they are read from the
        PDF. A PDF with no readable text (a scan) gives ``confident=False`` — never a guess.
        """
        from meridian.portal.pdftext import pod_dates_from_pdf
        from meridian.reconcile.types import Pod

        async def run():
            await self.open_menu("pods")
            if "shipment_id" not in await self._fill_search(shipment_id=shipment_id):
                raise PageNotUnderstood("POD search box not found")
            body = await self.page.inner_text("body")
            if re.search(r"no (delivery proof|pod|records?) found", body, re.I):
                return None
            kv = {k.lower(): v for k, v in (await self.key_values()).items()}
            if not kv:
                raise PageNotUnderstood(f"POD page for {shipment_id} has no details")
            prom = next((v for k, v in kv.items() if re.search(r"promised|due|expected", k)), "")
            deliv = next((v for k, v in kv.items() if re.search(r"delivered|delivery date|actual", k)), "")
            return prom, deliv

        found = await self.step(f"pod:{shipment_id}", run)
        if found is None:
            return None, None
        prom, deliv = found
        pdf = None
        link = self.page.get_by_role("link", name=re.compile(r"download|document|attachment", re.I))
        if await link.count():
            try:
                pdf = await self.download(link.first, f"POD_{shipment_id}")
            except Exception as exc:
                self.log.add(f"pod_pdf:{shipment_id}", "failed", error=type(exc).__name__)

        def to_date(t):
            try:
                return parse_date(t)
            except ValueError:
                return None

        p, dl = to_date(prom), to_date(deliv)
        if p and dl:
            return Pod(shipment_id, p, dl, confident=True), pdf
        if pdf is not None:
            p2, d2 = pod_dates_from_pdf(pdf)
            if p2 and d2:
                self.log.add(f"pod_pdf:{shipment_id}", "dates_from_pdf")
                return Pod(shipment_id, p2, d2, confident=True), pdf
        self.log.add(f"pod:{shipment_id}", "unreadable", detail="dates not on page and not readable from document")
        return Pod(shipment_id, None, None, confident=False), pdf

    async def rate_card(self):
        from meridian.portal.tables import parse_rate_card

        async def run():
            await self.open_menu("rate_card")
            return parse_rate_card((await self.main_grid(r"rate")).rows)

        return await self.step("rate_card", run)

    async def fuel_surcharge(self):
        from meridian.portal.tables import parse_fuel_surcharge

        async def run():
            await self.open_menu("fuel")
            return parse_fuel_surcharge((await self.main_grid(r"surcharge|fuel|%")).rows)

        return await self.step("fuel_surcharge", run)

    async def dispute_list(self) -> list[dict[str, str]]:
        """Rows of the portal's dispute list (raw header -> text)."""

        async def run():
            await self.open_menu("disputes")
            if re.search(r"no disputes", await self.page.inner_text("body"), re.I):
                return []
            try:
                g = await self.main_grid(r"dispute")
            except PageNotUnderstood:
                return []
            rows = list(g.rows)
            while await self._next_page():
                rows += (await self.main_grid(r"dispute")).rows
            return rows

        return await self.step("dispute_list", run)

    @staticmethod
    def disputed_invoices(rows: list[dict[str, str]]) -> set[str]:
        out = set()
        for r in rows:
            for h, v in r.items():
                if re.search(r"invoice", h, re.I) and v:
                    out.add(v.strip())
        return out

    async def submit_dispute(self, invoice_no: str, reasons: list[str], expected_amount) -> str:
        """Fill and submit the dispute form ONCE. No automatic retry — this is a write.

        Caller must have checked the dispute list first and must check it again afterwards.
        Returns the portal's message text (not proof by itself).
        """
        await self.open_menu("disputes")
        link = self.page.get_by_role("link", name=re.compile(r"raise|new dispute|create", re.I))
        if await link.count():
            await self.limiter.wait()
            await link.first.click()
            await self.page.wait_for_load_state("domcontentloaded")
            await self.settle()
        if not await self._set_control(r"invoice", "invoice", invoice_no):
            raise PageNotUnderstood("dispute form: invoice field not found")
        from meridian.portal.tables import REASON_HINTS, REASON_LABELS

        for r in reasons:
            box = self.page.locator(f"input[type=checkbox][value='{r}']")
            if await box.count() == 0 and r in REASON_LABELS:
                box = self.page.get_by_label(REASON_LABELS[r], exact=True)
            if await box.count() == 0:
                box = self.page.get_by_label(r, exact=True)
            if await box.count() == 0 and r in REASON_HINTS:
                hinted = self.page.get_by_label(re.compile(REASON_HINTS[r], re.I))
                # Only use a fuzzy match when exactly one box fits — never guess between two.
                if await hinted.count() == 1:
                    box = hinted
            if await box.count() == 0:
                raise PageNotUnderstood(f"dispute form: no checkbox for {r}")
            await box.first.check()
        if not await self._set_control(r"amount", "amount", f"{expected_amount:.2f}"):
            raise PageNotUnderstood("dispute form: amount field not found")
        await self.screenshot(f"dispute_before_submit_{invoice_no}")
        submit = self.page.get_by_role("button", name=re.compile(r"submit|raise|save", re.I))
        if await submit.count() == 0:
            raise PageNotUnderstood("dispute form: no submit button")
        await self.limiter.wait()
        await submit.first.click()
        await self.page.wait_for_load_state("domcontentloaded")
        await self.screenshot(f"dispute_after_submit_{invoice_no}")
        msg = (await self.page.inner_text("body"))[:400]
        self.log.add(f"dispute_submit:{invoice_no}", "submitted", message=msg[:120])
        return msg

    # ------------------------------------------------------------------ evidence

    async def screenshot(self, name: str) -> Path:
        """Masked screenshot: login fields and anything looking like a phone number or person are hidden."""
        path = self.screenshot_dir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', name)}.png"
        await self.page.evaluate(_MARK_PII_JS)
        masks = [
            self.page.locator("input[type=password]"),
            self.page.locator("#txtUser"),
            self.page.locator("[data-meridian-mask]"),
        ]
        await self.page.screenshot(path=str(path), full_page=True, mask=masks)
        return path

    async def download(self, trigger_locator, name: str) -> Path:
        async with self.page.expect_download() as info:
            await self.limiter.wait()
            await trigger_locator.click()
        dl = await info.value
        target = self.download_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + Path(dl.suggested_filename).suffix)
        await dl.save_as(str(target))
        return target
