from datetime import date
from decimal import Decimal

import pytest

from meridian.parsing import parse_amount, parse_date, to_paise


@pytest.mark.parametrize(
    "text,expected",
    [
        ("14-Oct-26", date(2026, 10, 14)),
        ("01-Aug-2026", date(2026, 8, 1)),
        ("2026-09-30", date(2026, 9, 30)),
        (" 14/10/2026 ", date(2026, 10, 14)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Rs. 1,23,456.00", Decimal("123456.00")),
        ("₹ 1,234.5", Decimal("1234.5")),
        ("INR 500", Decimal("500")),
        ("(1,000.00)", Decimal("-1000.00")),
        ("-250.75", Decimal("-250.75")),
        ("12,34,56,789.10", Decimal("123456789.10")),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "Rs.", "1.2.3"])
def test_parse_amount_rejects(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


def test_to_paise_half_up():
    assert to_paise(Decimal("10.005")) == Decimal("10.01")
    assert to_paise(Decimal("10.004")) == Decimal("10.00")
