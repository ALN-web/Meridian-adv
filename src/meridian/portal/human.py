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


class StoreHumanGate:
    """Asks the operator screen (via the run store) and waits for the answer."""

    def __init__(self, store, run_id: str, on_wait=None, on_resume=None, timeout_s: float = 900):
        self.store, self.run_id, self.timeout_s = store, run_id, timeout_s
        self.on_wait, self.on_resume = on_wait, on_resume

    async def _ask(self, kind: str) -> str:
        rid = self.store.request_human(self.run_id, kind)
        if self.on_wait:
            self.on_wait(kind)
        waited = 0.0
        while waited < self.timeout_s:
            ans = self.store.take_answer(rid)
            if ans is not None:
                if self.on_resume:
                    self.on_resume(kind)
                return ans
            await asyncio.sleep(0.5)
            waited += 0.5
        self.store.answer_human(rid, "")   # close the stale request so the screen stops asking
        self.store.take_answer(rid)
        from meridian.portal.errors import HumanNeeded

        raise HumanNeeded(kind, "no answer from the operator in time")

    async def request_otp(self) -> str:
        return await self._ask("otp")

    async def request_captcha(self) -> None:
        await self._ask("captcha")


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
