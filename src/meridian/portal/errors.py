"""Portal failure types. Each tells the runner what to do next."""


class PortalError(Exception):
    """Transient portal problem (error page, timeout, slow load). Retry with backoff."""


class SessionExpired(PortalError):
    """Logged out mid-task. Log in again and continue from the checkpoint."""


class RateLimited(PortalError):
    """Portal said we're going too fast. Back off longer, then retry."""


class HumanNeeded(Exception):
    """Pause the task: a person must act (OTP, CAPTCHA, unreadable document)."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class LoginFailed(Exception):
    """Credentials rejected. Do NOT retry blindly — repeated failures trigger a CAPTCHA."""


class PageNotUnderstood(PortalError):
    """The page doesn't look like what we expected. Candidate for the vision fallback."""
