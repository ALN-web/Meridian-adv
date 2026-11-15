"""Turn raw grid rows into typed records, tolerating column order / header wording changes.

The browser side only extracts ``{header text: cell text}`` dicts; everything here is pure Python.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from meridian.parsing import parse_amount, parse_date
from meridian.portal.errors import PageNotUnderstood

# canonical field -> header patterns seen (or likely) on the portal
ALIASES: dict[str, tuple[str, ...]] = {
    "invoice_no": (r"invoice\s*(no|number|#)", r"^inv\.?\s*(no|#)", r"bill\s*no"),
    "invoice_date": (r"invoice\s*date", r"inv\.?\s*date", r"bill\s*date", r"^date$"),
    "lane": (r"^lane$", r"route", r"origin.*dest"),
    "status": (r"status",),
    "total": (r"(invoice\s*)?total", r"invoice\s*value", r"amount\s*\(?(rs|inr)", r"^amount$", r"net\s*amount",
              r"grand\s*total", r"^value"),
    "shipment_id": (r"shipment|consignment|docket|lr\s*no|cn\s*no",),
    "billed_weight_kg": (r"(billed|charged|chargeable)\s*w(eigh)?t", r"weight", r"^wt"),
    "rate_per_kg": (r"rate", r"per\s*kg"),
    "freight": (r"^freight", r"basic\s*freight"),
    "fuel_pct": (r"(fuel|fsc).*%", r"(fsc|fuel).*(pct|percent)"),
    "fuel_amount": (r"fuel", r"fsc"),
    "detention": (r"detention|demurrage|waiting"),
    "line_total": (r"line\s*total", r"^total$", r"^amount$"),
    "promised_on": (r"promised|due\s*date|expected", r"edd"),
    "delivered_on": (r"delivered|delivery\s*date|pod\s*date|actual"),
    "received_by": (r"received\s*by|receiver|consignee\s*sign",),
    "credit_amount": (r"credit|cn\s*amount"),
    "effective_from": (r"effective\s*from|valid\s*from|w\.?e\.?f", r"^effective$"),
    "month": (r"^month$", r"period"),
    "surcharge_pct": (r"surcharge|fuel|fsc", r"%"),
}


# Rule code -> wording the portal uses for dispute reasons. The first three were seen on the real
# dispute list; the rest are best guesses until the Raise Dispute form has been seen.
REASON_LABELS: dict[str, str] = {
    "shipment_unknown": "Consignment not ours",
    "duplicate_billing": "Duplicate billing",
    "rate_wrong": "Incorrect rate applied",
    "no_pod": "No proof of delivery",
    "weight_over": "Weight overcharged",
    "surcharge_wrong": "Incorrect fuel surcharge",
    "detention_unjustified": "Detention not justified",
    "math_error": "Calculation error",
}

# Key words to find a reason's checkbox when the exact wording differs.
REASON_HINTS: dict[str, str] = {
    "shipment_unknown": r"not ours|unknown|not (our|meridian)",
    "duplicate_billing": r"duplicate",
    "rate_wrong": r"rate",
    "no_pod": r"proof|pod",
    "weight_over": r"weight",
    "surcharge_wrong": r"fuel|surcharge|fsc",
    "detention_unjustified": r"detention",
    "math_error": r"calculation|arithmetic|math|total",
}


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", h.replace("\xa0", " ")).strip().lower()


def map_headers(headers: list[str], wanted: list[str]) -> dict[str, str]:
    """Map canonical field names to the actual header text. Each header is used at most once,
    and earlier fields in ``wanted`` win ties (list specific fields first)."""
    normed = {h: _norm(h) for h in headers}
    used: set[str] = set()
    out: dict[str, str] = {}
    for field in wanted:
        patterns = ALIASES[field] if isinstance(ALIASES[field], tuple) else (ALIASES[field],)
        for pat in patterns:
            hit = next((h for h, n in normed.items() if h not in used and re.search(pat, n)), None)
            if hit is not None:
                out[field] = hit
                used.add(hit)
                break
    return out


def require(mapping: dict[str, str], fields: list[str], what: str) -> None:
    missing = [f for f in fields if f not in mapping]
    if missing:
        raise PageNotUnderstood(f"{what}: could not find columns {missing}")


def _cell(row: dict[str, str], mapping: dict[str, str], field: str) -> str | None:
    h = mapping.get(field)
    if h is None:
        return None
    v = (row.get(h) or "").strip()
    if v.lower() in {"-", "--", "—", "–", "nil", "n/a", "na"}:
        return None
    return v or None


def _pct(text: str) -> Decimal:
    return Decimal(text.replace("%", "").strip())


@dataclass(frozen=True)
class InvoiceRow:
    invoice_no: str
    invoice_date: date | None
    lane: str | None
    status: str
    total: Decimal
    total_text: str  # as printed — list tasks report the total "as printed"


def parse_invoice_list(rows: list[dict[str, str]]) -> list[InvoiceRow]:
    if not rows:
        return []
    m = map_headers(list(rows[0].keys()), ["invoice_no", "invoice_date", "lane", "status", "total"])
    require(m, ["invoice_no", "total", "status"], "invoice list")
    out = []
    for r in rows:
        no = _cell(r, m, "invoice_no")
        if not no:
            continue
        d = _cell(r, m, "invoice_date")
        total_text = _cell(r, m, "total") or "0"
        out.append(
            InvoiceRow(
                invoice_no=no,
                invoice_date=parse_date(d) if d else None,
                lane=_cell(r, m, "lane"),
                status=(_cell(r, m, "status") or "").title(),
                total=parse_amount(total_text),
                total_text=total_text,
            )
        )
    return out


def parse_invoice_lines(rows: list[dict[str, str]]):
    """Rows of an invoice's line grid -> ``InvoiceLine`` objects."""
    from meridian.reconcile.types import InvoiceLine

    if not rows:
        return []
    m = map_headers(
        list(rows[0].keys()),
        ["shipment_id", "billed_weight_kg", "fuel_pct", "rate_per_kg", "freight", "fuel_amount", "detention", "line_total"],
    )
    require(m, ["shipment_id", "billed_weight_kg", "rate_per_kg"], "invoice lines")
    out = []
    for r in rows:
        sid = _cell(r, m, "shipment_id")
        if not sid or not re.search(r"\d", sid):
            continue  # subtotal / blank rows
        amt = lambda f: parse_amount(v) if (v := _cell(r, m, f)) else None  # noqa: E731
        fuel_pct = _cell(r, m, "fuel_pct")
        out.append(
            InvoiceLine(
                shipment_id=sid,
                billed_weight_kg=parse_amount(_cell(r, m, "billed_weight_kg").lower().replace("kg", "")),
                rate_per_kg=parse_amount(_cell(r, m, "rate_per_kg")),
                freight=amt("freight"),
                fuel_pct=_pct(fuel_pct) if fuel_pct else None,
                fuel_amount=amt("fuel_amount"),
                detention=amt("detention") or Decimal("0"),
                line_total=amt("line_total"),
            )
        )
    return out


