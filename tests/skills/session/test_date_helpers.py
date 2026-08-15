"""Tests for the shared host-local date helper (Issue #4779).

Session logs are named by the contributor's current session date, which is the
host local date, not UTC. Near midnight UTC the two diverge. These tests fake
the clock so they never depend on the machine's real timezone or wall clock.
"""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-init"


@pytest.fixture(autouse=True)
def _add_skill_to_path():
    import sys

    path = str(SKILL_DIR)
    added = path not in sys.path
    if added:
        sys.path.insert(0, path)
    yield
    if added:
        sys.path.remove(path)


def _naive_local(utc_instant: datetime, offset_hours: int) -> datetime:
    """Local naive datetime a host at ``offset_hours`` would read.

    Mirrors ``datetime.now()`` (no tzinfo) for a host in that offset.
    """
    tz = timezone(timedelta(hours=offset_hours))
    return utc_instant.astimezone(tz).replace(tzinfo=None)


def test_host_session_date_when_host_behind_utc_returns_host_date():
    """Host at -0700; UTC has rolled to the next day but the host has not.

    Edge: the reported bug. UTC date is one day ahead of the host date.
    """
    from session_init.date_helpers import host_session_date

    utc_instant = datetime(2026, 8, 9, 6, 30, tzinfo=UTC)  # UTC date 2026-08-09
    assert utc_instant.strftime("%Y-%m-%d") == "2026-08-09"

    result = host_session_date(now=lambda: _naive_local(utc_instant, -7))

    assert result == "2026-08-08"  # host local date, not UTC


def test_host_session_date_when_host_ahead_utc_returns_host_date():
    """Host at +1000; the host has rolled to the next day but UTC has not."""
    from session_init.date_helpers import host_session_date

    utc_instant = datetime(2026, 8, 8, 16, 0, tzinfo=UTC)  # UTC date 2026-08-08
    assert utc_instant.strftime("%Y-%m-%d") == "2026-08-08"

    result = host_session_date(now=lambda: _naive_local(utc_instant, 10))

    assert result == "2026-08-09"  # host local date, not UTC


def test_host_session_date_positive_formats_injected_local_time():
    """Positive: a plain local datetime formats as YYYY-MM-DD."""
    from session_init.date_helpers import host_session_date

    result = host_session_date(now=lambda: datetime(2026, 8, 14, 12, 0, 0))

    assert result == "2026-08-14"


def test_host_session_date_boundary_midnight_and_last_second():
    """Edge: exactly midnight and one second before midnight."""
    from session_init.date_helpers import host_session_date

    assert host_session_date(now=lambda: datetime(2026, 8, 14, 0, 0, 0)) == "2026-08-14"
    assert host_session_date(now=lambda: datetime(2026, 8, 13, 23, 59, 59)) == "2026-08-13"


def test_session_date_helper_default_clocks_are_local_now_not_utc():
    """Creator and consumer production defaults use local ``datetime.now``.

    A regression to ``partial(datetime.now, tz=UTC)`` or any UTC-bound default
    would change these identities and reintroduce Issue #4779. The recent-date
    helper is pinned separately because ``get_recent_session_log`` invokes it
    without injecting a clock.
    """
    from session_init.date_helpers import host_session_date as creator_date

    from scripts.hook_utilities.utilities import (
        host_session_date as consumer_date,
    )
    from scripts.hook_utilities.utilities import (
        recent_host_session_dates,
    )

    for helper in (creator_date, consumer_date, recent_host_session_dates):
        assert helper.__defaults__ == (datetime.now,)


def test_new_populated_session_log_uses_host_date_helper():
    """Creation path substitutes the shared helper's value, not UTC."""
    from session_init import template_helpers

    template = (
        "date: YYYY-MM-DD session NN branch [branch name] sha [SHA] "
        "goal [What this session aims to accomplish] status [clean/dirty]"
    )
    git_info = {"branch": "fix/x", "commit": "abc123", "status": "clean"}
    user_input = {"session_number": 42, "objective": "do the thing"}

    with patch.object(template_helpers, "host_session_date", return_value="2026-08-08"):
        populated = template_helpers.new_populated_session_log(
            template, git_info, user_input
        )

    assert "date: 2026-08-08" in populated
    assert "YYYY-MM-DD" not in populated


@pytest.mark.parametrize(
    ("utc_instant", "offset_hours"),
    [
        (datetime(2026, 8, 9, 6, 30, tzinfo=UTC), -7),  # host behind UTC (the bug)
        (datetime(2026, 8, 8, 16, 0, tzinfo=UTC), 14),  # host ahead of UTC (Kiritimati)
        (datetime(2026, 8, 14, 0, 0, tzinfo=UTC), 0),  # exact midnight
        (datetime(2026, 12, 31, 23, 30, tzinfo=UTC), 14),  # year rollover, host ahead
    ],
)
def test_creator_and_consumer_host_date_helpers_agree(utc_instant, offset_hours):
    """The two physical copies of ``host_session_date`` must return the same value.

    The plugin boundary forbids one shared import, so the creator-side copy in
    ``session_init.date_helpers`` and the consumer-side copy in
    ``scripts.hook_utilities.utilities`` are separate files. If they diverge, a
    creator names a file the consumer cannot find (Issue #4779). Injecting one
    clock into both pins them to identical output.
    """
    from session_init.date_helpers import host_session_date as creator_date

    from scripts.hook_utilities.utilities import host_session_date as consumer_date

    expected = _naive_local(utc_instant, offset_hours)
    assert creator_date(now=lambda: expected) == consumer_date(now=lambda: expected)
