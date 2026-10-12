"""Validator tests for the metric artifact contract (#5639)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from scripts.metrics.metric_artifact import validate_artifact
from tests.metrics.metric_artifact_helpers import (
    NOW,
    SHA,
    flow_payload,
    nested,
    rate_payload,
    stock_payload,
    with_changes,
)


def _status(payload: Any, **kwargs: Any) -> str:
    return validate_artifact(payload, now=NOW, **kwargs).status


def _fields(payload: Any) -> set[str]:
    return {f.field for f in validate_artifact(payload, now=NOW).findings}


@pytest.mark.parametrize("build", [stock_payload, flow_payload, rate_payload])
def test_valid_artifact_passes_with_no_findings(build) -> None:
    result = validate_artifact(build(), now=NOW)

    assert result.status == "PASS"
    assert result.findings == ()
    assert result.reportable


@pytest.mark.parametrize("payload", [None, [], "text", 7])
def test_non_object_payload_is_invalid(payload) -> None:
    assert _status(payload) == "INVALID"


class TestTimestamps:
    @pytest.mark.parametrize(
        "value",
        [None, "", "yesterday", "2026-10-12T11:00:00", "2026-10-12T11:00:00+02:00", 5],
    )
    def test_unusable_retrieved_at_is_invalid(self, value) -> None:
        payload = with_changes(stock_payload(), retrieved_at=value)

        assert _status(payload) == "INVALID"
        assert "retrieved_at" in _fields(payload)

    def test_explicit_zero_offset_is_accepted(self) -> None:
        payload = with_changes(stock_payload(), retrieved_at="2026-10-12T11:00:00+00:00")

        assert _status(payload) == "PASS"

    def test_none_window_end_is_invalid(self) -> None:
        payload = nested(flow_payload(), "window", end=None)

        assert _status(payload) == "INVALID"
        assert "window.end" in _fields(payload)

    def test_flow_requires_window_start(self) -> None:
        payload = nested(flow_payload(), "window", start=None)

        assert "window.start" in _fields(payload)

    def test_stock_rejects_unparseable_window_start(self) -> None:
        payload = nested(stock_payload(), "window", start="soon")

        assert "window.start" in _fields(payload)

    def test_window_start_must_precede_end(self) -> None:
        payload = nested(flow_payload(), "window", start="2026-10-12T10:00:00Z")

        assert "window" in _fields(payload)

    def test_window_timezone_must_be_utc(self) -> None:
        payload = nested(flow_payload(), "window", timezone="America/Los_Angeles")

        assert "window.timezone" in _fields(payload)

    def test_window_ending_after_retrieval_is_invalid(self) -> None:
        payload = nested(flow_payload(), "window", end="2026-10-12T11:30:00Z")

        assert _status(payload) == "INVALID"

    def test_window_object_missing_is_invalid(self) -> None:
        payload = with_changes(stock_payload(), window=None)

        assert "window" in _fields(payload)

    def test_future_retrieval_is_invalid(self) -> None:
        payload = with_changes(stock_payload(), retrieved_at="2026-10-12T12:30:00Z")

        assert _status(payload) == "INVALID"

    def test_stale_retrieval_is_blocked(self) -> None:
        payload = with_changes(stock_payload(), retrieved_at="2026-10-10T11:00:00Z")
        payload["window"]["end"] = payload["retrieved_at"]

        assert _status(payload) == "BLOCKED"

    def test_max_age_is_configurable(self) -> None:
        payload = stock_payload()

        assert _status(payload, max_age=timedelta(minutes=30)) == "BLOCKED"

    def test_flow_ending_at_retrieval_warns_of_timing_race(self) -> None:
        payload = nested(flow_payload(), "window", end="2026-10-12T10:59:30Z")

        assert _status(payload) == "WARN"
        assert "window.end" in _fields(payload)

    def test_stock_snapshot_at_retrieval_is_not_a_race(self) -> None:
        assert _status(stock_payload()) == "PASS"


class TestPagination:
    def test_partial_pagination_is_blocked_and_names_the_page(self) -> None:
        payload = nested(
            stock_payload(),
            "pagination",
            complete=False,
            pages_fetched=300,
            failed_page=301,
            failure="HTTP 502 on page 301",
        )
        payload.update(numerator=None, status="BLOCKED", limitations=["page 301 failed"])
        payload["counts"].update(raw=0, derived=0)

        result = validate_artifact(payload, now=NOW)

        assert result.status == "BLOCKED"
        assert [f.status for f in result.findings if f.field == "pagination"] == ["BLOCKED"]

    def test_incomplete_run_that_declares_pass_with_a_number_is_not_reportable(self) -> None:
        payload = nested(
            stock_payload(), "pagination", complete=False, failed_page=301, failure="HTTP 502"
        )

        result = validate_artifact(payload, now=NOW)

        assert result.status == "BLOCKED"
        assert not result.reportable

    def test_failed_record_can_name_the_failure(self) -> None:
        payload = nested(
            stock_payload(), "pagination", complete=False, failed_record="issue#9", failure="x"
        )

        assert _status(payload) == "BLOCKED"

    def test_incomplete_run_must_name_page_or_record(self) -> None:
        payload = nested(stock_payload(), "pagination", complete=False, failure="HTTP 502")

        assert _status(payload) == "INVALID"

    def test_incomplete_run_must_say_why(self) -> None:
        payload = nested(stock_payload(), "pagination", complete=False, failed_page=2)

        assert "pagination.failure" in _fields(payload)

    @pytest.mark.parametrize("changes", [{"complete": "yes"}, {"complete": None}])
    def test_complete_must_be_boolean(self, changes) -> None:
        assert "pagination.complete" in _fields(nested(stock_payload(), "pagination", **changes))

    def test_pages_fetched_must_be_a_count(self) -> None:
        assert "pagination.pages_fetched" in _fields(
            nested(stock_payload(), "pagination", pages_fetched=-1)
        )

    def test_pagination_must_be_an_object(self) -> None:
        assert "pagination" in _fields(with_changes(stock_payload(), pagination="done"))


class TestCounts:
    def test_contradictory_counts_are_invalid(self) -> None:
        payload = nested(stock_payload(), "counts", raw=5)

        assert _status(payload) == "INVALID"
        assert "counts" in _fields(payload)

    @pytest.mark.parametrize("value", [-1, True, "3", None, 1.5])
    def test_count_values_must_be_non_negative_integers(self, value) -> None:
        assert "counts.null" in _fields(nested(stock_payload(), "counts", null=value))

    def test_missing_counts_key_is_invalid(self) -> None:
        payload = stock_payload()
        del payload["counts"]["excluded"]

        assert "counts.excluded" in _fields(payload)

    def test_empty_counts_object_is_invalid_without_raising(self) -> None:
        assert _status(with_changes(stock_payload(), counts={})) == "INVALID"

    def test_counts_must_be_an_object(self) -> None:
        assert "counts" in _fields(with_changes(stock_payload(), counts=[]))

    def test_empty_window_warns(self) -> None:
        payload = with_changes(
            flow_payload(),
            numerator=0,
            counts={"raw": 0, "derived": 0, "null": 0, "duplicates": 0, "excluded": 0},
        )

        result = validate_artifact(payload, now=NOW)

        assert result.status == "WARN"
        assert "counts.raw" in {f.field for f in result.findings}

    def test_duplicates_warn(self) -> None:
        payload = with_changes(
            stock_payload(),
            counts={"raw": 14, "derived": 12, "null": 0, "duplicates": 2, "excluded": 0},
        )

        assert _status(payload) == "WARN"
        assert "counts.duplicates" in _fields(payload)

    def test_null_records_warn(self) -> None:
        payload = with_changes(
            stock_payload(),
            counts={"raw": 13, "derived": 12, "null": 1, "duplicates": 0, "excluded": 0},
        )

        assert "counts.null" in _fields(payload)
        assert _status(payload) == "WARN"


class TestRevision:
    def test_code_dependent_metric_requires_a_revision(self) -> None:
        payload = with_changes(stock_payload(), code_dependent=True, source_revision=None)

        assert _status(payload) == "INVALID"
        assert "source_revision" in _fields(payload)

    def test_code_dependent_metric_with_revision_passes(self) -> None:
        assert (
            _status(with_changes(stock_payload(), code_dependent=True, source_revision=SHA))
            == "PASS"
        )

    def test_revision_may_be_null_when_not_code_dependent(self) -> None:
        assert _status(with_changes(stock_payload(), source_revision=None)) == "PASS"

    @pytest.mark.parametrize("value", ["main", "a" * 39, "A" * 40, 7])
    def test_revision_must_be_a_full_lowercase_sha(self, value) -> None:
        assert "source_revision" in _fields(with_changes(stock_payload(), source_revision=value))

    def test_code_dependent_must_be_boolean(self) -> None:
        assert "code_dependent" in _fields(with_changes(stock_payload(), code_dependent="no"))


class TestNumbers:
    def test_numerator_must_equal_derived_for_a_stock(self) -> None:
        assert "numerator" in _fields(with_changes(stock_payload(), numerator=13))

    def test_rate_numerator_cannot_exceed_denominator(self) -> None:
        payload = with_changes(rate_payload(), numerator=41)

        assert _status(payload) == "INVALID"
        assert "numerator" in _fields(payload)

    def test_rate_requires_a_denominator(self) -> None:
        assert "denominator" in _fields(with_changes(rate_payload(), denominator=None))

    def test_rate_denominator_must_equal_derived(self) -> None:
        assert "denominator" in _fields(with_changes(rate_payload(), denominator=39))

    def test_empty_cohort_rate_warns(self) -> None:
        payload = with_changes(
            rate_payload(),
            numerator=0,
            denominator=0,
            counts={"raw": 0, "derived": 0, "null": 0, "duplicates": 0, "excluded": 0},
        )

        assert _status(payload) == "WARN"

    def test_reconstructed_estimate_is_provisional_and_not_tied_to_counts(self) -> None:
        payload = with_changes(
            flow_payload(), kind="reconstructed_estimate", numerator=99, limitations=["estimate"]
        )

        result = validate_artifact(payload, now=NOW)

        assert result.status == "WARN"
        assert "numerator" not in {f.field for f in result.findings}

    @pytest.mark.parametrize("field", ["numerator", "denominator"])
    @pytest.mark.parametrize("value", [-1, True, "3", 1.5])
    def test_numbers_must_be_non_negative_integers_or_null(self, field, value) -> None:
        assert field in _fields(with_changes(stock_payload(), **{field: value}))

    def test_failed_status_must_not_carry_a_number(self) -> None:
        payload = with_changes(stock_payload(), status="BLOCKED", limitations=["api down"])

        assert _status(payload) == "INVALID"

    def test_reportable_status_requires_a_number(self) -> None:
        assert _status(with_changes(stock_payload(), numerator=None)) == "INVALID"


class TestDeclaration:
    def test_declared_pass_cannot_hide_a_warning(self) -> None:
        payload = nested(stock_payload(), "counts", raw=13, null=1)

        assert payload["status"] == "PASS"
        assert _status(payload) == "WARN"

    def test_declared_blocked_stays_blocked_when_checks_pass(self) -> None:
        payload = with_changes(
            stock_payload(), status="BLOCKED", numerator=None, limitations=["upstream outage"]
        )

        assert _status(payload) == "BLOCKED"

    def test_declared_warn_requires_limitations(self) -> None:
        assert "limitations" in _fields(with_changes(stock_payload(), status="WARN"))

    def test_unknown_status_is_invalid(self) -> None:
        payload = with_changes(stock_payload(), status="OK")

        assert _status(payload) == "INVALID"
        assert "status" in _fields(payload)

    @pytest.mark.parametrize("key", ["limitations", "excluded_data"])
    @pytest.mark.parametrize("value", ["none", [1], [""], None])
    def test_lists_must_hold_strings(self, key, value) -> None:
        assert key in _fields(with_changes(stock_payload(), **{key: value}))

    @pytest.mark.parametrize("query", [None, {}, {"parameters": []}, "q"])
    def test_query_parameters_are_required(self, query) -> None:
        assert "query" in _fields(with_changes(stock_payload(), query=query))


class TestEnvelope:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("schema_version", 2),
            ("metric", ""),
            ("branch", None),
            ("cohort", "  "),
            ("kind", "rate"),
            ("unit", "widgets"),
            ("repository", "rjmurillo"),
            ("repository", None),
        ],
    )
    def test_bad_identity_field_is_invalid(self, key, value) -> None:
        payload = with_changes(stock_payload(), **{key: value})

        assert _status(payload) == "INVALID"
        assert key in _fields(payload)


class TestReviewFindings:
    def test_boolean_schema_version_is_invalid(self) -> None:
        payload = with_changes(stock_payload(), schema_version=True)

        assert "schema_version" in _fields(payload)

    def test_stock_with_denominator_is_invalid(self) -> None:
        payload = with_changes(stock_payload(), denominator=99)

        assert _status(payload) == "INVALID"
        assert "denominator" in _fields(payload)

    def test_blocked_rate_with_null_numbers_is_blocked_not_invalid(self) -> None:
        payload = with_changes(
            rate_payload(),
            status="BLOCKED",
            numerator=None,
            denominator=None,
            limitations=["API outage"],
        )

        assert _status(payload) == "BLOCKED"

    def test_complete_pagination_with_recorded_failure_is_invalid(self) -> None:
        payload = nested(stock_payload(), "pagination", failed_page=301, failure="HTTP 502")

        assert _status(payload) == "INVALID"
        assert "pagination" in _fields(payload)

    @pytest.mark.parametrize(
        ("key", "value"),
        [("failed_page", 0), ("failed_record", 5), ("failure", " ")],
    )
    def test_malformed_failure_field_is_invalid(self, key, value) -> None:
        payload = nested(stock_payload(), "pagination", **{key: value})

        assert f"pagination.{key}" in _fields(payload)
