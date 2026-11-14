"""Run store: the shared state between the agent and the operator screen (SQLite).

The agent writes steps, asks for OTPs and proposes disputes here; the UI reads it and writes
human answers (OTP codes, approvals) back. Keeping this outside the browser is also what lets a
task resume after a crash.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, task_id TEXT, task_text TEXT, kind TEXT, params TEXT,
  plan TEXT, status TEXT, mode TEXT, created REAL, finished REAL, result TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts REAL, step TEXT, outcome TEXT,
  detail TEXT, retries INTEGER DEFAULT 0, duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS human_requests (
  id TEXT PRIMARY KEY, run_id TEXT, kind TEXT, status TEXT, value TEXT, created REAL, answered REAL
);
CREATE TABLE IF NOT EXISTS disputes (
  id TEXT PRIMARY KEY, run_id TEXT, invoice_no TEXT, reasons TEXT, billed_inr TEXT, expected_inr TEXT,
  evidence TEXT, status TEXT, decided_by TEXT, decided_at REAL, portal_ref TEXT, note TEXT, created REAL
);
-- At most one live proposal per invoice: a second run cannot queue a duplicate.
CREATE UNIQUE INDEX IF NOT EXISTS one_live_dispute ON disputes(invoice_no)
  WHERE status IN ('pending', 'approved', 'submitted', 'confirmed');
CREATE TABLE IF NOT EXISTS checkpoints (
  run_id TEXT, item TEXT, state TEXT, data TEXT, PRIMARY KEY (run_id, item)
);
-- Per-invoice explanation for the UI (lines, inputs, documents). Not part of the graded result.
CREATE TABLE IF NOT EXISTS details (
  run_id TEXT, invoice_no TEXT, data TEXT, PRIMARY KEY (run_id, invoice_no)
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, kind TEXT, label TEXT, path TEXT, ts REAL
);
"""

# Columns added after the first release; applied to existing databases on open.
MIGRATIONS = (
    "ALTER TABLE runs ADD COLUMN phase INTEGER DEFAULT 0",
    "ALTER TABLE runs ADD COLUMN cancel INTEGER DEFAULT 0",
)

RUN_ACTIVE = ("queued", "running", "waiting_for_human")


@dataclass
class Run:
    id: str
    task_id: str
    task_text: str
    kind: str
    params: dict
    plan: list[str]
    status: str
    mode: str
    created: float
    finished: float | None
    result: dict | None
    error: str | None
    phase: int = 0
    cancel: bool = False


