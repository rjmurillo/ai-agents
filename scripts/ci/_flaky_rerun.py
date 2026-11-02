"""Rerun a failed leg's failed tests once, serially, and record the result.

Node ids come from the first run's pytest cache (``lastfailed``), not from
JUnit, because a JUnit ``classname`` loses the path:
``.project-toolkit.scratch.x`` cannot be turned back into
``.project-toolkit/scratch/x.py``. The xdist controller writes the cache too,
so it holds every worker's failures. Above ``max_tests`` failures the rerun
is skipped: a mass failure is a real break, and rerunning it would eat the
job's 10 minutes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from scripts.ci import _flaky_state as fs
from scripts.ci._flaky_inputs import load_lastfailed

PytestRunner = Callable[[list[str]], int]


def rerun_args(nodeids: Sequence[str], out_dir: Path) -> list[str]:
    """The pytest arguments for the one serial rerun.

    ``-n 0`` keeps xdist loaded, so a test using its ``worker_id`` fixture still
    resolves, but runs in-process. The separate cache directory means the
    rerun's own ``lastfailed`` holds exactly the tests that failed again.

    ``--`` precedes the node ids, so a node id that begins with ``-`` (a test
    file named ``-k_something.py``, say) is read as a path rather than as an
    option. The cache is a file this job wrote, but a node id is still
    repository-controlled text, and an option-shaped one could otherwise change
    what the rerun collects.
    """
    return [
        "-n",
        "0",
        "-o",
        f"cache_dir={(out_dir / fs.RERUN_CACHE_DIR).resolve()}",
        f"--junitxml={(out_dir / fs.RERUN_JUNIT_FILE).resolve()}",
        "--",
        *nodeids,
    ]


def run_rerun(lastfailed: Path, out_dir: Path, max_tests: int, runner: PytestRunner) -> int:
    """Rerun the first run's failed tests once and record what happened."""
    nodeids = load_lastfailed(lastfailed)
    state: dict[str, object] = {
        "version": fs.STATE_VERSION,
        "first_failures": nodeids,
        "max_tests": max_tests,
        "rerun_exit": None,
        "rerun_failures": [],
    }
    state_path = out_dir / fs.STATE_FILE
    if not nodeids or len(nodeids) > max_tests:
        state["status"] = fs.STATUS_NO_NODEIDS if not nodeids else fs.STATUS_OVER_CAP
        fs.write_json(state_path, state)
        reason = (
            f"{lastfailed} lists no failed test"
            if not nodeids
            else f"{len(nodeids)} failed tests exceed the cap of {max_tests}"
        )
        print(f"rerun: skipped, {reason}")
        return fs.EXIT_OK

    # Written before pytest starts, so a step timeout leaves "started" behind
    # and the report says the rerun did not finish instead of guessing.
    state["status"] = fs.STATUS_STARTED
    fs.write_json(state_path, state)
    print(f"rerun: running {len(nodeids)} failed test(s) once, serially")
    rerun_exit = runner(rerun_args(nodeids, out_dir))
    state["status"] = fs.STATUS_RAN
    state["rerun_exit"] = rerun_exit
    state["rerun_failures"] = load_lastfailed(
        out_dir / fs.RERUN_CACHE_DIR / "v" / "cache" / "lastfailed"
    )
    fs.write_json(state_path, state)
    print(f"rerun: pytest exited {rerun_exit}")
    return fs.EXIT_OK
