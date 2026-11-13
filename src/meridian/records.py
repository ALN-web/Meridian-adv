"""Meridian's own shipment records.

Columns: shipment_id, booked_on, lane, actual_weight_kg, delivered_on, meridian_ref.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    booked_on: date
    lane: str
    actual_weight_kg: Decimal
    delivered_on: date
    meridian_ref: str


def load_shipments(path: str | Path) -> dict[str, Shipment]:
    out: dict[str, Shipment] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("shipment_id") or "").strip():
                continue
            s = Shipment(
                shipment_id=row["shipment_id"].strip(),
                booked_on=date.fromisoformat(row["booked_on"].strip()),
                lane=row["lane"].strip(),
                actual_weight_kg=Decimal(row["actual_weight_kg"].strip()),
                delivered_on=date.fromisoformat(row["delivered_on"].strip()),
                meridian_ref=row["meridian_ref"].strip(),
            )
            out[s.shipment_id] = s
    return out


def delivered_in(shipments: dict[str, Shipment], lane: str, month: str) -> list[Shipment]:
    """Shipments on ``lane`` delivered in ``month`` (YYYY-MM). Used by *missing* tasks."""
    return sorted(
        (s for s in shipments.values() if s.lane == lane and s.delivered_on.strftime("%Y-%m") == month),
        key=lambda s: s.shipment_id,
    )
