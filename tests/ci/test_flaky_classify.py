"""Tests for scripts/ci/_flaky_classify.py: every verdict branch."""

from __future__ import annotations

import pytest

from scripts.ci import _flaky_classify as fc
from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import JunitCounts
from tests.ci.flaky_test_helpers import BROKEN, FLAKY, MODULE, make_state

_FAILED_FIRST = JunitCounts(tests=10, failed=2)
# BROKEN failed again and FLAKY ran and passed.
_RERUN_TWO = JunitCounts(tests=2, failed=1, passed=1)
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
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(2, 0, passed=2))
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
    assert "does not account for the 2" in outcome.headline


def test_failure_lost_by_the_cache_is_inconclusive():
    """A failing testcase the cache does not list means a failure was lost.

    The proof must account for both node ids: one failed again (BROKEN) and the
    other produced no passing testcase, so the rerun cannot say it passed.
    """
    state = make_state(rerun_failures=[BROKEN])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(2, 1))
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "does not account for the 2" in outcome.headline


def test_duplicate_junit_cases_for_one_node_id_are_tolerated():
    """A call failure plus a teardown error writes two cases for one test.

    pytest emits one testcase per report, so a test that fails in the call phase
    and again in a fixture finalizer produces two failing cases against one
    cache entry. Element counts therefore cannot be compared with node ids; the
    leg must still classify instead of going inconclusive.
    """
    state = make_state(rerun_failures=[BROKEN])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(3, 2, passed=1))
    assert outcome.exit_code == fs.EXIT_FAILED
    assert outcome.flaky == [FLAKY]
    assert outcome.consistent == [BROKEN]


def test_aborted_session_case_is_not_a_pass():
    """An aborted session writes a nameless case that proves nothing.

    ``pytest.exit`` mid-run still writes a testcase element, so counting
    elements would read the aborted test as having passed.
    """
    state = make_state(rerun_failures=[BROKEN])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(2, 1, passed=0))
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]


def test_skipped_on_rerun_is_inconclusive():
    """A skip proves nothing about passing.

    An xfail run as a skip, or a test that skipped on the rerun, is absent from
    lastfailed and is not a failure, so it would otherwise read as "failed, then
    passed". A skip did not run, so the rerun cannot prove it passed. BROKEN
    failed again and FLAKY skipped, which is the only signal that separates this
    from a genuine flake.
    """
    state = make_state(rerun_failures=[BROKEN])
    rerun = JunitCounts(tests=2, failed=1, skipped=1)
    outcome = fc.classify(_FAILED_FIRST, "failure", state, rerun)
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
    assert "1 skipped" in outcome.headline


def test_all_skipped_rerun_is_inconclusive():
    """Every first-run failure skipped, so nothing was proven."""
    state = make_state(rerun_failures=[])
    outcome = fc.classify(_FAILED_FIRST, "failure", state, JunitCounts(2, 0, skipped=2))
    assert outcome.exit_code == fs.EXIT_EXTERNAL
    assert outcome.unclassified == [BROKEN, FLAKY]
