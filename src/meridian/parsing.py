"""Parsers for the portal's display formats.

The portal shows dates like ``14-Oct-26`` and amounts like ``Rs. 1,23,456.00``
(Indian digit grouping). Money is always ``Decimal`` — never float.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")

_DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d %b %Y", "%d %B %Y")
_AMOUNT_JUNK = re.compile(r"(?i)\b(?:rs|inr)\b\.?|₹|\s")


def parse_date(text: str) -> date:
    """Parse a portal date (``14-Oct-26``, ``2026-10-14``, ``14/10/2026`` ...)."""
    s = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {text!r}")


def parse_amount(text: str) -> Decimal:
    """Parse ``Rs. 1,23,456.00`` / ``₹ 1,234.5`` / ``(1,000.00)`` / ``-500`` into Decimal."""
    s = _AMOUNT_JUNK.sub("", text.strip())
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.startswith("-"):
        negative, s = True, s[1:]
    s = s.replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        raise ValueError(f"Unrecognised amount: {text!r}")
    value = Decimal(s)
    return -value if negative else value


def to_paise(value: Decimal) -> Decimal:
    """Round half-up to two decimals (paise)."""
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)
