"""Decide what kind of page we're on from a cheap snapshot — before trusting its content.

Pure function, so it's unit-tested without a browser. Keywords are a first guess; tune them
from recon output (runs/recon/) once real pages are seen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class PageState(str, Enum):
    OK = "ok"
    LOGIN = "login"
    OTP = "otp"
    CAPTCHA = "captcha"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    NOTICE = "notice"  # overlay / modal blocking clicks


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    title: str
    text: str
    has_overlay: bool = False
    has_password_field: bool = False
    has_otp_field: bool = False
    has_captcha: bool = False
    http_status: int | None = None


_RATE = re.compile(r"too many requests|too fast|slow down|rate limit|try again in \d+", re.I)
_ERROR = re.compile(
    r"server error in '/' application|runtime error|internal server error|service unavailable|"
    r"an error has occurred|unexpected error|bad gateway|gateway time-?out|page cannot be displayed",
    re.I,
)
_EXPIRED = re.compile(r"session (has )?(expired|timed out)|please log ?in again|you have been logged out", re.I)
_OTP = re.compile(r"one[- ]time password|\bOTP\b|verification code", re.I)
_CAPTCHA = re.compile(r"captcha|i'?m not a robot|verify you are human", re.I)


def classify(s: PageSnapshot) -> PageState:
    text = f"{s.title}\n{s.text}"
    if s.has_captcha or _CAPTCHA.search(text):
        return PageState.CAPTCHA
    if s.http_status == 429 or _RATE.search(text):
        return PageState.RATE_LIMITED
    if s.has_otp_field or (_OTP.search(text) and not s.has_password_field):
        return PageState.OTP
    if s.has_password_field or "/login.aspx" in s.url.lower() or _EXPIRED.search(text):
        return PageState.LOGIN
    if (s.http_status is not None and s.http_status >= 500) or _ERROR.search(text):
        return PageState.ERROR
    if s.has_overlay:
        return PageState.NOTICE
    return PageState.OK
