"""Read dates from a downloaded proof-of-delivery PDF.

Text PDFs are read directly. Image-only scans are read with OCR (Tesseract, run locally — the
document never leaves the machine). OCR is trusted only when the words it read are confident
and both dates parse; otherwise (None, None) and the line goes to a human. Never a guess.
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


OCR_MIN_CONFIDENCE = 80.0  # mean Tesseract word confidence (0-100) on the lines holding the dates


def _tesseract():
    import os
    import shutil

    import pytesseract

    if not shutil.which("tesseract"):
        for c in (os.environ.get("TESSERACT_CMD", ""), r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                  r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if c and Path(c).exists():
                pytesseract.pytesseract.tesseract_cmd = c
                break
    return pytesseract


def ocr_text(path: str | Path) -> tuple[str, dict[int, float]]:
    """OCR every page. Returns the text and, per line number in that text, the mean word confidence."""
    try:
        import pypdfium2 as pdfium

        tess = _tesseract()
        lines: list[str] = []
        conf: dict[int, float] = {}
        pdf = pdfium.PdfDocument(str(path))
        for page in pdf:
            from meridian.portal.scaninvoice import deskew

            img = deskew(page.render(scale=300 / 72).to_pil().convert("L"))
            d = tess.image_to_data(img, output_type=tess.Output.DICT)
            rows: dict[tuple, list[tuple[str, float]]] = {}
            for i, w in enumerate(d["text"]):
                if w.strip() and float(d["conf"][i]) >= 0:
                    rows.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append((w, float(d["conf"][i])))
            for key in sorted(rows):
                words = rows[key]
                conf[len(lines)] = sum(c for _, c in words) / len(words)
                lines.append(" ".join(w for w, _ in words))
        return "\n".join(lines), conf
    except Exception:
        return "", {}


def ocr_dates(path: str | Path) -> tuple[date | None, date | None, float]:
    """Dates from a scan, with the confidence of the lines they came from (0 if not found)."""
    text, conf = ocr_text(path)
    if not text:
        return None, None, 0.0
    prom, deliv = dates_from_text(text)
    used = [conf.get(i, 0.0) for i, line in enumerate(text.split("\n")) if _PROM.search(line) or _DELIV.search(line)]
    return prom, deliv, (min(used) if used else 0.0)


def pod_dates_from_pdf(path: str | Path) -> tuple[date | None, date | None]:
    """Text first; OCR only for scans, and only when it read the date lines confidently."""
    p, d = dates_from_text(pdf_text(path))
    if p and d:
        return p, d
    p, d, c = ocr_dates(path)
    if p and d and c >= OCR_MIN_CONFIDENCE:
        return p, d
    return None, None
