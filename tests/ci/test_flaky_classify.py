"""Tests for scripts/ci/_flaky_classify.py: every verdict branch."""

from __future__ import annotations

import pytest

from scripts.ci import _flaky_classify as fc
from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import JunitCounts
from tests.ci.flaky_test_helpers import BROKEN, FLAKY, MODULE, make_state

_FAILED_FIRST = JunitCounts(tests=10, failed=2)
_RERUN_TWO = JunitCounts(tests=2, failed=1)
# A rerun that measured one failure but executed only one of the two tests.
_RERUN_SHORT = JunitCounts(tests=1, failed=1)


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


def test_collection_error_rerun_is_inconclusive():
    """A collection error makes pytest blame the module, not the test.

    On exit 2 pytest records the failure against the module node id, so the
    rerun proves nothing about the individual tests. They must not be called
    flaky just because their node ids are absent from the rerun's cache.
    """
    state = make_state(rerun_exit=2, rerun_failures=[MODULE])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, _RERUN_TWO)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "collection error" in outcome.headline


def test_rerun_failure_outside_first_failures_is_inconclusive():
    """A module-level failure entry is not one of the tests that failed."""
    state = make_state(rerun_exit=1, rerun_failures=[MODULE])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, _RERUN_TWO)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert MODULE in outcome.headline


def test_short_rerun_is_inconclusive():
    """Fewer tests ran than failed, so the missing ones were never measured."""
    outcome = fc.classify(_FAILED_FIRST, "failure", make_state(), _RERUN_SHORT)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "never rerun" in outcome.headline


def test_exit_one_failure_count_mismatch_is_inconclusive():
    """The JUnit failure count and the cache node id count must agree."""
    state = make_state(rerun_failures=[BROKEN])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(2, 2))
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "disagree" in outcome.headline
