"""Shared fixtures for the backlog_provenance tests (issue #5702)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
START = NOW - timedelta(days=7)
ENDPOINT = "repos/o/r/issues?state=all&since=x&per_page=100"


def record(number, minutes_ago=60.0, title="A feature", login="owner", labels=(), pr=False):
    created = NOW - timedelta(minutes=minutes_ago)
    data = {
        "number": number,
        "title": title,
        "user": {"login": login},
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": [{"name": name} for name in labels],
    }
    if pr:
        data["pull_request"] = {"url": "x"}
    return data
