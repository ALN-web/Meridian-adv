"""Human-in-the-loop gate. The agent never reads the OTP inbox and never solves CAPTCHAs.

The UI provides its own implementation; ``ConsoleHumanGate`` is for scripts like recon.
"""
from __future__ import annotations

import asyncio
from typing import Protocol


class HumanGate(Protocol):
    async def request_otp(self) -> str:
        """Ask a person for the one-time password they see in the operator inbox."""
        ...

    async def request_captcha(self) -> None:
        """Ask a person to solve the CAPTCHA in the visible browser; return when done."""
        ...


class ConsoleHumanGate:
    async def request_otp(self) -> str:
        return (await asyncio.to_thread(input, "\n[HUMAN] Portal asks for a one-time password. "
                                               "Open the operator inbox yourself and type it here: ")).strip()

    async def request_captcha(self) -> None:
        await asyncio.to_thread(input, "\n[HUMAN] CAPTCHA shown. Solve it in the browser window, then press Enter: ")
