"""Classify a failed leg's tests as flaky, consistent, or unclassified.

A test is flaky only when the rerun proves it ran and passed. A test that
failed twice is a consistent failure. Every other path (no rerun, a skipped or
unfinished rerun, an unusable rerun result) leaves the tests unclassified.
Whatever the verdict, a failed first run never yields exit 0: this is
detection only, and a flake must stay visible instead of passing.

Absence from the rerun's failure list is not proof that a test passed. On a
collection error or an interrupt, pytest records the failure against the module
that failed to import rather than against its test functions, so a naive
"not in ``rerun_failures``" rule would label every first-run failure, including
tests that never ran, as flaky. Each check below closes one route to that
mistake, and an unprovable case is reported as inconclusive instead of flaky.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import JunitCounts

VERDICT_FLAKY = "flaky"
VERDICT_CONSISTENT = "consistent"
VERDICT_UNCLASSIFIED = "unclassified"

# pytest exit codes: 0 all passed, 1 some failed. Exit 2 covers an interrupt
# and a collection error; on those pytest reports the failure against the
# module, not the test, so the rerun cannot say which tests ran. Anything
# else (3 internal, 4 usage such as an unknown node id, 5 nothing collected,
# a signal) means the rerun did not measure the tests either.
_RERUN_MEASURED_EXITS = frozenset({0, 1})
_RERUN_COLLECTION_EXIT = 2


@dataclass(frozen=True)
class Outcome:
    """The classification of one leg."""

    exit_code: int
    headline: str
    rows: list[tuple[str, str, str]] = field(default_factory=list)
    flaky: list[str] = field(default_factory=list)
    consistent: list[str] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)


def _unclassified(exit_code: int, headline: str, nodeids: list[str], rerun: str) -> Outcome:
    rows = [(nodeid, rerun, VERDICT_UNCLASSIFIED) for nodeid in nodeids]
    return Outcome(exit_code, headline, rows=rows, unclassified=list(nodeids))


def _without_rerun(first: JunitCounts, first_outcome: str) -> Outcome:
    """The verdict when the rerun step has nothing to report."""
    if first.failed == 0:
        if first_outcome == "success":
            return Outcome(fs.EXIT_OK, "The first run passed; nothing to rerun.")
        return Outcome(
            fs.EXIT_FAILED,
            f"pytest failed ({first_outcome}) but its JUnit report records no failed "
            "test, so there is nothing to rerun. Read the Run pytest log.",
        )
    return Outcome(
        fs.EXIT_EXTERNAL,
        f"{first.failed} test(s) failed, and the rerun step wrote no state. "
        "It crashed before starting; nothing was classified.",
    )


def _before_rerun(first: JunitCounts, state: dict[str, object]) -> Outcome | None:
    """The verdict when the rerun did not run to the end, or None to keep going."""
    nodeids = fs.string_list(state, "first_failures")
    status = state["status"]
    if status == fs.STATUS_NO_NODEIDS:
        return Outcome(
            fs.EXIT_EXTERNAL,
            f"{first.failed} test(s) failed, but the pytest cache lists none, so no "
            "test could be rerun.",
        )
    if status == fs.STATUS_OVER_CAP:
        return _unclassified(
            fs.EXIT_FAILED,
            f"{len(nodeids)} tests failed, above the rerun cap of {state.get('max_tests')}. "
            "A failure this wide is treated as a real break, so nothing was rerun.",
            nodeids,
            "skipped",
        )
    if status == fs.STATUS_STARTED:
        return _unclassified(
            fs.EXIT_EXTERNAL,
            "The rerun started but did not finish (step timeout or crash).",
            nodeids,
            "did not finish",
        )
    return None


def _rerun_problem(state: dict[str, object], rerun: JunitCounts | None, nodeids: list[str]) -> str:
    """Why the rerun result cannot be classified, or an empty string when it can.

    A flaky verdict needs the rerun to have executed every first-run failure and
    to have reported its failures as test node ids. Each branch below rejects a
    rerun that cannot support that claim, so the tests are reported as
    inconclusive rather than being called flaky by default.
    """
    rerun_exit = state.get("rerun_exit")
    if rerun is None or rerun.tests == 0 or rerun_exit not in _RERUN_MEASURED_EXITS:
        if rerun_exit == _RERUN_COLLECTION_EXIT:
            return (
                "The rerun exited 2 (a collection error or an interrupt). pytest records "
                "that failure against the module, not the test, so the rerun cannot say "
                "which tests ran. Its result cannot be classified."
            )
        return f"The rerun exited {rerun_exit} and ran no test, so its result cannot be classified."
    still_failing = fs.string_list(state, "rerun_failures")
    if rerun_exit != 0 and not still_failing:
        return f"The rerun exited {rerun_exit} but recorded no failed test."
    if rerun_exit == 0 and (still_failing or rerun.failed):
        return "The rerun exited 0 yet recorded a failure; its result is inconsistent."
    unexpected = sorted(set(still_failing) - set(nodeids))
    if unexpected:
        listed = ", ".join(unexpected[:3])
        return (
            f"The rerun reported failure(s) for {listed}, which did not fail on the "
            "first run. A module-level or collection failure reads this way, so the "
            "result cannot be classified."
        )
    # Positive proof: every first-run failure must appear either as a cache entry
    # (it failed again) or as a named JUnit case with no outcome child (it ran and
    # passed). Counting testcases instead would treat a skip, an aborted session,
    # or a failure the cache lost as a pass, which is the defect this guard
    # exists to prevent. Duplicate JUnit cases for one node id are normal, so the
    # cache count is compared against node ids, never against element counts.
    if rerun.passed + len(still_failing) != len(nodeids):
        return (
            f"The rerun recorded {rerun.passed} passed, {len(still_failing)} failed, and "
            f"{rerun.skipped} skipped test(s), which does not account for the "
            f"{len(nodeids)} that failed first. A test that was skipped, aborted, or "
            "never rerun cannot prove it passed, so its result cannot be classified."
        )
    return ""


def classify(
    first: JunitCounts,
    first_outcome: str,
    state: dict[str, object] | None,
    rerun: JunitCounts | None,
) -> Outcome:
    """Decide the leg's verdict from the first run, the state, and the rerun."""
    if first.failed == 0 or state is None:
        return _without_rerun(first, first_outcome)
    early = _before_rerun(first, state)
    if early is not None:
        return early
    nodeids = fs.string_list(state, "first_failures")
    problem = _rerun_problem(state, rerun, nodeids)
    if problem:
        return _unclassified(fs.EXIT_EXTERNAL, problem, nodeids, "inconclusive")
    still_failing = set(fs.string_list(state, "rerun_failures"))
    flaky = [nodeid for nodeid in nodeids if nodeid not in still_failing]
    consistent = [nodeid for nodeid in nodeids if nodeid in still_failing]
    rows = [(nodeid, "passed", VERDICT_FLAKY) for nodeid in flaky]
    rows += [(nodeid, "failed", VERDICT_CONSISTENT) for nodeid in consistent]
    headline = (
        f"{len(nodeids)} failed test(s) rerun once: {len(flaky)} flaky "
        f"(failed, then passed), {len(consistent)} failed again. The job still fails."
    )
    return Outcome(fs.EXIT_FAILED, headline, rows=rows, flaky=flaky, consistent=consistent)
