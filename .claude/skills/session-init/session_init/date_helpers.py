"""Date helpers for session log generation.

Session logs are named by the contributor's current session date. The host
clock is the authority for that date, not UTC. Near midnight UTC the two
diverge, so a UTC date can name a log one day ahead of the active session
(Issue #4779).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

_ISO_DATE = "%Y-%m-%d"


def host_session_date(now: Callable[[], datetime] = datetime.now) -> str:
    """Return the host local date as ``YYYY-MM-DD``.

    Uses the host's local timezone so filenames and populated dates match
    the contributor's active session, not UTC. ``now`` is injectable for
    deterministic tests; it must return a naive local datetime, matching
    :func:`datetime.datetime.now` with no timezone argument.
    """
    return now().strftime(_ISO_DATE)
