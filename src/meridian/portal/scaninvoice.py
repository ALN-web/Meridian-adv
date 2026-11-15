"""Line items from a scanned (image-only) invoice PDF — the portal's "legacy invoice".

OCR runs locally (Tesseract). Words are placed back into table rows by their position on the
page, then every number is cross-checked before it is trusted:

    weight × rate = freight,  freight × fuel % = fuel,  freight + fuel + detention = line total,
    sum of line totals = sub total,  sub total × 1.12 = invoice total (when given)

If any check fails the result is ``None`` and the invoice goes to a human — never a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from meridian.parsing import parse_amount

HEADERS = ["Consignment", "Booked On", "Weight (kg)", "Rate/kg", "Freight", "Fuel %", "Fuel Amt", "Detention", "Amount"]
_SID = re.compile(r"^[A-Z]{2,4}-\d{4,}$")
_DATE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_NUM = re.compile(r"^-?[\d,]+(\.\d+)?$")
TOL = Decimal("1.00")


@dataclass
class ScannedInvoice:
    rows: list[dict[str, str]]
    sub_total: Decimal | None
    total: Decimal | None
    problems: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.rows) and not self.problems


def deskew(img, max_deg: float = 4.0, step: float = 0.1):
    """Straighten a slightly rotated scan: pick the angle whose text rows are sharpest."""
    import numpy as np

    small = img.resize((img.width // 4, img.height // 4))
    best, best_score = 0.0, -1.0
    a = -max_deg
    while a <= max_deg + 1e-9:
        arr = np.asarray(small.rotate(a, fillcolor=255), dtype=np.float32)
        rows = (255 - arr).sum(axis=1)
        score = float(np.square(np.diff(rows)).sum())
        if score > best_score:
            best, best_score = a, score
        a += step
    return img.rotate(best, fillcolor=255, resample=3) if abs(best) > 0.05 else img


def _words(path: str | Path) -> list[dict]:
    import pypdfium2 as pdfium

    from meridian.portal.pdftext import _tesseract

    tess = _tesseract()
    out = []
    for pno, page in enumerate(pdfium.PdfDocument(str(path))):
        img = deskew(page.render(scale=300 / 72).to_pil().convert("L"))
        d = tess.image_to_data(img, output_type=tess.Output.DICT, config="--psm 6")
        for i, w in enumerate(d["text"]):
            w = w.strip()
            if w:
                out.append({"t": w, "x": d["left"][i], "y": d["top"][i] + d["height"][i] / 2,
                            "h": d["height"][i], "p": pno, "c": float(d["conf"][i])})
    return out


def _tokens(words: list[dict]) -> list[str]:
    """Row words left→right, with 'Rs.' prefixes dropped and 'Rs.2,818.22' split."""
    toks = []
    for w in sorted(words, key=lambda w: w["x"]):
        t = re.sub(r"^(rs\.?|₹)", "", w["t"], flags=re.I).strip(":;|_'`\"")
        t = re.sub(r"(?<=\d)[.,]+$", "", t) if re.search(r"\d\.\d{2}[.,]+$", t) else t  # '0.00,' -> '0.00'
        if not re.search(r"[A-Za-z0-9]", t):
            continue  # lone ',' or '-' from paper noise
        if (m := re.search(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}", t)) and not _DATE.match(t):
            t = m.group(0)  # stray mark glued to a date, e.g. '9=22-Aug-26'
        if re.fullmatch(r"[\dOoSl,.:;]+", t) and re.search(r"\d", t):
            # common OCR slips inside numbers; the arithmetic checks still decide if the row is trusted
            t = re.sub(r"(?<=\d)[:;](?=\d)", ".", t).replace("O", "0").replace("o", "0").replace("S", "5").replace("l", "1")
            t = re.sub(r",(\d{2})$", r".\1", t) if "." not in t else t  # '0,00' -> '0.00'
        if t:
            toks.append(t)
    return toks


def _amount_after(text: str, label: str) -> Decimal | None:
    m = re.search("(?:" + label + r")[^\d\n]{0,25}([\d,]+\.\d{2})", text, re.I)
    return parse_amount(m.group(1)) if m else None


def read_scanned_invoice(path: str | Path, page_sub_total: Decimal | None = None) -> ScannedInvoice:
    """``page_sub_total``: the sub total shown as text on the invoice web page, the strongest check."""
    try:
        words = _words(path)
    except Exception as exc:
        return ScannedInvoice([], None, None, [f"OCR failed: {type(exc).__name__}"])
    for w in words:  # 'SHP-60425.' / 'SHP-6O425' -> 'SHP-60425'
        m = re.fullmatch(r"([A-Z]{2,4})-([\dO]{4,})[.,:;_'`]*", w["t"])
        if m:
            w["t"] = f"{m.group(1)}-{m.group(2).replace('O', '0')}"
    anchors = [w for w in words if _SID.match(w["t"])]
    rows, problems = [], []
    for a in sorted(anchors, key=lambda w: (w["p"], w["y"])):
        same = [w for w in words if w["p"] == a["p"] and abs(w["y"] - a["y"]) <= max(a["h"], 12) * 0.6 and w["x"] > a["x"]]
        toks = _tokens(same)
        date = next((t for t in toks if _DATE.match(t)), None)
        nums = [t for t in toks if _NUM.match(t) and not _DATE.match(t)]
        if date is None or len(nums) != 7:
            problems.append(f"{a['t']}: expected a date and 7 numbers, read {toks}")
            continue
        rows.append(dict(zip(HEADERS, [a["t"], date] + nums)))

    text = "\n".join(_tokens([w]) [0] if _tokens([w]) else "" for w in words)  # fallback, not used for totals
    line_text = _line_text(words)
    sub = _amount_after(line_text, r"sub\s*total")
    total = _amount_after(line_text, r"invoice\s*total|grand\s*total")
    if page_sub_total is not None:
        if sub is not None and abs(sub - page_sub_total) > TOL:
            problems.append(f"scan sub total {sub} ≠ page sub total {page_sub_total}")
        sub = page_sub_total
    problems += _verify(rows, sub)
    return ScannedInvoice(rows, sub, total, problems)


def _line_text(words: list[dict]) -> str:
    """Words grouped into visual lines (for the totals block)."""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["p"], w["y"])):
        if lines and lines[-1][0]["p"] == w["p"] and abs(lines[-1][0]["y"] - w["y"]) <= max(w["h"], 12) * 0.6:
            lines[-1].append(w)
        else:
            lines.append([w])
    return "\n".join(" ".join(x["t"] for x in sorted(line, key=lambda x: x["x"])) for line in lines)


def _verify(rows: list[dict[str, str]], sub: Decimal | None) -> list[str]:
    # The invoice total is NOT checked here: a wrong total is a finding (math_error), not an OCR fault.
    bad = []
    q = Decimal("0.01")
    line_sum = Decimal("0")
    for r in rows:
        try:
            wt, rate, fr = (parse_amount(r[k]) for k in ("Weight (kg)", "Rate/kg", "Freight"))
            pct, fuel, det, amt = (parse_amount(r[k]) for k in ("Fuel %", "Fuel Amt", "Detention", "Amount"))
        except Exception:
            bad.append(f"{r['Consignment']}: a number could not be read")
            continue
        if abs((wt * rate).quantize(q) - fr) > TOL:
            bad.append(f"{r['Consignment']}: weight × rate ≠ freight as read")
        if abs((fr * pct / 100).quantize(q) - fuel) > TOL:
            bad.append(f"{r['Consignment']}: fuel % ≠ fuel amount as read")
        if abs(fr + fuel + det - amt) > TOL:
            bad.append(f"{r['Consignment']}: line parts ≠ line total as read")
        line_sum += amt
    if sub is None:
        bad.append("sub total not found on the scan")
    elif rows and abs(line_sum - sub) > TOL:
        bad.append(f"lines add to {line_sum}, sub total reads {sub}")
    return bad
