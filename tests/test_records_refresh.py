"""Hidden test: the portal is reset to a new seed, so Meridian's records must be fresh, not the old copy."""
import httpx
import pytest
from pydantic import SecretStr

from meridian.agent import live
from meridian.config import Settings

HEAD = "shipment_id,booked_on,lane,actual_weight_kg,delivered_on,meridian_ref\n"
OLD = HEAD + "SHP-1,2026-10-01,PUN-BLR,100,2026-10-03,M1\n"
NEW = HEAD + "SHP-9,2026-10-01,PUN-BLR,100,2026-10-03,M9\n"


class Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


@pytest.fixture
def portal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "meridian-shipments.csv").write_text(OLD)  # left over from the public seed
    live._RECORDS_FETCHED.clear()
    monkeypatch.delenv("MERIDIAN_OFFLINE_RECORDS", raising=False)
    return Settings(portal_base_url="https://portal.example", team_key=SecretStr("k"))


def test_real_portal_records_are_downloaded_fresh(portal, monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **k: calls.append(1) or Resp(NEW))
    assert set(live.load_meridian_records(portal)) == {"SHP-9"}
    live.load_meridian_records(portal)
    assert calls == [1]  # once per process, not once per task


def test_old_copy_is_only_a_fallback(portal, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp("<html>error</html>", 500))
    assert set(live.load_meridian_records(portal)) == {"SHP-1"}


def test_offline_switch_keeps_the_local_copy(portal, monkeypatch):
    monkeypatch.setenv("MERIDIAN_OFFLINE_RECORDS", "1")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("must not download"))
    assert set(live.load_meridian_records(portal)) == {"SHP-1"}
