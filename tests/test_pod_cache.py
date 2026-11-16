"""Delivery proofs are cached on disk: confident ones are reused, anything doubtful is fetched again."""
import asyncio
from datetime import date

import pytest

from meridian.config import Settings
from meridian.portal.client import PortalClient
from meridian.reconcile.types import Pod

REAL = "https://transindus-portal.onrender.com"


def client(base=REAL):
    return PortalClient(Settings(portal_base_url=base), human=None)


@pytest.fixture(autouse=True)
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cache lives under ./runs/cache


def fetcher(c, result):
    calls = []

    async def fake(sid):
        calls.append(sid)
        return result

    c._fetch_pod = fake
    return calls


def test_confident_pod_is_fetched_once_then_cached(tmp_path):
    pdf = tmp_path / "POD_SHP-1.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    good = Pod("SHP-1", date(2026, 8, 24), date(2026, 8, 25), confident=True)
    c = client()
    calls = fetcher(c, (good, pdf, False))
    assert asyncio.run(c.get_pod("SHP-1")) == (good, pdf)

    c2 = client()  # a later run, new browser session
    calls2 = fetcher(c2, (None, None, False))
    pod, got_pdf = asyncio.run(c2.get_pod("SHP-1"))
    assert (pod, got_pdf) == (good, pdf)
    assert calls == ["SHP-1"] and calls2 == []
    assert c2.log.events[-1]["outcome"] == "cached"


@pytest.mark.parametrize("result", [
    (Pod("SHP-2", None, None, confident=False), None, False),                       # unreadable
    (Pod("SHP-2", date(2026, 8, 1), date(2026, 8, 2), confident=True), None, True),  # PDF download failed
    (None, None, False),                                                             # no POD on the portal yet
])
def test_doubtful_pods_are_not_cached(result):
    c = client()
    fetcher(c, result)
    asyncio.run(c.get_pod("SHP-2"))
    c2 = client()
    calls = fetcher(c2, (None, None, False))
    asyncio.run(c2.get_pod("SHP-2"))
    assert calls == ["SHP-2"]


def test_cached_pod_refetched_when_its_pdf_is_gone(tmp_path):
    pdf = tmp_path / "POD_SHP-3.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    good = Pod("SHP-3", date(2026, 9, 1), date(2026, 9, 4), confident=True)
    c = client()
    fetcher(c, (good, pdf, False))
    asyncio.run(c.get_pod("SHP-3"))
    pdf.unlink()
    c2 = client()
    calls = fetcher(c2, (good, None, False))
    asyncio.run(c2.get_pod("SHP-3"))
    assert calls == ["SHP-3"]


def test_fake_portal_is_never_cached():
    good = Pod("SHP-4", date(2026, 9, 1), date(2026, 9, 2), confident=True)
    c = client("http://127.0.0.1:8600")
    fetcher(c, (good, None, False))
    asyncio.run(c.get_pod("SHP-4"))
    c2 = client("http://127.0.0.1:8600")
    calls = fetcher(c2, (good, None, False))
    asyncio.run(c2.get_pod("SHP-4"))
    assert calls == ["SHP-4"]
