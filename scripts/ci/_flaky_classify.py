"""Classify a failed leg's tests as flaky, consistent, or unclassified.

A test that failed and then passed on the rerun is flaky. A test that failed
twice is a consistent failure. Every other path (no rerun, a skipped or
unfinished rerun, an unusable rerun result) leaves the tests unclassified.
Whatever the verdict, a failed first run never yields exit 0: this is
detection only, and a flake must stay visible instead of passing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import JunitCounts

VERDICT_FLAKY = "flaky"
VERDICT_CONSISTENT = "consistent"
VERDICT_UNCLASSIFIED = "unclassified"

# pytest exit codes: 0 all passed, 1 some failed, 2 interrupted (a collection
# error included). Anything else (3 internal, 4 usage such as an unknown node
# id, 5 nothing collected, a signal) means the rerun did not measure the tests.
_RERUN_MEASURED_EXITS = frozenset({0, 1, 2})


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


def _rerun_problem(state: dict[str, object], rerun: JunitCounts | None) -> str:
    """Why the rerun result cannot be classified, or an empty string when it can."""
    rerun_exit = state.get("rerun_exit")
    if rerun is None or rerun.tests == 0 or rerun_exit not in _RERUN_MEASURED_EXITS:
        return (
            f"The rerun exited {rerun_exit} without a usable JUnit report, so its "
            "result cannot be classified."
        )
    still_failing = fs.string_list(state, "rerun_failures")
    if rerun_exit != 0 and not still_failing:
        return f"The rerun exited {rerun_exit} but recorded no failed test."
    if rerun_exit == 0 and (still_failing or rerun.failed):
        return "The rerun exited 0 yet recorded a failure; its result is inconsistent."
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
    problem = _rerun_problem(state, rerun)
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
