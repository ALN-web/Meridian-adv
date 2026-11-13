"""Playwright client for the TransIndus portal.

TODO: login (OTP -> pause for a human), invoice search + pagination, invoice detail / PDF,
credit notes, PODs, rate card, fuel surcharge, dispute list + form.
Every step gets a timeout, retry with backoff, and an explicit done/failed check. At most 2 req/s.
"""
