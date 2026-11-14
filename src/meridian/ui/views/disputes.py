"""Disputes: every proposal and what happened to it, with receipts and screenshots."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from meridian.ui.common import big, get_store, hhmm, inr

ORDER = ("pending", "approved", "submitted", "confirmed", "rejected", "skipped", "failed")


def render() -> None:
    store = get_store()
    st.title("Disputes")
    st.caption("Lifecycle: proposed by the rules → approved or rejected by a person → dispute list checked → submitted once "
               "→ confirmed in the portal's list. A success message alone is never treated as proof.")
    rows = store.disputes()
    if not rows:
        st.info("No disputes proposed yet. Run a dispute task (e.g. T-19 or T-20).")
        return
    counts = Counter(d["status"] for d in rows)
    live = Counter(d["invoice_no"] for d in rows if d["status"] in ("submitted", "confirmed"))
    c = st.columns(5)
    big(c[0], "Waiting for approval", str(counts.get("pending", 0)))
    big(c[1], "Confirmed on portal", str(counts.get("confirmed", 0)))
    big(c[2], "Rejected by a person", str(counts.get("rejected", 0)))
    big(c[3], "Skipped (already existed)", str(counts.get("skipped", 0)))
    big(c[4], "Duplicates", str(sum(v - 1 for v in live.values() if v > 1)), "target 0")
    claimed = sum((Decimal(d["billed_inr"]) - Decimal(d["expected_inr"]) for d in rows if d["status"] == "confirmed"), Decimal(0))
    st.markdown(f"<div class='lbl'>Overcharge under dispute</div><div class='big'>{inr(claimed)}</div>", unsafe_allow_html=True)

    status = st.multiselect("Status", ORDER, default=[s for s in ORDER if counts.get(s)], key="disp_status")
    view = [d for d in rows if d["status"] in status]
    if view:
        df = pd.DataFrame(view)
        df["reasons"] = df["reasons"].map(", ".join)
        df["overcharge"] = df.apply(lambda x: float(Decimal(x["billed_inr"]) - Decimal(x["expected_inr"])), axis=1)
        df["billed_inr"] = df["billed_inr"].astype(float)
        df["expected_inr"] = df["expected_inr"].astype(float)
        df["decided_at"] = df["decided_at"].map(hhmm)
        money = st.column_config.NumberColumn(format="₹ %.2f")
        st.dataframe(df[["invoice_no", "status", "reasons", "billed_inr", "expected_inr", "overcharge", "portal_ref",
                         "decided_by", "decided_at", "note"]],
                     hide_index=True, width="stretch",
                     column_config={"billed_inr": money, "expected_inr": money, "overcharge": money})

    st.subheader("Receipts and screenshots")
    shown = 0
    for d in rows:
        if d["status"] != "confirmed":
            continue
        safe = d["invoice_no"].replace("/", "_")
        docs = [x for x in store.documents(d["run_id"]) if x["kind"] in ("screenshot", "dispute_receipt") and safe in x["label"].replace("/", "_")]
        if not docs:
            continue
        shown += 1
        with st.expander(f"{d['invoice_no']} · {d['portal_ref'] or ''}"):
            for x in docs:
                p = Path(x["path"])
                if p.suffix.lower() == ".png" and p.exists():
                    st.image(str(p), caption=x["label"], width="stretch")
                elif p.exists():
                    st.download_button(f"⬇ {x['label']}", p.read_bytes(), file_name=p.name, key=f"dr-{x['id']}")
    if not shown:
        st.caption("No receipts yet.")
