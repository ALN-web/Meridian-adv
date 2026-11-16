"""Reading the dispute list must never fail open: a misread list could lead to a duplicate dispute."""
import asyncio

import pytest

from meridian.config import Settings
from meridian.portal.client import PortalClient
from meridian.portal.errors import PageNotUnderstood


def test_invoice_numbers_found_whatever_the_column_is_called():
    seen_on_portal = [  # header names seen, plus renamed variants like the invoice list's
        {"Dispute No": "DSP-5008", "Invoice No": "TIR/26-27/10170", "Status": "Open"},
        {"Ref #": "DSP-4100", "Inv #": "TIR/26-27/10172", "Status": "Open"},
        {"Ticket": "DSP-4099", "Bill Ref": " TIR/26-27/10166 ", "Reasons": "Calculation error"},
        {"Dispute": "DSP-4098", "Details": "Raised for TIR/26-27/10150 (rate)"},
    ]
    assert PortalClient.disputed_invoices(seen_on_portal) == {
        "TIR/26-27/10170", "TIR/26-27/10172", "TIR/26-27/10166", "TIR/26-27/10150"}


def test_empty_list_means_nothing_disputed():
    assert PortalClient.disputed_invoices([]) == set()


def test_rows_without_any_invoice_number_raise_instead_of_meaning_none():
    with pytest.raises(PageNotUnderstood):
        PortalClient.disputed_invoices([{"Dispute No": "DSP-1", "Status": "Open"}])


def test_dispute_grid_not_found_raises_instead_of_returning_empty():
    c = PortalClient(Settings(portal_base_url="https://transindus-portal.onrender.com"), human=None)

    class Page:
        async def inner_text(self, _):
            return "Disputes · some layout we have never seen"

    c.page = Page()

    async def nothing(*a, **k):
        return None

    async def no_grid(_pat):
        raise PageNotUnderstood("no grid")

    async def step(name, fn):  # run once, no retries
        return await fn()

    c.open_menu, c.main_grid, c.debug_dump, c.step = nothing, no_grid, nothing, step
    with pytest.raises(PageNotUnderstood):
        asyncio.run(c.dispute_list())
