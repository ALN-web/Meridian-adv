"""Documents: every invoice PDF, proof of delivery and write-action screenshot a run collected."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from meridian.portal.pdftext import pdf_text
from meridian.ui.common import get_store, hhmm, pick_run

KINDS = {"invoice_pdf": "Invoice PDFs", "pod_pdf": "Proofs of delivery", "screenshot": "Write-action screenshots",
         "dispute_receipt": "Dispute receipts"}


@st.cache_data(show_spinner=False)
def _text(path: str, mtime: float) -> str:
    return pdf_text(path)


def render() -> None:
    store = get_store()
    st.title("Documents")
    run = pick_run(store, "doc_run")
    if run is None:
        st.info("No runs yet.")
        return
    docs = store.documents(run.id)
    if not docs:
        st.info("This run hasn't collected any documents.")
        return
    q = st.text_input("Filter by name (invoice or shipment number)", key="doc_q").strip().upper()
    for kind, title in KINDS.items():
        group = [d for d in docs if d["kind"] == kind and (not q or q in d["label"].upper())]
        if not group:
            continue
        st.subheader(f"{title} ({len(group)})")
        for d in group:
            p = Path(d["path"])
            with st.expander(f"{d['label']} · {hhmm(d['ts'])}"):
                if not p.exists():
                    st.warning("File no longer on disk.")
                    continue
                if p.suffix.lower() == ".png":
                    st.image(str(p), caption="Personal data and login fields are masked", width="stretch")
                else:
                    text = _text(str(p), p.stat().st_mtime)
                    if text.strip():
                        st.code(text, language=None)
                    else:
                        st.warning("No readable text — a scanned image. The agent does not guess; a person must read it.")
                st.download_button("⬇ Download", p.read_bytes(), file_name=p.name, key=f"doc-{d['id']}")
