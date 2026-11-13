"""Inputs to the reconciliation engine — plain data the portal layer fills in.

Everything money-like is ``Decimal``. Nothing here talks to a browser or an LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from meridian.parsing import to_paise


@dataclass(frozen=True)
class InvoiceLine:
    """One invoice line = one shipment, as printed on the portal."""

    shipment_id: str
    billed_weight_kg: Decimal
    rate_per_kg: Decimal
    freight: Decimal | None = None
    fuel_pct: Decimal | None = None  # e.g. Decimal("12.5") for 12.5 %
    fuel_amount: Decimal | None = None
    detention: Decimal = Decimal("0")
    line_total: Decimal | None = None  # as printed; derived from parts if absent

    def billed_freight(self) -> Decimal:
        return self.freight if self.freight is not None else to_paise(self.billed_weight_kg * self.rate_per_kg)

    def billed_fuel(self) -> Decimal:
        if self.fuel_amount is not None:
            return self.fuel_amount
        return to_paise(self.billed_freight() * (self.fuel_pct or Decimal("0")) / 100)

    def billed_total(self) -> Decimal:
        if self.line_total is not None:
            return self.line_total
        return self.billed_freight() + self.billed_fuel() + self.detention


@dataclass(frozen=True)
class Invoice:
    invoice_no: str
    invoice_date: date
    lane: str
    status: str  # "Open" | "Cancelled"
    total: Decimal  # invoice total as printed (incl. 12 % GST, before credit notes)
    lines: tuple[InvoiceLine, ...] = ()
    credit_notes: tuple[Decimal, ...] = ()

    @property
    def is_cancelled(self) -> bool:
        return self.status.strip().lower() == "cancelled"

    @property
    def credit_total(self) -> Decimal:
        return sum(self.credit_notes, Decimal("0"))

    @property
    def sort_key(self) -> tuple[date, int, str]:
        """Order used for duplicate detection: invoice date, then invoice number."""
        return (self.invoice_date, invoice_number_value(self.invoice_no), self.invoice_no)


@dataclass(frozen=True)
class BillingRecord:
    """Minimal view of *any* portal invoice, used to detect duplicate billing across invoices."""

    invoice_no: str
    invoice_date: date
    status: str
    shipment_ids: tuple[str, ...]

    @property
    def is_cancelled(self) -> bool:
        return self.status.strip().lower() == "cancelled"

    @property
    def sort_key(self) -> tuple[date, int, str]:
        return (self.invoice_date, invoice_number_value(self.invoice_no), self.invoice_no)

    @classmethod
    def from_invoice(cls, inv: Invoice) -> "BillingRecord":
        return cls(inv.invoice_no, inv.invoice_date, inv.status, tuple(l.shipment_id for l in inv.lines))


@dataclass(frozen=True)
class RateCardEntry:
    lane: str
    rate_per_kg: Decimal
    effective_from: date
    effective_to: date | None = None


@dataclass(frozen=True)
class Pod:
    shipment_id: str
    promised_on: date | None
    delivered_on: date | None
    confident: bool = True  # False when a scanned proof couldn't be read with confidence


@dataclass
class ReferenceData:
    """Everything the rules need besides the invoice itself."""

    rate_card: list[RateCardEntry]
    fuel_surcharge_pct: dict[str, Decimal]  # "YYYY-MM" -> pct
    pods: dict[str, Pod]
    billing_history: list[BillingRecord]  # every invoice seen on the portal (any lane / month)
    disputed_invoices: set[str] = field(default_factory=set)


_NUM = re.compile(r"(\d+)\s*$")


def invoice_number_value(invoice_no: str) -> int:
    """Trailing serial of an invoice number, e.g. ``TIR/26-27/10121`` -> 10121."""
    m = _NUM.search(invoice_no)
    return int(m.group(1)) if m else 0
