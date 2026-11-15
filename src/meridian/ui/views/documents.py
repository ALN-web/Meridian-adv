"""Documents: every invoice PDF, proof of delivery and write-action screenshot a run collected."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from meridian.portal.pdftext import pdf_text
from meridian.ui.common import get_store, header, pick_run

KINDS = {"invoice_pdf": "Invoices", "pod_pdf": "Delivery proofs", "screenshot": "Screenshots", "dispute_receipt": "Receipts"}


@st.cache_data(show_spinner=False)
def _text(path: str, mtime: float) -> str:
    return pdf_text(path)


def render() -> None:
    store = get_store()
    header("Documents", "Everything the agent downloaded or captured.")
    c = st.columns([2, 1], vertical_alignment="bottom")
    with c[0]:
        run = pick_run(store, "doc_run")
    if run is None:
        st.info("No runs yet.")
        return
    docs = store.documents(run.id)
    q = c[1].text_input("Search", key="doc_q", placeholder="Invoice or shipment").strip().upper()
    if not docs:
        st.info("No documents in this run.")
        return
    kinds = [k for k in KINDS if any(d["kind"] == k for d in docs)]
    tabs = st.tabs([f"{KINDS[k]} · {sum(d['kind'] == k for d in docs)}" for k in kinds])
    for tab, kind in zip(tabs, kinds):
        with tab:
            group = [d for d in docs if d["kind"] == kind and (not q or q in d["label"].upper())]
            if not group:
                st.markdown("<p class='muted'>No match.</p>", unsafe_allow_html=True)
            for d in group:
                p = Path(d["path"])
                with st.expander(d["label"]):
                    if not p.exists():
                        st.warning("File no longer on disk.")
                        continue
                    if p.suffix.lower() == ".png":
                        st.image(str(p), width="stretch")
                    else:
                        text = _text(str(p), p.stat().st_mtime)
                        if text.strip():
                            st.code(text, language=None)
                        else:
                            st.warning("Scanned image, no readable text. A person must check it.")
                    st.download_button("Download", p.read_bytes(), file_name=p.name, key=f"doc-{d['id']}")
