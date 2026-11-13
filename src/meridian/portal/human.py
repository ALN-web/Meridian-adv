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
    async def _ask(self, prompt: str) -> str:
        try:
            return (await asyncio.to_thread(input, prompt)).strip()
        except EOFError:
            # Terminal closed or not interactive: stop cleanly instead of crashing.
            from meridian.portal.errors import HumanNeeded

            raise HumanNeeded("no_terminal", "run this script in an interactive terminal") from None

    async def request_otp(self) -> str:
        return await self._ask("\n[HUMAN] Portal asks for a one-time password. "
                               "Open the operator inbox yourself and type it here: ")

    async def request_captcha(self) -> None:
        await self._ask("\n[HUMAN] CAPTCHA shown. Solve it in the browser window, then press Enter: ")
