#!/usr/bin/env python3
"""Detect flaky tests in a failed CI pytest leg, without masking the failure.

A leg in `.github/workflows/pytest.yml` that fails runs this twice.

``rerun`` reads the node ids pytest recorded as failed in its cache
(``.pytest_cache/v/cache/lastfailed``) and runs only those tests once more,
serially, with a separate cache and JUnit report. The cache is the source
because a JUnit ``classname`` loses the path: ``.project-toolkit.scratch.x``
cannot be turned back into ``.project-toolkit/scratch/x.py``. The cache is
written by the xdist controller too, so it holds every worker's failures.
When more than ``--max-tests`` tests failed, the rerun is skipped, because a
mass failure is a real break and rerunning it would eat the job's 10 minutes.

``report`` classifies each first-run failure. A test that failed and then
passed is flaky. A test that failed twice is a consistent failure. It writes a
markdown table to ``GITHUB_STEP_SUMMARY``, a ``::warning`` per flaky test, and
a JSON report. It exits nonzero whenever the first run failed, flaky or not:
this is detection only, and a flake must stay visible instead of passing.

EXIT CODES (ADR-035):
  0  - ``rerun``: state written (any test outcome, or a skipped rerun).
       ``report``: the first run passed and recorded no failure.
  1  - ``report``: the first run failed (always, even when every failure was
       flaky), or the rerun was skipped above the cap.
  2  - Config: bad arguments, or a state file this script did not write.
  3  - External: a missing or malformed JUnit report or cache file, a rerun
       that did not finish, or a rerun whose result cannot be classified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.ci import run_pytest_non_tmp
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts.ci import run_pytest_non_tmp

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

STATE_VERSION = 1
STATE_FILE = "rerun-state.json"
RERUN_JUNIT_FILE = "rerun.xml"
RERUN_CACHE_DIR = "rerun-cache"
REPORT_FILE = "flaky-tests.json"
LASTFAILED_RELATIVE = Path(".pytest_cache") / "v" / "cache" / "lastfailed"
DEFAULT_MAX_TESTS = 25

STATUS_RAN = "ran"
STATUS_STARTED = "started"
STATUS_OVER_CAP = "skipped_over_cap"
STATUS_NO_NODEIDS = "skipped_no_nodeids"
_KNOWN_STATUSES = frozenset({STATUS_RAN, STATUS_STARTED, STATUS_OVER_CAP, STATUS_NO_NODEIDS})

VERDICT_FLAKY = "flaky"
VERDICT_CONSISTENT = "consistent"
VERDICT_UNCLASSIFIED = "unclassified"

# pytest exit codes: 0 all passed, 1 some failed, 2 interrupted (a collection
# error included). Anything else (3 internal, 4 usage such as an unknown node
# id, 5 nothing collected, a signal) means the rerun did not measure the tests.
_RERUN_MEASURED_EXITS = frozenset({0, 1, 2})

PytestRunner = Callable[[list[str]], int]


class InputError(Exception):
    """An input file is missing or malformed. Maps to exit 3."""


class StateError(Exception):
    """The state file is not one this script wrote. Maps to exit 2."""


@dataclass(frozen=True)
class JunitCounts:
    """Testcase totals from one JUnit report."""

    tests: int
    failed: int


@dataclass(frozen=True)
class Outcome:
    """The classification of one leg."""

    exit_code: int
    headline: str
    rows: list[tuple[str, str, str]]
    flaky: list[str]
    consistent: list[str]
    unclassified: list[str]


def load_junit_counts(path: Path) -> JunitCounts:
    """Count testcases and failed testcases (a failure or error child).

    ``defusedxml`` is not a project dependency, so a report declaring a DTD or
    an entity is rejected before the stdlib parser can expand it (CWE-611,
    CWE-776). Same fail-closed guard as ``scripts/testing/slow_test_report.py``.
    """
    if not path.is_file():
        raise InputError(f"JUnit report not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"could not read JUnit report {path}: {exc}") from exc
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise InputError(f"{path}: report declares a DTD or entity; refusing to parse it")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise InputError(f"malformed JUnit report {path}: {exc}") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise InputError(f"{path}: root element <{root.tag}> is not a JUnit report")
    tests = 0
    failed = 0
    for case in root.iter("testcase"):
        tests += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed += 1
    return JunitCounts(tests=tests, failed=failed)


def load_lastfailed(path: Path) -> list[str]:
    """Return the sorted node ids in a pytest ``lastfailed`` cache file.

    A missing file is an empty list: pytest deletes nothing, it simply does not
    write the file when no test failed.
    """
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"malformed pytest cache file {path}: {exc}") from exc
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise InputError(f"{path}: expected a JSON object keyed by node id")
    return sorted(key for key, value in data.items() if value)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rerun_args(nodeids: Sequence[str], out_dir: Path) -> list[str]:
    """The pytest arguments for the one serial rerun.

    ``-n 0`` keeps xdist loaded, so a test using its ``worker_id`` fixture still
    resolves, but runs in-process. The separate cache directory means the
    rerun's own ``lastfailed`` holds exactly the tests that failed again.
    """
    return [
        "-n",
        "0",
        "-o",
        f"cache_dir={(out_dir / RERUN_CACHE_DIR).resolve()}",
        f"--junitxml={(out_dir / RERUN_JUNIT_FILE).resolve()}",
        *nodeids,
    ]


def run_rerun(
    lastfailed: Path,
    out_dir: Path,
    max_tests: int,
    runner: PytestRunner,
) -> int:
    """Rerun the first run's failed tests once and record what happened."""
    nodeids = load_lastfailed(lastfailed)
    state: dict[str, object] = {
        "version": STATE_VERSION,
        "first_failures": nodeids,
        "max_tests": max_tests,
        "rerun_exit": None,
        "rerun_failures": [],
    }
    state_path = out_dir / STATE_FILE
    if not nodeids:
        state["status"] = STATUS_NO_NODEIDS
        _write_json(state_path, state)
        print(f"rerun: skipped, {lastfailed} lists no failed test")
        return EXIT_OK
    if len(nodeids) > max_tests:
        state["status"] = STATUS_OVER_CAP
        _write_json(state_path, state)
        print(f"rerun: skipped, {len(nodeids)} failed tests exceed the cap of {max_tests}")
        return EXIT_OK

    # Written before pytest starts, so a step timeout leaves "started" behind
    # and the report says the rerun did not finish instead of guessing.
    state["status"] = STATUS_STARTED
    _write_json(state_path, state)
    print(f"rerun: running {len(nodeids)} failed test(s) once, serially")
    rerun_exit = runner(rerun_args(nodeids, out_dir))
    state["status"] = STATUS_RAN
    state["rerun_exit"] = rerun_exit
    state["rerun_failures"] = load_lastfailed(
        out_dir / RERUN_CACHE_DIR / "v" / "cache" / "lastfailed"
    )
    _write_json(state_path, state)
    print(f"rerun: pytest exited {rerun_exit}")
    return EXIT_OK


