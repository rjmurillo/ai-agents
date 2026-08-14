"""End-to-end agreement test: creator names it, every consumer finds it.

Issue #4779. Controlled-instant unit tests prove that the shared date helpers
select the host-local calendar date when it differs from UTC. This module has a
different responsibility: under real process timezones, a real creator and all
date-prefix consumers must agree on the same filename. It intentionally tests
pipeline agreement rather than independently proving the date authority.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_INIT_SCRIPTS = REPO_ROOT / ".claude" / "skills" / "session-init" / "scripts"
PRECOMPACT_DIR = REPO_ROOT / ".claude" / "hooks" / "PreCompact"

for _path in (str(SESSION_INIT_SCRIPTS), str(PRECOMPACT_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import invoke_compact_checkpoint  # noqa: E402
import new_session_log_json  # noqa: E402

from scripts.hook_utilities.utilities import get_recent_session_log  # noqa: E402
from scripts.validation.git_hook_policy import (  # noqa: E402
    _recent_session_candidates,
)

# Both drift directions plus the no-offset control. Kiritimati is UTC+14, so its
# host date runs a day ahead of UTC; Los Angeles is UTC-7/8, a day behind.
_TIMEZONES = ["UTC", "Pacific/Kiritimati", "America/Los_Angeles"]

pytestmark = pytest.mark.skipif(
    not hasattr(time, "tzset"),
    reason="process timezone switching requires time.tzset",
)


@pytest.fixture(params=_TIMEZONES)
def host_timezone(request: pytest.FixtureRequest):
    """Set a real process timezone so ``datetime.now()`` reads host-local."""
    original = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    try:
        yield request.param
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def _create_session_log(tmp_path: Path) -> Path:
    """Drive the real JSON creator; return the file it named."""
    sessions_dir = tmp_path / ".agents" / "sessions"
    sessions_dir.mkdir(parents=True)
    with patch.object(new_session_log_json, "_get_repo_root", return_value=str(tmp_path)), \
         patch.object(new_session_log_json, "_get_branch", return_value="fix/4779-e2e"), \
         patch.object(new_session_log_json, "_get_commit", return_value="abc1234"):
        exit_code = new_session_log_json.main(
            ["--session-number", "1", "--objective", "end to end"]
        )
    assert exit_code == 0
    created = list(sessions_dir.glob("*.json"))
    assert len(created) == 1
    return created[0]


def test_hook_utilities_consumer_finds_host_dated_log(host_timezone, tmp_path):
    """``get_recent_session_log`` locates the creator's host-dated file."""
    created = _create_session_log(tmp_path)
    sessions_dir = created.parent

    result = get_recent_session_log(str(sessions_dir))

    assert result is not None, f"consumer missed the log under TZ={host_timezone}"
    assert result.name == created.name


def test_git_hook_policy_consumer_finds_host_dated_log(host_timezone, tmp_path):
    """``_recent_session_candidates`` includes the creator's host-dated file."""
    created = _create_session_log(tmp_path)
    sessions_dir = created.parent

    candidates = _recent_session_candidates(sessions_dir)

    assert candidates is not None, f"scan returned None under TZ={host_timezone}"
    assert created in candidates, f"candidate set missed the log under TZ={host_timezone}"


def _create_then_scan_across_timezones(
    tmp_path: Path,
    *,
    creator_timezone: str,
    scanner_timezone: str,
    creator_date: str,
    scanner_today: str,
) -> Path:
    """Create for one host date, then scan from another fixed host date."""
    os.environ["TZ"] = creator_timezone
    time.tzset()
    with patch.object(
        new_session_log_json, "host_session_date", return_value=creator_date
    ):
        created = _create_session_log(tmp_path)

    os.environ["TZ"] = scanner_timezone
    time.tzset()
    scanner_yesterday = (
        date.fromisoformat(scanner_today) - timedelta(days=1)
    ).isoformat()
    with patch(
        "scripts.validation.git_hook_policy.recent_host_session_dates",
        return_value=(scanner_today, scanner_yesterday),
    ):
        candidates = _recent_session_candidates(created.parent)

    assert candidates is not None
    assert created in candidates
    return created


def test_git_hook_policy_finds_next_day_log_after_timezone_switch(tmp_path):
    """A UTC scanner finds a log created for a UTC+14 host next day."""
    original = os.environ.get("TZ")
    try:
        _create_then_scan_across_timezones(
            tmp_path,
            creator_timezone="Pacific/Kiritimati",
            scanner_timezone="UTC",
            creator_date="2026-08-09",
            scanner_today="2026-08-08",
        )
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def test_git_hook_policy_finds_log_across_extreme_timezone_switch(tmp_path):
    """A UTC-12 scanner finds a UTC+14 creator date two days ahead."""
    original = os.environ.get("TZ")
    try:
        _create_then_scan_across_timezones(
            tmp_path,
            creator_timezone="Pacific/Kiritimati",
            scanner_timezone="Etc/GMT+12",
            creator_date="2026-08-10",
            scanner_today="2026-08-08",
        )
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def test_git_hook_policy_finds_log_across_reverse_timezone_switch(tmp_path):
    """A UTC+14 scanner finds a UTC-12 creator date two days behind."""
    original = os.environ.get("TZ")
    try:
        _create_then_scan_across_timezones(
            tmp_path,
            creator_timezone="Etc/GMT+12",
            scanner_timezone="Pacific/Kiritimati",
            creator_date="2026-08-08",
            scanner_today="2026-08-10",
        )
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def test_checkpoint_fallback_consumer_finds_host_dated_log(host_timezone, tmp_path):
    """The checkpoint fallback locates the creator's host-dated file."""
    created = _create_session_log(tmp_path)
    sessions_dir = created.parent

    result = invoke_compact_checkpoint._fallback_get_recent_session_log(
        str(sessions_dir)
    )

    assert result is not None, f"fallback missed the log under TZ={host_timezone}"
    assert Path(result).name == created.name


def test_created_filename_and_payload_agree(host_timezone, tmp_path):
    """The real creator uses one date consistently in filename and payload.

    The controlled-instant authority assertions live in
    ``tests/skills/session/test_date_helpers.py``; this end-to-end assertion
    covers agreement only.
    """
    created = _create_session_log(tmp_path)

    payload = json.loads(created.read_text(encoding="utf-8"))
    assert created.name == f"{payload['session']['date']}-session-1.json"
