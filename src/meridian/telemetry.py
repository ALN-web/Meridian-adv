"""Tracing: one trace per task, one span per step (page, action, outcome, retries, time).

- Sends to Langfuse when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set (SDK v5, OpenTelemetry based).
- Always writes a local copy to runs/traces/<trace_id>.jsonl, so traces exist and show in the UI
  even without Langfuse.
- Write actions (dispute submit) get their screenshot attached; screenshots are masked in the browser
  before capture (login fields, names, phone numbers).
- Everything sent passes through ``scrub``: portal user, password, team key, phone numbers,
  e-mail addresses and "Received by <name>" are replaced. OTP codes are never logged anywhere.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meridian.config import Settings, get_settings

log = logging.getLogger(__name__)
TRACE_DIR = Path("runs/traces")

_PHONE = re.compile(r"(?<!\d)(\+91[\s-]?)?[6-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PERSON = re.compile(r"(?i)(received\s*by|receiver|contact\s*person|signed\s*by|driver)\s*[:=]?\s*[A-Z][\w.]*(\s+[A-Z][\w.]*){0,3}")

# Which portal page a step name belongs to (live runs report the real page path instead).
PAGE_OF = [
    (r"^(open_portal|login|otp|captcha)", "Login.aspx"),
    (r"^search_invoices|^missing:", "Invoices.aspx"),
    (r"^(open_invoice|invoice(_pdf)?):", "Invoice.aspx"),
    (r"^pod(_pdf)?:", "Pods.aspx"),
    (r"^rate_card", "RateCard.aspx"),
    (r"^fuel", "Fuel.aspx"),
    (r"^dispute_list|^dispute_submit|^dispute:", "Disputes.aspx"),
    (r"^dismiss_notice", "(notice overlay)"),
    (r"^reconcile:|^billing_history|^load_meridian", "(rules engine, no page)"),
    (r"^approvals|^approval", "(operator screen)"),
]


def page_for(step: str) -> str:
    for pat, page in PAGE_OF:
        if re.search(pat, step):
            return page
    return ""


class Scrubber:
    def __init__(self, settings: Settings):
        self.secrets = [v for v in (settings.portal_user, settings.portal_password.get_secret_value(),
                                    settings.team_key.get_secret_value()) if v and len(v) >= 4]

    def text(self, s: str) -> str:
        for v in self.secrets:
            s = s.replace(v, "[redacted]")
        s = _PHONE.sub("[phone]", s)
        s = _EMAIL.sub("[email]", s)
        s = _PERSON.sub(lambda m: f"{m.group(1)} [person]", s)
        return s

    def __call__(self, data: Any = None, **_: Any) -> Any:
        """Works as Langfuse's ``mask`` hook and for local records."""
        if isinstance(data, str):
            return self.text(data)
        if isinstance(data, dict):
            return {k: self(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [self(v) for v in data]
        return data


_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def langfuse_client(settings: Settings):
    """Shared Langfuse client, or None when not configured / not installed."""
    global _CLIENT
    if not (settings.langfuse_public_key and settings.langfuse_secret_key.get_secret_value()):
        return None
    with _CLIENT_LOCK:
        if _CLIENT is None:
            try:
                from langfuse import Langfuse

                _CLIENT = Langfuse(public_key=settings.langfuse_public_key,
                                   secret_key=settings.langfuse_secret_key.get_secret_value(),
                                   host=settings.langfuse_host, mask=Scrubber(settings),
                                   environment="meridian-agent")
            except Exception as exc:  # tracing must never break a task
                log.warning("Langfuse disabled: %s", exc)
                _CLIENT = False
        return _CLIENT or None


def new_trace_id(seed: str | None = None) -> str:
    try:
        from langfuse import Langfuse

        return Langfuse.create_trace_id(seed=seed)
    except Exception:
        return uuid.uuid4().hex


class TaskTracer:
    """One trace for one task run. Feed it steps; it writes locally and (optionally) to Langfuse."""

    def __init__(self, run_id: str, task_id: str, task_text: str, kind: str, mode: str,
                 settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.scrub = Scrubber(self.settings)
        self.run_id, self.task_id, self.kind, self.mode = run_id, task_id, kind, mode
        self.trace_id = new_trace_id(seed=f"{run_id}-{time.time()}")
        self.url: str | None = None
        self.t_last = time.time()
        self.t0 = self.t_last
        self.spans = 0
        self._lock = threading.Lock()
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        self.path = TRACE_DIR / f"{self.trace_id}.jsonl"
        self._write({"type": "trace", "trace_id": self.trace_id, "name": f"{task_id} · {kind}", "run_id": run_id,
                     "task_id": task_id, "kind": kind, "mode": mode, "input": self.scrub(task_text),
                     "start": _iso(self.t0)})
        self.lf = langfuse_client(self.settings)
        self.root = None
        if self.lf is not None:
            try:
                self.root = self.lf.start_observation(
                    trace_context={"trace_id": self.trace_id}, name=f"task {task_id} · {kind}", as_type="agent",
                    input={"task": task_text, "kind": kind}, metadata={"run_id": run_id, "mode": mode})
            except Exception as exc:
                log.warning("Langfuse trace start failed: %s", exc)
                self.root = None
            if self.root is not None:
                try:  # the link is nice to have; a failure here must not drop the trace
                    self.url = self.lf.get_trace_url(trace_id=self.trace_id)
                except Exception as exc:
                    log.info("Langfuse trace URL unavailable: %s", exc)

    # ------------------------------------------------------------------ store listener interface

    def on_step(self, step: str, outcome: str, detail: str = "", retries: int = 0,
                duration_ms: int | None = None, page: str | None = None) -> None:
        now = time.time()
        with self._lock:
            dur = duration_ms if duration_ms is not None else int((now - self.t_last) * 1000)
            self.t_last = now
            self.spans += 1
        level = ("ERROR" if outcome in ("failed", "submit_error", "not_confirmed") else
                 "WARNING" if outcome in ("needs_human", "session_expired", "unreadable", "not_found", "cancelled",
                                          "rejected", "waiting_for_human", "otp_requested") or retries else "DEFAULT")
        action, _, target = step.partition(":")
        rec = {"type": "span", "name": step, "action": action, "target": target, "page": page or page_for(step),
               "outcome": outcome, "detail": self.scrub.text(detail or ""), "retries": retries, "duration_ms": dur,
               "level": level, "end": _iso(now)}
        self._write(rec)
        if self.root is not None:
            try:
                span = self.root.start_observation(
                    name=step, as_type="tool" if action in ("reconcile",) else "span",
                    input={"page": rec["page"], "action": action, "target": target},
                    output={"outcome": outcome, "detail": rec["detail"]},
                    metadata={"retries": retries, "duration_ms": dur}, level=level)
                span.end()
            except Exception as exc:
                log.debug("span export failed: %s", exc)

    def on_document(self, kind: str, label: str, path: str) -> None:
        """Attach write-action screenshots (and receipts) to the trace."""
        if kind not in ("screenshot", "dispute_receipt"):
            return
        self._write({"type": "attachment", "kind": kind, "label": label, "path": str(path), "at": _iso(time.time())})
        if self.root is not None:
            try:
                from langfuse import LangfuseMedia

                p = Path(path)
                ctype = "image/png" if p.suffix.lower() == ".png" else "application/pdf"
                media = LangfuseMedia(content_bytes=p.read_bytes(), content_type=ctype)
                span = self.root.start_observation(name=f"write_action:{label}", as_type="span",
                                                   input={"kind": kind, "label": label}, output={"evidence": media})
                span.end()
            except Exception as exc:
                log.debug("attachment export failed: %s", exc)

    # ------------------------------------------------------------------ finish

    def finish(self, status: str, result: dict | None = None) -> None:
        result = result or {}
        summary = {
            "status": status, "steps": result.get("steps"), "retries": result.get("retries"),
            "duration_s": result.get("duration_s"), "cost_inr": result.get("cost_inr"),
            "human_steps": result.get("human_steps"),
            "invoices": {k: sum(1 for i in result.get("invoices") or [] if i.get("result") == k)
                         for k in ("match", "mismatch", "cancelled")},
            "disputes": [d.get("invoice_no") for d in result.get("disputes") or []],
            "missing_in_portal": len(result.get("missing_in_portal") or []),
            "error": self.scrub.text(result.get("error") or ""),
        }
        self._write({"type": "end", "status": status, "output": summary, "end": _iso(time.time()),
                     "duration_s": round(time.time() - self.t0, 1), "spans": self.spans})
        if self.root is not None:
            try:
                self.root.update(output=summary, level="ERROR" if status == "failed" else
                                 "WARNING" if status in ("needs_human", "cancelled") else "DEFAULT")
                self.root.end()
                self.lf.flush()
            except Exception as exc:
                log.warning("Langfuse trace end failed: %s", exc)

    def _write(self, rec: dict) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")


def read_trace(trace_id: str) -> list[dict]:
    p = TRACE_DIR / f"{trace_id}.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds")
