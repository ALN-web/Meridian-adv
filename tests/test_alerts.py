"""Operator alerts: what is waiting, the tab title, and the OTP countdown."""
import json
import re

from meridian.ui import alerts


def test_items_cover_otps_and_dispute_approvals():
    got = alerts.items([{"id": "h1", "kind": "otp", "created": 10.0}],
                       [{"id": "d1", "created": 20.0, "invoice_no": "TIR/26-27/10170"}])
    assert got == [{"id": "h1", "kind": "otp", "created": 10.0}, {"id": "d1", "kind": "approval", "created": 20.0}]


def test_title_puts_the_otp_first():
    assert alerts.title_for([{"kind": "approval"}, {"kind": "otp"}]).startswith("(!) OTP needed")
    assert alerts.title_for([{"kind": "approval"}]).startswith("(!) Approval needed")
    assert alerts.title_for([{"kind": "captcha"}]).startswith("(!) Needs you")


def test_otp_countdown_uses_the_newest_code():
    reqs = [{"kind": "otp", "created": 1000.0}, {"kind": "otp", "created": 1100.0}, {"kind": "captcha", "created": 1200.0}]
    assert alerts.otp_seconds_left(reqs, now=1160.0) == 240
    assert alerts.otp_seconds_left(reqs, now=2000.0) == 0
    assert alerts.otp_seconds_left([{"kind": "captcha", "created": 1.0}]) is None


def test_script_carries_data_and_stops_when_nothing_waits():
    on = alerts.script([{"id": "h1", "kind": "otp", "created": 1.0}], 301.0)
    data = json.loads(re.search(r"const W = window.parent, D = W.document, S = (\{.*?\});", on).group(1))
    assert data["items"][0]["id"] == "h1" and data["deadline"] == 301.0 and data["title"].startswith("(!)")
    off = alerts.script([], None)
    assert '"items": []' in off and "D.title = A.base" in off


def test_script_never_answers_anything():
    js = alerts.script([{"id": "h1", "kind": "otp", "created": 1.0}], 301.0)
    for action in ("fetch(", "XMLHttpRequest", ".click()", ".submit(", "sendBeacon", "input", "textarea"):
        assert action not in js, action  # attention only: no network calls, clicks or form fields
    sound_free = re.sub(r"\b(frequency|gain)\.value\b", "", js)  # the beep's pitch and volume
    assert ".value" not in sound_free  # never types a value anywhere
