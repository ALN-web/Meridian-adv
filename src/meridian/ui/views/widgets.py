"""Widgets used on more than one page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from meridian.store import Store
from meridian.ui.common import REASON_LABEL, chips, inr, money_table, reasons_text

LINE_COLS = {
    "shipment_id": "Shipment",
    "booked_on": "Booked",
    "billed_weight_kg": "Billed kg",
    "actual_weight_kg": "Actual kg",
    "weight_limit_kg": "Limit (+2%)",
    "billed_rate": "Billed rate",
    "card_rate": "Card rate",
    "billed_fuel_pct": "Billed fuel %",
    "month_fuel_pct": "Month fuel %",
    "detention": "Detention",
    "promised_on": "Promised",
    "delivered_on": "Delivered",
    "days_late": "Days late",
    "billed_inr": "Billed",
    "expected_inr": "Expected",
    "reasons": "Why",
}
# which columns to highlight for each reason
REASON_COLS = {
    "weight_over": ["Billed kg", "Actual kg", "Limit (+2%)"],
    "rate_wrong": ["Billed rate", "Card rate"],
    "surcharge_wrong": ["Billed fuel %", "Month fuel %"],
    "detention_unjustified": ["Detention", "Promised", "Delivered", "Days late"],
    "shipment_unknown": ["Shipment"],
    "duplicate_billing": ["Shipment"],
    "no_pod": ["Promised", "Delivered"],
}


def line_table(detail: dict) -> None:
    rows = detail.get("lines") or []
    if not rows:
        st.caption("No line details recorded for this invoice.")
        return
    df = pd.DataFrame(rows)
    codes = df["reasons"].map(lambda r: list(r) if r else [])
    df["reasons"] = codes.map(lambda r: reasons_text(r) if r else "OK")
    df = df[[c for c in LINE_COLS if c in df]].rename(columns=LINE_COLS)

    def hi(row):
        bad = {c for code in codes[row.name] for c in REASON_COLS.get(code, [])}
        return ["background-color: rgba(208,59,59,.16)" if c in bad or (c == "Why" and codes[row.name]) else ""
                for c in row.index]

    kg = st.column_config.NumberColumn(format="%.1f")
    pct = st.column_config.NumberColumn(format="%.1f%%")
    rate = st.column_config.NumberColumn(format="%.2f")
    money_table(df, ["Billed", "Expected", "Detention"], style=lambda sty: sty.apply(hi, axis=1), hide_index=True,
                width="stretch",
                column_config={"Billed kg": kg, "Actual kg": kg, "Limit (+2%)": kg,
                               "Billed rate": rate, "Card rate": rate,
                               "Billed fuel %": pct, "Month fuel %": pct,
                               "Days late": st.column_config.NumberColumn(format="%d")})


def invoice_header(detail: dict) -> None:
    from meridian.ui.common import big

    c = st.columns(4)
    big(c[0], "Printed total", inr(detail.get("printed_total")), f"lines + GST {inr(detail.get('lines_plus_gst'))}")
    credits = detail.get("credit_notes") or []
    big(c[1], "Billed", inr(detail.get("billed_inr")), f"after {len(credits)} credit note(s)" if credits else "")
    big(c[2], "Expected", inr(detail.get("expected_inr")))
    big(c[3], "Difference", inr(detail.get("overcharge_inr")), "dispute exists" if detail.get("already_disputed") else "")
    reasons = detail.get("reasons") or []
    st.markdown("<div style='margin-top:10px'>" + (chips([REASON_LABEL.get(r, r) for r in reasons], "bad") if reasons else chips(["all rules passed"], "ok")) + "</div>",
                unsafe_allow_html=True)


def trace_view(result: dict, key: str) -> None:
    """Trace link (Langfuse) and the local copy of the trace: one span per step."""
    from pathlib import Path

    from meridian.telemetry import read_trace

    tid = result.get("trace_id")
    if not tid:
        st.markdown("<p class='muted'>No trace for this run.</p>", unsafe_allow_html=True)
        return
    url = result.get("trace_url")
    recs = read_trace(tid)
    spans = [r for r in recs if r["type"] == "span"]
    end = next((r for r in recs if r["type"] == "end"), {})
    c = st.columns([3, 1], vertical_alignment="center")
    c[0].markdown(f"<span class='muted'>{len(spans)} spans · {end.get('duration_s', '—')} s · "
                  f"{'Langfuse' if url else 'local copy'} · <span class='mono'>{tid[:12]}…</span></span>", unsafe_allow_html=True)
    if url:
        c[1].link_button("Open in Langfuse", url, width="stretch")
    if spans:
        df = pd.DataFrame(spans)[["end", "name", "page", "outcome", "retries", "duration_ms", "level", "detail"]]
        df["end"] = df["end"].str[11:19]
        colour = {"ERROR": "background-color: rgba(208,59,59,.14)", "WARNING": "background-color: rgba(250,178,25,.16)"}
        st.dataframe(df.style.apply(lambda r: [colour.get(r["level"], "")] * len(r), axis=1), hide_index=True,
                     width="stretch", height=320,
                     column_config={"end": "time", "duration_ms": st.column_config.NumberColumn("ms", format="%d")})
    for a in [r for r in recs if r["type"] == "attachment"]:
        p = Path(a["path"])
        if p.suffix.lower() == ".png" and p.exists():
            st.image(str(p), caption=a["label"], width="stretch")
        elif p.exists():
            st.download_button(a["label"], p.read_bytes(), file_name=p.name, key=f"{key}-{a['label']}")
    st.caption("Personal data and secrets are masked. OTPs are never logged.")


def documents_for(store: Store, run_id: str, labels: list[str]) -> list[dict]:
    want = set(labels)
    return [d for d in store.documents(run_id) if d["label"] in want]


@st.cache_data(show_spinner=False, max_entries=64)
def _page_png(path: str, mtime: float, page: int = 0) -> bytes | None:
    """First page of a PDF as a PNG, for showing evidence next to the numbers."""
    try:
        import io

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        img = pdf[min(page, len(pdf) - 1)].render(scale=1.6).to_pil().convert("RGB")
        from PIL import ImageChops, ImageOps

        # trim the blank paper around the text (portal PDFs are mostly empty A4) and keep a margin
        box = ImageChops.difference(img, ImageOps.invert(ImageOps.invert(img).point(lambda _: 0))).getbbox()
        if box:
            m = 40
            img = img.crop((max(0, box[0] - m), max(0, box[1] - m), min(img.width, box[2] + m), min(img.height, box[3] + m)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _show_doc(col, doc: dict | None, title: str, missing: str) -> None:
    from pathlib import Path

    col.markdown(f"**{title}**")
    if doc is None or not Path(doc["path"]).exists():
        col.markdown(f"<p class='muted'>{missing}</p>", unsafe_allow_html=True)
        return
    p = Path(doc["path"])
    png = _page_png(str(p), p.stat().st_mtime) if p.suffix.lower() == ".pdf" else None
    if png:
        col.image(png, width="stretch")
    elif p.suffix.lower() == ".png":
        col.image(str(p), width="stretch")
    col.download_button(f"Download {p.name}", p.read_bytes(), file_name=p.name, key=f"ev-{doc['id']}", width="stretch")


def evidence(store: Store, run_id: str, detail: dict) -> None:
    """The invoice and a delivery proof side by side, opened on the line that failed."""
    no = detail.get("invoice_no", "")
    lines = detail.get("lines") or []
    sids = [l["shipment_id"] for l in lines]
    docs = {d["label"]: d for d in documents_for(store, run_id, [f"INV_{no}"] + [f"POD_{s}" for s in sids])}
    if not docs:
        return
    first_bad = next((l["shipment_id"] for l in lines if l.get("reasons")), sids[0] if sids else None)
    st.markdown("<span class='label sec-label'>Evidence</span>", unsafe_allow_html=True)

    def why(sid: str) -> str:
        rs = next((l.get("reasons") or [] for l in lines if l["shipment_id"] == sid), [])
        return f"{sid} · " + (", ".join(REASON_LABEL.get(r, r) for r in rs) if rs else "OK")

    sid = None
    if sids:
        sid = st.selectbox("Delivery proof for", sids, index=sids.index(first_bad) if first_bad in sids else 0,
                           format_func=why, key=f"ev-pod-{run_id}-{no}")
    left, right = st.columns(2, gap="medium")
    _show_doc(left, docs.get(f"INV_{no}"), f"Invoice {no}", "The invoice PDF wasn't kept for this run.")
    if sid:
        _show_doc(right, docs.get(f"POD_{sid}"), f"Delivery proof {sid}",
                  "No delivery proof on the portal for this shipment.")
