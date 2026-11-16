"""Amounts on the operator screen use Indian digit grouping, as Meridian's staff write them."""
import pytest

from meridian.ui.common import inr


@pytest.mark.parametrize("value,shown", [
    ("0", "₹0.00"), ("999", "₹999.00"), ("1000", "₹1,000.00"), ("12345.6", "₹12,345.60"),
    ("171710.58", "₹1,71,710.58"), ("1146895.32", "₹11,46,895.32"), ("12345678.9", "₹1,23,45,678.90"),
    ("-23840.5", "-₹23,840.50"), (None, "—"),
])
def test_indian_grouping(value, shown):
    assert inr(value) == shown
