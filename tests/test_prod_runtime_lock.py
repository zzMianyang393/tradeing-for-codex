from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from prod.runtime_lock import RuntimeLock, is_lock_stale


def test_is_lock_stale_pure():
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    fresh = {"acquired_at": "2026-07-17T11:30:00Z"}
    stale = {"acquired_at": "2026-07-17T10:00:00Z"}
    assert is_lock_stale(fresh, now=now, stale_after=timedelta(minutes=45)) is False
    assert is_lock_stale(stale, now=now, stale_after=timedelta(minutes=45)) is True
    assert is_lock_stale({}, now=now) is True


def test_runtime_lock_exclusive(tmp_path: Path):
    lock_path = tmp_path / "prod.lock"
    with RuntimeLock(lock_path, stale_after=timedelta(minutes=45)):
        second = RuntimeLock(lock_path, stale_after=timedelta(minutes=45))
        with pytest.raises(TimeoutError):
            second.acquire(timeout_seconds=0.0)
    # after release, reacquire works
    with RuntimeLock(lock_path):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_runtime_lock_reclaims_stale(tmp_path: Path):
    lock_path = tmp_path / "stale.lock"
    old = {
        "token": "old",
        "owner": "dead",
        "acquired_at": "2020-01-01T00:00:00Z",
        "pid": 1,
    }
    import json

    lock_path.write_text(json.dumps(old), encoding="utf-8")
    with RuntimeLock(lock_path, stale_after=timedelta(minutes=1)):
        assert lock_path.exists()
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["token"] != "old"
