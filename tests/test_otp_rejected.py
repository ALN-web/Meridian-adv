"""A refused OTP must lead to a fresh login (which sends a new code), never to waiting for a code that won't come."""
import asyncio

import pytest

from meridian.config import Settings
from meridian.portal.client import PortalClient
from meridian.portal.pagestate import PageSnapshot


class Page:
    def __init__(self, url, text):
        self.url, self.text = url, text

    async def inner_text(self, _sel):
        return self.text


def client(url, text, has_otp_field=True):
    c = PortalClient(Settings(portal_base_url="https://transindus-portal.onrender.com"), human=None)
    c.page = Page(url, text)

    async def snap(status=None):
        return PageSnapshot(url=url, title="OTP", text=text, has_otp_field=has_otp_field)

    c.snapshot = snap
    return c


@pytest.mark.parametrize("url,text,rejected", [
    ("https://x/Login/Otp.aspx?msg=bad", "Enter the one-time password", True),
    ("https://x/Login/Otp.aspx", "Invalid or expired OTP. Enter the one-time password", True),
    ("https://x/Login/Otp.aspx", "Incorrect code. Try again", True),
    ("https://x/Login/Otp.aspx", "Enter the one-time password sent to the operator inbox", False),
])
def test_rejection_is_recognised(url, text, rejected):
    assert asyncio.run(client(url, text)._otp_rejected()) is rejected


def test_home_page_after_a_good_code_is_not_a_rejection():
    c = client("https://x/Default.aspx", "Welcome meridian.ap · Invoices", has_otp_field=False)
    assert asyncio.run(c._otp_rejected()) is False
