"""Tiny dependency-free PDF writer for the fake portal (text PDFs and text-less "scans")."""
from __future__ import annotations


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace").decode("latin-1")


def make_pdf(lines: list[str], *, scanned: bool = False) -> bytes:
    """One-page PDF. ``scanned=True`` draws grey boxes instead of text, like an image-only scan."""
    if scanned:
        ops = ["0.6 g"] + [f"72 {720 - i * 22} {200 + (i * 37) % 250} 12 re f" for i in range(len(lines) or 6)]
    else:
        ops = ["BT /F1 11 Tf 14 TL 72 760 Td"] + [f"({_esc(l)}) Tj T*" for l in lines] + ["ET"]
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
