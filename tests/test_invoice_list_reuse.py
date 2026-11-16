"""The full invoice list is read once per task and then filtered in code — never trusted blindly."""
import asyncio
from datetime import date
from decimal import Decimal

from meridian.config import Settings
from meridian.portal.client import PortalClient
from meridian.portal.tables import InvoiceRow


def row(no, lane, month, status="Open"):
    return InvoiceRow(no, date(2026, month, 10), lane, status, Decimal("100.00"), "100.00")


FULL = [row("A", "PUN-HYD", 9), row("B", "PUN-HYD", 10), row("C", "PUN-BLR", 9, "Paid"), row("D", "PUN-HYD", 9, "Paid")]


def client(portal_rows):
    c = PortalClient(Settings(portal_base_url="https://transindus-portal.onrender.com"), human=None)
    calls = []

    async def fake_step(name, fn):  # stands in for the browser read; records each portal visit
        calls.append(name)
        return list(portal_rows)

    c.step = fake_step
    return c, calls


def test_full_list_read_once_then_filtered_in_code():
    c, calls = client(FULL)
    assert len(asyncio.run(c.search_invoices())) == 4
    hyd = asyncio.run(c.search_invoices("PUN-HYD", "2026-09"))
    one = asyncio.run(c.search_invoices(invoice_no="C"))
    paid = asyncio.run(c.search_invoices(status="paid"))
    assert [r.invoice_no for r in hyd] == ["A", "D"]
    assert [r.invoice_no for r in one] == ["C"]
    assert [r.invoice_no for r in paid] == ["C", "D"]
    assert len(calls) == 1  # one portal read for the whole task
    assert c.log.events[-1]["outcome"] == "reused"


def test_one_invoice_lookup_counts_as_the_full_read():
    c, calls = client(FULL)
    asyncio.run(c.search_invoices(invoice_no="B"))  # T-04 style: the portal has no number box
    asyncio.run(c.search_invoices())  # billing history
    assert len(calls) == 1


def test_lane_read_by_the_portal_is_not_mistaken_for_the_full_list():
    c, calls = client([r for r in FULL if r.lane == "PUN-HYD"])
    asyncio.run(c.search_invoices("PUN-HYD", "2026-09"))
    asyncio.run(c.search_invoices())
    assert len(calls) == 2  # the full list still has to be read


def test_rows_without_a_lane_fall_back_to_the_portal_filter():
    c, calls = client(FULL + [row("E", None, 9)])
    asyncio.run(c.search_invoices())
    asyncio.run(c.search_invoices("PUN-HYD", "2026-09"))
    assert len(calls) == 2  # a lane-less row could otherwise slip into the lane


def test_submitting_a_dispute_forgets_the_list():
    c, calls = client(FULL)
    asyncio.run(c.search_invoices())

    async def stop(*a, **k):
        raise RuntimeError("stop before touching the portal")

    c.open_invoice = stop
    try:
        asyncio.run(c.submit_dispute("A", ["rate_wrong"], Decimal("90")))
    except RuntimeError:
        pass
    asyncio.run(c.search_invoices())
    assert len(calls) == 2
