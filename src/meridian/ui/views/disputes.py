"""Disputes: every proposal and what happened to it, with receipts and screenshots."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from meridian.ui.common import big, get_store, header, hhmm, inr

ORDER = ("pending", "approved", "submitted", "confirmed", "rejected", "skipped", "failed")
FLOW = "<span class='pill p-grey'>Proposed</span> → <span class='pill p-wait'>Approved</span> → " \
       "<span class='pill p-grey'>List checked</span> → <span class='pill p-grey'>Submitted</span> → " \
       "<span class='pill p-ok'>Confirmed</span>"


def render() -> None:
    store = get_store()
    header("Disputes", "Raised only after you approve. Confirmed in the portal's own list.")
    st.markdown(FLOW, unsafe_allow_html=True)
    rows = store.disputes()
    modes = {rid: (r.mode if (r := store.get_run(rid)) else "demo") for rid in {d["run_id"] for d in rows}}
    real = [d for d in rows if modes[d["run_id"]] == "live"]
    if real and len(real) < len(rows):
        # Practice disputes (demo / fake portal) never mix with the real portal's by default.
        if not st.toggle(f"Include practice-portal disputes ({len(rows) - len(real)})", key="disp_demo"):
            rows = real
    if not rows:
        st.info("No disputes yet. Run a dispute task, e.g. T-19.")
        return
    counts = Counter(d["status"] for d in rows)
    live = Counter(d["invoice_no"] for d in rows if d["status"] in ("submitted", "confirmed"))
    claimed = sum((Decimal(d["billed_inr"]) - Decimal(d["expected_inr"]) for d in rows if d["status"] == "confirmed"), Decimal(0))
    st.write("")
    c = st.columns(5)
    big(c[0], "To approve", str(counts.get("pending", 0)))
    big(c[1], "Confirmed", str(counts.get("confirmed", 0)))
    big(c[2], "Rejected", str(counts.get("rejected", 0)))
    big(c[3], "Duplicates", str(sum(v - 1 for v in live.values() if v > 1)))
    big(c[4], "Under dispute", inr(claimed))
    st.write("")

    status = st.pills("Status", ORDER, selection_mode="multi", default=[s for s in ORDER if counts.get(s)],
                      key="disp_status", label_visibility="collapsed") or []
    view = [d for d in rows if d["status"] in status]
    if view:
        df = pd.DataFrame(view)
        df["reasons"] = df["reasons"].map(", ".join)
        df["overcharge"] = df.apply(lambda x: float(Decimal(x["billed_inr"]) - Decimal(x["expected_inr"])), axis=1)
        df["decided_at"] = df["decided_at"].map(hhmm)
        money = lambda t: st.column_config.NumberColumn(t, format="₹ %.2f")  # noqa: E731
        st.dataframe(df[["invoice_no", "status", "reasons", "overcharge", "portal_ref", "decided_at"]],
                     hide_index=True, width="stretch",
                     column_config={"invoice_no": "Invoice", "status": "Status", "reasons": "Reasons",
                                    "overcharge": money("Over"), "portal_ref": "Portal ref", "decided_at": "Decided"})

    receipts = []
    for d in rows:
        if d["status"] != "confirmed":
            continue
        safe = d["invoice_no"].replace("/", "_")
        docs = [x for x in store.documents(d["run_id"])
                if x["kind"] in ("screenshot", "dispute_receipt") and safe in x["label"].replace("/", "_")]
        if docs:
            receipts.append((d, docs))
    if receipts:
        st.markdown("**Receipts**")
        for d, docs in receipts:
            with st.expander(f"{d['invoice_no']} · {d['portal_ref'] or ''}"):
                for x in docs:
                    p = Path(x["path"])
                    if p.suffix.lower() == ".png" and p.exists():
                        st.image(str(p), caption=x["label"], width="stretch")
                    elif p.exists():
                        st.download_button(x["label"], p.read_bytes(), file_name=p.name, key=f"dr-{x['id']}")
