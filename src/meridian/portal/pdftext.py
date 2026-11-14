"""Read dates from a downloaded proof-of-delivery PDF.

Text PDFs are read directly. Image-only scans have no text and return (None, None) — the line
is then flagged for a human. Hook for the week-2 OCR reader: ``ocr_reader`` (not wired yet).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from meridian.parsing import parse_date

_DATE = r"(\d{1,2}[-/ ][A-Za-z]{3}[-/ ]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
_PROM = re.compile(r"(promised|due|expected)[^\n\d]{0,25}" + _DATE, re.I)
_DELIV = re.compile(r"(delivered|delivery date|received on)[^\n\d]{0,25}" + _DATE, re.I)


def pdf_text(path: str | Path) -> str:
    try:
        from pypdf import PdfReader

        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:
        return ""


def dates_from_text(text: str) -> tuple[date | None, date | None]:
    def grab(rx):
        m = rx.search(text)
        if not m:
            return None
        try:
            return parse_date(m.group(2).replace("/", "-") if re.match(r"\d{1,2}/[A-Za-z]", m.group(2)) else m.group(2))
        except ValueError:
            return None

    return grab(_PROM), grab(_DELIV)


def pod_dates_from_pdf(path: str | Path) -> tuple[date | None, date | None]:
    return dates_from_text(pdf_text(path))