def _string_list(state: dict[str, object], key: str) -> list[str]:
    value = state.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise StateError(f"state field {key!r} is not a list of strings")
    return value


def load_state(path: Path) -> dict[str, object] | None:
    """Read the rerun state, or None when the rerun step never wrote it."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"malformed rerun state {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        raise StateError(f"{path}: not a version {STATE_VERSION} rerun state")
    if data.get("status") not in _KNOWN_STATUSES:
        raise StateError(f"{path}: unknown status {data.get('status')!r}")
    _string_list(data, "first_failures")
    _string_list(data, "rerun_failures")
    return data


def _unclassified(exit_code: int, headline: str, nodeids: list[str], rerun: str) -> Outcome:
    rows = [(nodeid, rerun, VERDICT_UNCLASSIFIED) for nodeid in nodeids]
    return Outcome(exit_code, headline, rows, [], [], list(nodeids))


def classify(
    first: JunitCounts,
    first_outcome: str,
    state: dict[str, object] | None,
    rerun: JunitCounts | None,
) -> Outcome:
    """Decide the leg's verdict from the first run, the state, and the rerun."""
    if first.failed == 0:
        if first_outcome == "success":
            return Outcome(EXIT_OK, "The first run passed; nothing to rerun.", [], [], [], [])
        return Outcome(
            EXIT_FAILED,
            f"pytest failed ({first_outcome}) but its JUnit report records no failed "
            "test, so there is nothing to rerun. Read the Run pytest log.",
            [],
            [],
            [],
            [],
        )
    if state is None:
        return Outcome(
            EXIT_EXTERNAL,
            f"{first.failed} test(s) failed, and the rerun step wrote no state. "
            "It crashed before starting; nothing was classified.",
            [],
            [],
            [],
            [],
        )
    nodeids = _string_list(state, "first_failures")
    status = state["status"]
    if status == STATUS_NO_NODEIDS:
        return Outcome(
            EXIT_EXTERNAL,
            f"{first.failed} test(s) failed, but the pytest cache lists none, so no "
            "test could be rerun.",
            [],
            [],
            [],
            [],
        )
    if status == STATUS_OVER_CAP:
        return _unclassified(
            EXIT_FAILED,
            f"{len(nodeids)} tests failed, above the rerun cap of {state.get('max_tests')}. "
            "A failure this wide is treated as a real break, so nothing was rerun.",
            nodeids,
            "skipped",
        )
    if status == STATUS_STARTED:
        return _unclassified(
            EXIT_EXTERNAL,
            "The rerun started but did not finish (step timeout or crash).",
            nodeids,
            "did not finish",
        )
    rerun_exit = state.get("rerun_exit")
    if rerun is None or rerun.tests == 0 or rerun_exit not in _RERUN_MEASURED_EXITS:
        return _unclassified(
            EXIT_EXTERNAL,
            f"The rerun exited {rerun_exit} without a usable JUnit report, so its "
            "result cannot be classified.",
            nodeids,
            "inconclusive",
        )
    still_failing = set(_string_list(state, "rerun_failures"))
    if rerun_exit != 0 and not still_failing:
        return _unclassified(
            EXIT_EXTERNAL,
            f"The rerun exited {rerun_exit} but recorded no failed test.",
            nodeids,
            "inconclusive",
        )
    if rerun_exit == 0 and (still_failing or rerun.failed):
        return _unclassified(
            EXIT_EXTERNAL,
            "The rerun exited 0 yet recorded a failure; its result is inconsistent.",
            nodeids,
            "inconclusive",
        )
    flaky = [nodeid for nodeid in nodeids if nodeid not in still_failing]
    consistent = [nodeid for nodeid in nodeids if nodeid in still_failing]
    rows = [(nodeid, "passed", VERDICT_FLAKY) for nodeid in flaky]
    rows += [(nodeid, "failed", VERDICT_CONSISTENT) for nodeid in consistent]
    headline = (
        f"{len(nodeids)} failed test(s) rerun once: {len(flaky)} flaky "
        f"(failed, then passed), {len(consistent)} failed again. The job still fails."
    )
    return Outcome(EXIT_FAILED, headline, rows, flaky, consistent, [])


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("`", "'").replace("\n", " ")


