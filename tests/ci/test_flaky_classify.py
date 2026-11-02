"""Tests for scripts/ci/_flaky_classify.py: every verdict branch."""

from __future__ import annotations

import pytest

from scripts.ci import _flaky_classify as fc
from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import JunitCounts
from tests.ci.flaky_test_helpers import BROKEN, FLAKY, make_state

_FAILED_FIRST = JunitCounts(tests=10, failed=2)
_RERUN_TWO = JunitCounts(tests=2, failed=1)


def test_first_run_passed():
    outcome = fc.classify(JunitCounts(5, 0), "success", None, None)
    assert outcome.exit_code == fs.EXIT_OK
    assert outcome.rows == []


def test_failed_step_without_failed_test():
    outcome = fc.classify(JunitCounts(5, 0), "failure", None, None)
    assert outcome.exit_code == fs.EXIT_FAILED
    assert "records no failed test" in outcome.headline


def test_missing_state():
    assert fc.classify(_FAILED_FIRST, "failure", None, None).exit_code == fs.EXIT_EXTERNAL


def test_no_nodeids():
    state = make_state(status=fs.STATUS_NO_NODEIDS, first_failures=[])
    assert fc.classify(_FAILED_FIRST, "failure", state, None).exit_code == fs.EXIT_EXTERNAL


def test_over_cap_fails_and_lists_tests():
    outcome = fc.classify(_FAILED_FIRST, "failure", make_state(status=fs.STATUS_OVER_CAP), None)
    assert outcome.exit_code == fs.EXIT_FAILED
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "above the rerun cap of 25" in outcome.headline


def test_started_but_not_finished():
    outcome = fc.classify(_FAILED_FIRST, "failure", make_state(status=fs.STATUS_STARTED), None)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert {row[1] for row in outcome.rows} == {"did not finish"}


@pytest.mark.parametrize(
    ("rerun", "rerun_exit"),
    [(None, 1), (JunitCounts(0, 0), 1), (_RERUN_TWO, 4), (_RERUN_TWO, None)],
)
def test_unusable_rerun_is_inconclusive(rerun, rerun_exit):
    outcome = fc.classify(_FAILED_FIRST, "failure", make_state(rerun_exit=rerun_exit), rerun)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]


def test_nonzero_rerun_without_failures_is_inconclusive():
    outcome = fc.classify(_FAILED_FIRST, "failure", make_state(rerun_failures=[]), _RERUN_TWO)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert "recorded no failed test" in outcome.headline


def test_zero_exit_with_failure_is_inconsistent():
    state = make_state(rerun_exit=0, rerun_failures=[])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, _RERUN_TWO)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert "inconsistent" in outcome.headline


def test_flaky_and_consistent():
    outcome = fc.classify(_FAILED_FIRST, "failure", make_state(), _RERUN_TWO)
    assert outcome.exit_code == fs.EXIT_FAILED
    assert outcome.flaky == [FLAKY]
    assert outcome.consistent == [BROKEN]


def test_all_flaky_still_fails_the_leg():
    state = make_state(rerun_exit=0, rerun_failures=[])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(2, 0))
    assert outcome.exit_code == fs.EXIT_FAILED
    assert outcome.flaky == [BROKEN, FLAKY]


def test_collection_error_rerun_counts_as_consistent():
    state = make_state(rerun_exit=2, rerun_failures=[BROKEN, FLAKY])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, _RERUN_TWO)
    assert outcome.consistent == [BROKEN, FLAKY]
    assert outcome.exit_code == fs.EXIT_FAILED