def parse_pod_row(row: dict[str, str]):
    from meridian.reconcile.types import Pod

    m = map_headers(list(row.keys()), ["shipment_id", "promised_on", "delivered_on"])
    sid = _cell(row, m, "shipment_id")
    p, d = _cell(row, m, "promised_on"), _cell(row, m, "delivered_on")
    if not sid:
        raise PageNotUnderstood("POD row without shipment id")
    try:
        return Pod(sid, parse_date(p) if p else None, parse_date(d) if d else None, confident=bool(p and d))
    except ValueError:
        return Pod(sid, None, None, confident=False)


def parse_rate_card(rows: list[dict[str, str]]):
    from meridian.reconcile.types import RateCardEntry

    if not rows:
        return []
    m = map_headers(list(rows[0].keys()), ["lane", "effective_from", "rate_per_kg"])
    require(m, ["lane", "effective_from", "rate_per_kg"], "rate card")
    return [
        RateCardEntry(_cell(r, m, "lane"), parse_amount(_cell(r, m, "rate_per_kg")), parse_date(_cell(r, m, "effective_from")))
        for r in rows
        if _cell(r, m, "lane")
    ]


_MONTH_FORMATS = ("%b-%y", "%b-%Y", "%B %Y", "%b %Y", "%Y-%m", "%m/%Y")


def parse_month(text: str) -> str:
    from datetime import datetime

    s = text.strip()
    for fmt in _MONTH_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    raise ValueError(f"Unrecognised month: {text!r}")


def parse_fuel_surcharge(rows: list[dict[str, str]]) -> dict[str, Decimal]:
    if not rows:
        return {}
    m = map_headers(list(rows[0].keys()), ["month", "surcharge_pct"])
    require(m, ["month", "surcharge_pct"], "fuel surcharge")
    return {parse_month(_cell(r, m, "month")): _pct(_cell(r, m, "surcharge_pct")) for r in rows if _cell(r, m, "month")}
