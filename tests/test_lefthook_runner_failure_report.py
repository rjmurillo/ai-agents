"""A failed hook names its stage, the failing job, and a rerun command (issue #6734, item 5).

`lefthook.yml` once set `output: false`, so a failed hook printed the job's own
output and `exit status 1`, with no stage and no rerun command. It now sets
`output: [failure]`, and `lefthook_runner.py` closes a failed `run <hook>` with a
block naming both. Each test pins one part of that block.

Coverage:

- positive: stage, job, file path, and a rerun command reach the user.
- edge: unnamed groups, a reason Lefthook gives for a job that never started, no
  reported job, many failed jobs, and a pre-push hook whose rerun must replay its
  stdin ref lines.
- security: job names and ref lines are shell-quoted in the rerun command.

`test_lefthook_runner_main_report.py` covers `main`, `test_lefthook_report_contracts.py`
covers credentials and config guards, and `test_lefthook_runner_real_binary.py` runs
a real Lefthook binary.
"""

from __future__ import annotations

import importlib
import shlex
import sys
from pathlib import Path

import pytest

from scripts.validation import lefthook_runner as runner
from tests.support.lefthook_binary import resolve_lefthook

# The runner imports its sibling by bare name; patch the module object it holds.
report_module = importlib.import_module(runner.run_hook_with_report.__module__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")
_LEFTHOOK = resolve_lefthook()
FIGHT = "\U0001f94a"
COMMAND = ["uv", "run", "--frozen", "lefthook"]


def _lefthook_failure(job: str, finding: str) -> str:
    return (
        f"{finding}\n\nexit status 1\n{FIGHT} group (6) (10.23 seconds)\n"
        f"  {FIGHT} {job} (0.03 seconds)\n"
    )


def test_split_output_removes_job_lines_and_ignores_unnamed_groups() -> None:
    text = _lefthook_failure("python-format", "scripts/a.py:4:1 bad")

    shown, jobs = report_module.split_output(text)

    assert jobs == ["python-format"]
    assert FIGHT not in shown
    assert "scripts/a.py:4:1 bad" in shown


def test_split_output_keeps_ordinary_lines_unchanged() -> None:
    text = "a\n\n  indented line\nno newline at end"

    assert report_module.split_output(text) == (text, [])


def test_split_output_strips_color_codes_and_lists_each_job_once() -> None:
    text = (
        f"\x1b[31m{FIGHT} lint (1.5 seconds)\x1b[0m\n"
        f"{FIGHT} lint (1 second)\n{FIGHT} types (2 seconds)\n"
    )

    assert report_module.split_output(text)[1] == ["lint", "types"]


def test_split_output_keeps_the_reason_lefthook_gives_for_a_job_that_never_ran() -> None:
    text = f"{FIGHT} range-check: exit status 128 (0.01 seconds)\n"

    assert report_module.split_output(text) == (text, ["range-check"])


def test_report_names_stage_job_and_runnable_rerun() -> None:
    report = report_module.failure_report(COMMAND, ["run", "pre-commit"], 1, ["python-format"], [])

    assert "pre-commit FAILED (exit 1)" in report
    assert "job: python-format" in report
    assert "rerun: uv run --frozen lefthook run pre-commit --job python-format\n" in report


def test_report_quotes_job_names_and_keeps_hook_arguments() -> None:
    report = report_module.failure_report(
        COMMAND, ["run", "commit-msg", ".git/COMMIT_EDITMSG"], 1, ["my job"], []
    )

    assert "--job 'my job' .git/COMMIT_EDITMSG" in report


def test_report_replays_pre_push_stdin_so_the_rerun_is_not_a_silent_pass() -> None:
    ref = "refs/heads/x abc refs/heads/x 000"

    report = report_module.failure_report(
        COMMAND, ["run", "pre-push", "origin", "url"], 1, ["a"], [ref]
    )

    assert f"printf '%s\\n' {shlex.quote(ref)} | uv run" in report
    assert "run pre-push --job a origin url" in report


def test_report_quotes_shell_metacharacters_in_job_names_and_ref_lines() -> None:
    ref = "refs/heads/$(touch pwned) `id`; x"

    report = report_module.failure_report(
        COMMAND, ["run", "pre-push", "origin", "u"], 1, ["a; touch pwned"], [ref]
    )

    assert f"printf '%s\\n' {shlex.quote(ref)} |" in report
    assert "--job 'a; touch pwned'" in report


def test_report_replays_every_ref_of_a_large_push() -> None:
    refs = [f"r{n}" for n in range(25)]

    report = report_module.failure_report(
        COMMAND, ["run", "pre-push", "origin", "u"], 1, ["a"], refs
    )

    assert report.count("r24") == 2  # the job rerun and the hook rerun
    assert " r0 r1 r2 " in report


def test_report_without_a_reported_job_still_gives_a_rerun() -> None:
    report = report_module.failure_report(COMMAND, ["run", "pre-commit"], 3, [], [])

    assert "pre-commit FAILED (exit 3)" in report
    assert "job: not reported by Lefthook" in report
    assert "rerun hook: uv run --frozen lefthook run pre-commit\n" in report


def test_report_ends_with_a_rerun_of_the_whole_hook() -> None:
    report = report_module.failure_report(COMMAND, ["run", "pre-commit"], 1, ["a", "b"], [])

    assert report.splitlines()[-1] == "  rerun hook: uv run --frozen lefthook run pre-commit"


def test_report_lists_every_failed_job() -> None:
    jobs = [f"job{n}" for n in range(8)]

    report = report_module.failure_report(COMMAND, ["run", "pre-commit"], 1, jobs, [])

    assert report.count("  job: ") == 8
    for job in jobs:
        assert f"run pre-commit --job {job}\n" in report


def test_report_text_has_no_dashes() -> None:
    report = report_module.failure_report(COMMAND, ["run", "pre-push", "o", "u"], 1, ["a"], ["r"])

    assert chr(0x2013) not in report
    assert chr(0x2014) not in report
