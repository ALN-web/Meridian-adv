"""Scanned legacy invoices and PODs: OCR must read a tilted scan, and refuse when sums don't check."""
from decimal import Decimal

import pytest

from meridian.portal.pdftext import _tesseract, pod_dates_from_pdf

try:
    _tesseract().get_tesseract_version()
except Exception:  # pragma: no cover - machine without Tesseract
    pytest.skip("Tesseract not installed", allow_module_level=True)

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from meridian.portal.scaninvoice import read_scanned_invoice  # noqa: E402

ROWS = [
    ("SHP-60483", "24-Oct-26", "2145.5", "9.73", "Rs. 20,875.72", "13.5", "Rs. 2,818.22", "Rs. 3,000.00", "Rs. 26,693.94"),
    ("SHP-60462", "26-Oct-26", "508.1", "9.73", "Rs. 4,943.81", "13.5", "Rs. 667.41", "Rs. 0.00", "Rs. 5,611.22"),
    ("SHP-90093", "29-Oct-26", "564.2", "9.73", "Rs. 5,489.67", "13.5", "Rs. 741.11", "Rs. 0.00", "Rs. 6,230.78"),
]
SUB = Decimal("38535.94")


def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _scan(path, header, rows, footer, tilt=1.1):
    img = Image.new("L", (2480, 1754), 255)
    d = ImageDraw.Draw(img)
    f = _font(30)
    y = 120
    for line in header:
        d.text((100, y), line, font=f, fill=0)
        y += 55
    xs = [100, 330, 520, 680, 820, 1100, 1220, 1480, 1720]
    for r in rows:
        y += 55
        for x, cell in zip(xs, r):
            d.text((x, y), cell, font=f, fill=0)
    y += 90
    for line in footer:
        d.text((100, y), line, font=f, fill=0)
        y += 55
    img = img.rotate(tilt, fillcolor=255, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.5))
    img.convert("RGB").save(path, "PDF", resolution=200)
    return path


def test_tilted_scanned_invoice_is_read_and_checked(tmp_path):
    pdf = _scan(tmp_path / "inv.pdf", ["TAX INVOICE", "Consignment Booked Wt(kg) Rate/kg Freight Fuel% Fuel amt Detention Line total"],
                ROWS, ["Sub Total: Rs. 38,535.94", "INVOICE TOTAL: Rs. 43,160.25"])
    scan = read_scanned_invoice(pdf, SUB)
    assert scan.ok, scan.problems
    assert [r["Consignment"] for r in scan.rows] == ["SHP-60483", "SHP-60462", "SHP-90093"]
    assert scan.rows[0]["Detention"] == "3,000.00"


def test_scanned_invoice_refused_when_lines_do_not_add_up(tmp_path):
    pdf = _scan(tmp_path / "inv.pdf", ["TAX INVOICE"], ROWS, ["Sub Total: Rs. 38,535.94"])
    scan = read_scanned_invoice(pdf, Decimal("40000.00"))  # page says something else -> do not trust the scan
    assert not scan.ok
    assert any("sub total" in p for p in scan.problems)


def test_scanned_pod_dates(tmp_path):
    img = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(img)
    for i, t in enumerate(["Proof of Delivery", "Shipment: SHP-60225", "Promised Date: 14-Sep-26", "Delivered Date: 17-Sep-26"]):
        d.text((120, 150 + i * 70), t, font=_font(34), fill=0)
    path = tmp_path / "pod.pdf"
    img.rotate(-0.8, fillcolor=255).convert("RGB").save(path, "PDF", resolution=150)
    p, dl = pod_dates_from_pdf(path)
    assert (p.isoformat(), dl.isoformat()) == ("2026-09-14", "2026-09-17")
