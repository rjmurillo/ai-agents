"""Report gate tests for the metric artifact contract (#5639)."""

from __future__ import annotations

from scripts.metrics.metric_artifact import validate_artifact
from scripts.metrics.metric_artifact_report import check_combinable, report_line
from tests.metrics.metric_artifact_helpers import (
    NOW,
    flow_payload,
    nested,
    stock_payload,
    with_changes,
)


def _line(payload) -> str:
    return report_line(payload, validate_artifact(payload, now=NOW))


def test_blocked_report_names_the_producer_limitation() -> None:
    payload = with_changes(
        stock_payload(), status="BLOCKED", numerator=None, limitations=["API outage"]
    )

    line = _line(payload)

    assert line.startswith("[BLOCKED] open_issues: withheld (")
    assert "API outage" in line
    assert "12" not in line


def test_untrusted_text_is_escaped_and_single_line() -> None:
    payload = with_changes(
        stock_payload(),
        metric="<b>x</b>\n# head",
        status="BLOCKED",
        numerator=None,
        limitations=["<script>"],
    )

    line = _line(payload)

    assert "\n" not in line
    assert "<b>" not in line
    assert "<script>" not in line
    assert "&lt;script&gt;" in line


def test_non_list_limitations_do_not_raise() -> None:
    payload = with_changes(stock_payload(), limitations="oops")

    assert _line(payload).startswith("[INVALID]")


def test_z_and_zero_offset_windows_are_combinable() -> None:
    other = nested(flow_payload(), "window", end="2026-10-12T10:00:00+00:00")

    assert check_combinable([flow_payload(), other]) == []


def test_different_windows_are_not_combinable() -> None:
    other = nested(flow_payload(), "window", end="2026-10-12T09:00:00Z")

    assert [f.field for f in check_combinable([flow_payload(), other])] == ["window"]


def test_different_branch_and_cohort_are_not_combinable() -> None:
    other = with_changes(flow_payload(), branch="dev", cohort="other cohort")

    fields = {f.field for f in check_combinable([flow_payload(), other])}

    assert fields == {"branch", "cohort"}


def test_declared_scope_allows_mixed_artifacts() -> None:
    other = with_changes(flow_payload(), branch="dev")

    assert check_combinable([flow_payload(), other], declared_scope="release vs dev") == []
