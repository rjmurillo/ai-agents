"""Shared payload builders for the metric artifact tests (#5639)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def stock_payload() -> dict[str, Any]:
    """A valid PASS stock snapshot of 12 open issues."""
    return {
        "schema_version": 1,
        "metric": "open_issues",
        "kind": "stock_snapshot",
        "unit": "issues",
        "repository": "rjmurillo/ai-agents",
        "branch": "main",
        "source_revision": SHA,
        "code_dependent": False,
        "retrieved_at": "2026-10-12T11:00:00Z",
        "query": {"parameters": {"state": "open"}},
        "pagination": {
            "complete": True,
            "pages_fetched": 1,
            "failed_page": None,
            "failed_record": None,
            "failure": None,
        },
        "window": {"start": None, "end": "2026-10-12T11:00:00Z", "timezone": "UTC"},
        "cohort": "open issues at retrieval",
        "numerator": 12,
        "denominator": None,
        "counts": {"raw": 12, "derived": 12, "null": 0, "duplicates": 0, "excluded": 0},
        "status": "PASS",
        "limitations": [],
        "excluded_data": [],
    }


def flow_payload() -> dict[str, Any]:
    """A valid PASS 30-day issue creation flow of 30 records."""
    payload = stock_payload()
    payload.update(
        metric="issues_created_30d",
        kind="event_flow",
        window={
            "start": "2026-09-12T10:00:00Z",
            "end": "2026-10-12T10:00:00Z",
            "timezone": "UTC",
        },
        cohort="issues created in window",
        numerator=30,
        counts={"raw": 30, "derived": 30, "null": 0, "duplicates": 0, "excluded": 0},
    )
    return payload


def rate_payload() -> dict[str, Any]:
    """A valid PASS same-cohort rate of 8 closed out of 40 created."""
    payload = flow_payload()
    payload.update(
        metric="close_rate_30d",
        kind="same_cohort_rate",
        cohort="issues created in window, closed by retrieval",
        numerator=8,
        denominator=40,
        counts={"raw": 40, "derived": 40, "null": 0, "duplicates": 0, "excluded": 0},
    )
    return payload


def with_changes(payload: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Deep copy ``payload`` and replace the top-level keys in ``changes``."""
    updated = copy.deepcopy(payload)
    updated.update(changes)
    return updated


def nested(payload: dict[str, Any], key: str, **changes: Any) -> dict[str, Any]:
    """Deep copy ``payload`` and replace keys inside the ``key`` object."""
    updated = copy.deepcopy(payload)
    updated[key].update(changes)
    return updated