class Store:
    def __init__(self, path: str | Path = "runs/meridian.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            for m in MIGRATIONS:
                try:
                    c.execute(m)
                except sqlite3.OperationalError:
                    pass  # already applied

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ runs

    def create_run(self, task_id: str, task_text: str, kind: str, params: dict, plan: list[str], mode: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO runs (id, task_id, task_text, kind, params, plan, status, mode, created, finished, result, error, phase, cancel)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0)",
                (run_id, task_id, task_text, kind, json.dumps(params), json.dumps(plan), "queued", mode,
                 time.time(), None, None, None),
            )
        return run_id

    def set_status(self, run_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> None:
        finished = time.time() if status in ("completed", "needs_human", "failed") else None
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE runs SET status=?, finished=COALESCE(?, finished), result=COALESCE(?, result), "
                "error=COALESCE(?, error) WHERE id=?",
                (status, finished, json.dumps(result) if result is not None else None, error, run_id),
            )

    def get_run(self, run_id: str) -> Run | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def list_runs(self, limit: int = 50) -> list[Run]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [self._run(r) for r in rows]

    @staticmethod
    def _run(r) -> Run:
        return Run(
            id=r["id"], task_id=r["task_id"], task_text=r["task_text"], kind=r["kind"],
            params=json.loads(r["params"] or "{}"), plan=json.loads(r["plan"] or "[]"), status=r["status"],
            mode=r["mode"], created=r["created"], finished=r["finished"],
            result=json.loads(r["result"]) if r["result"] else None, error=r["error"],
            phase=r["phase"] or 0, cancel=bool(r["cancel"]),
        )

    # ------------------------------------------------------------------ steps

    def add_step(self, run_id: str, step: str, outcome: str, detail: str = "", retries: int = 0,
                 duration_ms: int | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO steps (run_id, ts, step, outcome, detail, retries, duration_ms) VALUES (?,?,?,?,?,?,?)",
                (run_id, time.time(), step, outcome, detail, retries, duration_ms),
            )

    def steps(self, run_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM steps WHERE run_id=? ORDER BY id", (run_id,))]

    # ------------------------------------------------------------------ human requests (OTP / CAPTCHA)

    def request_human(self, run_id: str, kind: str) -> str:
        rid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO human_requests VALUES (?,?,?,?,?,?,?)", (rid, run_id, kind, "pending", None, time.time(), None))
        return rid

    def pending_human(self, run_id: str | None = None) -> list[dict]:
        q = "SELECT id, run_id, kind, created FROM human_requests WHERE status='pending'"
        args: tuple = ()
        if run_id:
            q += " AND run_id=?"
            args = (run_id,)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY created", args)]

    def answer_human(self, request_id: str, value: str = "") -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE human_requests SET status='answered', value=?, answered=? WHERE id=? AND status='pending'",
                (value, time.time(), request_id),
            )

    def take_answer(self, request_id: str) -> str | None:
        """Read an answer once and wipe it — OTP codes are not kept."""
        with self._lock, self._conn() as c:
            row = c.execute("SELECT status, value FROM human_requests WHERE id=?", (request_id,)).fetchone()
            if not row or row["status"] != "answered":
                return None
            c.execute("UPDATE human_requests SET status='used', value=NULL WHERE id=?", (request_id,))
            return row["value"] or ""

    # ------------------------------------------------------------------ disputes

    def propose_dispute(self, run_id: str, invoice_no: str, reasons: list[str], billed: str, expected: str,
                        evidence: list[str]) -> str | None:
        """Queue a dispute for approval. Returns None if this invoice already has a live one."""
        did = uuid.uuid4().hex[:12]
        try:
            with self._lock, self._conn() as c:
                c.execute(
                    "INSERT INTO disputes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (did, run_id, invoice_no, json.dumps(reasons), billed, expected, json.dumps(evidence),
                     "pending", None, None, None, None, time.time()),
                )
        except sqlite3.IntegrityError:
            return None
        return did

    def disputes(self, *, status: str | None = None, run_id: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM disputes WHERE 1=1", []
        if status:
            q += " AND status=?"
            args.append(status)
        if run_id:
            q += " AND run_id=?"
            args.append(run_id)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q + " ORDER BY created", args)]
        for r in rows:
            r["reasons"] = json.loads(r["reasons"])
            r["evidence"] = json.loads(r["evidence"])
        return rows

    def decide_dispute(self, dispute_id: str, approve: bool, by: str = "operator", note: str = "") -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE disputes SET status=?, decided_by=?, decided_at=?, note=? WHERE id=? AND status='pending'",
                ("approved" if approve else "rejected", by, time.time(), note, dispute_id),
            )
            return cur.rowcount == 1

    def mark_dispute(self, dispute_id: str, status: str, portal_ref: str | None = None, note: str | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE disputes SET status=?, portal_ref=COALESCE(?, portal_ref), note=COALESCE(?, note) WHERE id=?",
                (status, portal_ref, note, dispute_id),
            )

    # ------------------------------------------------------------------ checkpoints (resume)

    def checkpoint(self, run_id: str, item: str, state: str, data: dict | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?)", (run_id, item, state, json.dumps(data or {})))

    def checkpoints(self, run_id: str) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT item, state, data FROM checkpoints WHERE run_id=?", (run_id,)).fetchall()
        return {r["item"]: {"state": r["state"], "data": json.loads(r["data"])} for r in rows}

    # ------------------------------------------------------------------ progress, stop, resume

    def set_phase(self, run_id: str, phase: int) -> None:
        """Index of the plan step the run is on (for the live plan view)."""
        with self._lock, self._conn() as c:
            c.execute("UPDATE runs SET phase=? WHERE id=?", (phase, run_id))

    def request_cancel(self, run_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE runs SET cancel=1 WHERE id=?", (run_id,))

    def cancel_requested(self, run_id: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT cancel FROM runs WHERE id=?", (run_id,)).fetchone()
        return bool(row and row["cancel"])

    def prepare_resume(self, run_id: str) -> None:
        """Re-queue a finished run; checkpoints are kept so finished invoices are skipped."""
        with self._lock, self._conn() as c:
            c.execute("UPDATE runs SET status='queued', cancel=0, finished=NULL, error=NULL, phase=0 WHERE id=?", (run_id,))
            c.execute("UPDATE human_requests SET status='expired' WHERE run_id=? AND status='pending'", (run_id,))

    # ------------------------------------------------------------------ explanations and documents

    def save_detail(self, run_id: str, invoice_no: str, data: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO details VALUES (?,?,?)", (run_id, invoice_no, json.dumps(data, default=str)))

    def details(self, run_id: str) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT invoice_no, data FROM details WHERE run_id=?", (run_id,)).fetchall()
        return {r["invoice_no"]: json.loads(r["data"]) for r in rows}

    def add_document(self, run_id: str, kind: str, label: str, path: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO documents (run_id, kind, label, path, ts) VALUES (?,?,?,?,?)",
                      (run_id, kind, label, str(path), time.time()))

    def documents(self, run_id: str | None = None, kind: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM documents WHERE 1=1", []
        if run_id:
            q += " AND run_id=?"
            args.append(run_id)
        if kind:
            q += " AND kind=?"
            args.append(kind)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY id", args)]