def render_summary(partition: str, outcome: Outcome, cache_note: str) -> str:
    """The markdown block for the job step summary."""
    lines = [f"## Flaky test report ({_cell(partition)})", "", outcome.headline, ""]
    if cache_note:
        lines += [f"> [!NOTE]\n> {cache_note}", ""]
    if outcome.rows:
        lines += ["| Test | First run | Rerun | Verdict |", "| --- | --- | --- | --- |"]
        lines += [
            f"| `{_cell(nodeid)}` | failed | {rerun} | {verdict} |"
            for nodeid, rerun, verdict in outcome.rows
        ]
        lines.append("")
    if outcome.flaky:
        lines += [
            "Flaky tests failed once and passed on rerun. The leg is still red: fix",
            "the flaky test; a rerun never turns a leg green.",
            "",
        ]
    return "\n".join(lines) + "\n"


def _cache_note(first: JunitCounts, nodeids: list[str]) -> str:
    if nodeids and len(nodeids) > first.failed:
        return (
            f"The pytest cache lists {len(nodeids)} failed tests but the JUnit report "
            f"records {first.failed}; some cache entries may predate this run."
        )
    return ""


def _emit_summary(content: str) -> int:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_file:
        print(content, end="")
        return EXIT_OK
    try:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        print(f"::error::could not write the step summary {summary_file}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


def run_report(
    first_junit: Path,
    first_outcome: str,
    out_dir: Path,
    partition: str,
) -> int:
    """Classify the leg, write the summary and JSON report, return the exit code."""
    try:
        first = load_junit_counts(first_junit)
    except InputError as exc:
        print(f"::error title=Flaky test report::{exc}")
        _write_json(
            out_dir / REPORT_FILE,
            {"partition": partition, "verdict": "error", "error": str(exc)},
        )
        return EXIT_EXTERNAL
    try:
        state = load_state(out_dir / STATE_FILE)
        rerun: JunitCounts | None = None
        rerun_path = out_dir / RERUN_JUNIT_FILE
        if state is not None and state["status"] == STATUS_RAN and rerun_path.is_file():
            rerun = load_junit_counts(rerun_path)
        outcome = classify(first, first_outcome, state, rerun)
    except (InputError, StateError) as exc:
        print(f"::error title=Flaky test report::{exc}")
        _write_json(
            out_dir / REPORT_FILE,
            {"partition": partition, "verdict": "error", "error": str(exc)},
        )
        return EXIT_CONFIG if isinstance(exc, StateError) else EXIT_EXTERNAL

    nodeids = _string_list(state, "first_failures") if state is not None else []
    for nodeid in outcome.flaky:
        print(f"::warning title=Flaky test::{nodeid} failed, then passed on rerun")
    print(outcome.headline)
    _write_json(
        out_dir / REPORT_FILE,
        {
            "partition": partition,
            "first_run_outcome": first_outcome,
            "first_run_failed": first.failed,
            "first_run_tests": first.tests,
            "rerun_status": state["status"] if state is not None else None,
            "flaky": outcome.flaky,
            "consistent": outcome.consistent,
            "unclassified": outcome.unclassified,
            "exit_code": outcome.exit_code,
        },
    )
    if outcome.exit_code == EXIT_OK and not outcome.rows:
        return EXIT_OK
    summary_rc = _emit_summary(render_summary(partition, outcome, _cache_note(first, nodeids)))
    return outcome.exit_code if outcome.exit_code != EXIT_OK else summary_rc


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Build the two-subcommand parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    rerun = sub.add_parser("rerun", help="Rerun the first run's failed tests once.")
    rerun.add_argument("--out-dir", type=Path, required=True)
    rerun.add_argument("--lastfailed", type=Path, default=_PROJECT_ROOT / LASTFAILED_RELATIVE)
    rerun.add_argument("--max-tests", type=_positive_int, default=DEFAULT_MAX_TESTS)

    report = sub.add_parser("report", help="Classify flaky tests and write the summary.")
    report.add_argument("--first-junit", type=Path, required=True)
    report.add_argument(
        "--first-outcome",
        choices=["success", "failure", "cancelled", "skipped"],
        required=True,
    )
    report.add_argument("--out-dir", type=Path, required=True)
    report.add_argument("--partition", required=True)
    return parser


def main(argv: Sequence[str] | None = None, runner: PytestRunner | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_CONFIG
    try:
        if args.command == "rerun":
            return run_rerun(
                args.lastfailed,
                args.out_dir,
                args.max_tests,
                runner if runner is not None else run_pytest_non_tmp.main,
            )
        return run_report(args.first_junit, args.first_outcome, args.out_dir, args.partition)
    except InputError as exc:
        print(f"::error title=Flaky test report::{exc}")
        return EXIT_EXTERNAL
    except OSError as exc:
        print(f"::error title=Flaky test report::{exc}")
        return EXIT_EXTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
