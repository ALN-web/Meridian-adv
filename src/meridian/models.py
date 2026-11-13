"""Task and task-result schemas (the format the hidden test compares)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TaskKind = Literal["list", "one", "lane_month", "missing", "collect", "dispute"]
TaskStatus = Literal["completed", "needs_human", "failed"]
InvoiceResult = Literal["match", "mismatch", "cancelled"]
ReasonCode = Literal[
    "shipment_unknown",
    "duplicate_billing",
    "no_pod",
    "weight_over",
    "rate_wrong",
    "surcharge_wrong",
    "detention_unjustified",
    "math_error",
]


class Task(BaseModel):
    task_id: str
    kind: TaskKind
    task: str
    params: dict = Field(default_factory=dict)


class ListedInvoice(BaseModel):
    invoice_no: str
    total_inr: float
    status: Literal["Open", "Cancelled"]


class ReconciledInvoice(BaseModel):
    invoice_no: str
    result: InvoiceResult
    reasons: list[ReasonCode] = Field(default_factory=list)
    billed_inr: float | None = None
    expected_inr: float | None = None
    evidence: list[str] = Field(default_factory=list)


class Pod(BaseModel):
    shipment_id: str
    promised_on: str  # YYYY-MM-DD
    delivered_on: str  # YYYY-MM-DD


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    invoices: list[ListedInvoice | ReconciledInvoice] = Field(default_factory=list)
    missing_in_portal: list[str] = Field(default_factory=list)
    pods: list[Pod] = Field(default_factory=list)
    disputes: list[dict] = Field(default_factory=list)
    human_steps: list[str] = Field(default_factory=list)
    steps: int = 0
    retries: int = 0
    duration_s: float = 0
    cost_inr: float = 0
    trace_id: str | None = None
