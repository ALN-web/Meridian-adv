"""Tracing: masking, one trace per task with one span per step, and the real Langfuse export path
(against a local stub server — nothing leaves the machine)."""
import socket
import threading
import time

import pytest
from pydantic import SecretStr

from meridian import telemetry
from meridian.agent import demo
from meridian.agent.planner import plan_task
from meridian.config import Settings
from meridian.store import Store
from meridian.telemetry import Scrubber, TaskTracer, page_for, read_trace

SECRETS = Settings(portal_user="meridian.ap", portal_password=SecretStr("Sup3r-Secret!"),
                   team_key=SecretStr("teamkey123"))


def test_scrubber_masks_secrets_and_personal_data():
    s = Scrubber(SECRETS)
    text = ("login meridian.ap / Sup3r-Secret! key=teamkey123 Received By: Ravi Kulkarni "
            "call 9811777417 or +91 9876543210, mail ravi.k@example.com")
    out = s.text(text)
    for leak in ("meridian.ap", "Sup3r-Secret!", "teamkey123", "Ravi", "Kulkarni", "9811777417", "9876543210", "example.com"):
        assert leak not in out
    assert "[phone]" in out and "[email]" in out and "[person]" in out
    assert s({"a": ["9811777417"], "b": {"c": "Sup3r-Secret!"}}) == {"a": ["[phone]"], "b": {"c": "[redacted]"}}


def test_page_for_steps():
    assert page_for("search_invoices:PUN-BLR") == "Invoices.aspx"
    assert page_for("pod:SHP-1") == "Pods.aspx"
    assert page_for("reconcile:TIR/1").startswith("(rules")


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "TRACE_DIR", tmp_path / "traces")
    return Store(tmp_path / "s.sqlite")


def _auto(store, stop):
    while not stop.is_set():
        for r in store.pending_human():
            store.answer_human(r["id"], "123456")
        for d in store.disputes(status="pending"):
            store.decide_dispute(d["id"], True)
        time.sleep(0.03)


def test_one_trace_per_task_one_span_per_step(store, monkeypatch):
    demo.STEP_DELAY = 0
    monkeypatch.setattr(demo, "_WORLD", None)  # fresh simulated portal: no disputes raised by earlier tests
    text = "Reconcile all invoices on lane PUN-BLR dated in September 2026, and raise disputes for overcharges after approval."
    plan = plan_task(text)
    run_id = store.create_run("T-TR", text, plan.kind, plan.params, plan.steps, "demo")
    stop = threading.Event()
    threading.Thread(target=_auto, args=(store, stop), daemon=True).start()
    demo.DemoRunner(store, run_id, plan, "T-TR").start().join(timeout=60)
    stop.set()
    run = store.get_run(run_id)
    tid = run.result["trace_id"]
    recs = read_trace(tid)
    assert [r["type"] for r in recs].count("trace") == 1
    assert recs[-1]["type"] == "end" and recs[-1]["status"] == run.status
    spans = [r for r in recs if r["type"] == "span"]
    assert len(spans) == len(store.steps(run_id))
    assert all({"page", "action", "outcome", "retries", "duration_ms"} <= set(s) for s in spans)
    assert any(r["type"] == "attachment" for r in recs), "write action evidence should be attached"
    blob = "\n".join(str(r) for r in recs)
    assert "123456" not in blob, "OTP codes must never be traced"


class _Stub:
    """Minimal HTTP server standing in for Langfuse; records every request body."""

    def __init__(self):
        import http.server

        self.bodies: list[tuple[str, bytes]] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def _ok(self):
                n = int(self.headers.get("Content-Length") or 0)
                outer.bodies.append((self.path, self.rfile.read(n) if n else b""))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"data": []}' if "projects" in self.path else b"{}")

            do_POST = do_PUT = do_PATCH = do_GET = _ok

            def log_message(self, *a):
                pass

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


def test_langfuse_export_sends_spans_without_secrets(tmp_path, monkeypatch):
    pytest.importorskip("langfuse")
    stub = _Stub()
    monkeypatch.setattr(telemetry, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(telemetry, "_CLIENT", None)
    settings = SECRETS.model_copy(update={"langfuse_public_key": "pk-lf-test", "langfuse_secret_key": SecretStr("sk-lf-test"),
                                          "langfuse_host": f"http://127.0.0.1:{stub.port}"})
    tr = TaskTracer("run1", "T-01", "List invoices for meridian.ap", "list", "test", settings=settings)
    tr.on_step("login", "ok", "user meridian.ap password Sup3r-Secret!")
    tr.on_step("pod:SHP-1", "ok", "Received By: Ravi Kulkarni 9811777417")
    tr.finish("completed", {"steps": 2})
    deadline = time.time() + 15
    while time.time() < deadline and not any("otel" in p for p, _ in stub.bodies):
        time.sleep(0.2)
    stub.srv.shutdown()
    monkeypatch.setattr(telemetry, "_CLIENT", None)
    import gzip

    otel = b"".join(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b for p, b in stub.bodies if "otel" in p)
    assert otel, f"no OTel export seen; paths: {[p for p, _ in stub.bodies]}"
    assert b"pod:SHP-1" in otel and b"login" in otel
    for leak in (b"Sup3r-Secret!", b"Kulkarni", b"9811777417", b"teamkey123"):
        assert leak not in otel
