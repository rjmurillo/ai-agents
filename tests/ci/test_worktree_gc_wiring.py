"""Structural tests for worktree GC automation wiring (issue #4193)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"


def _iter_jobs(node: Any):
    if isinstance(node, dict):
        if "name" in node and "run" in node:
            yield node
        for value in node.values():
            yield from _iter_jobs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_jobs(item)


def _lefthook_job(name: str) -> dict[str, Any]:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    matches = [job for job in _iter_jobs(data) if job.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_worktree_gc_report_runs_in_pre_push_without_apply() -> None:
    job = _lefthook_job("worktree-gc-report")
    assert job["run"].startswith("uv run --frozen python scripts/maintenance/gc_worktrees.py")
    assert "--apply" not in job["run"]


def test_the_advisory_guard_carries_no_yaml_comment_character() -> None:
    """A ``#`` in a plain YAML scalar truncates the command at that point.

    The guard message is the only free prose in this job's ``run`` string, so
    it is the only place a stray ``#`` could silently cut the shell command in
    half. Measured: ``yaml.safe_load`` on ``run: cmd || echo "see issue #42"``
    yields ``cmd || echo "see issue``, an unterminated quote that makes the
    shell exit non-zero, which is precisely the failure the guard exists to
    prevent. Quoting the whole scalar would also work; asserting the absence
    is cheaper and does not constrain how the value is written.
    """
    assert "#" not in _lefthook_job("worktree-gc-report")["run"]


def test_worktree_gc_report_is_in_pre_push_group() -> None:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    pre_push = data["pre-push"]["jobs"]
    group_jobs = [job for group in pre_push if "group" in group for job in group["group"]["jobs"]]
    assert any(job.get("name") == "worktree-gc-report" for job in group_jobs)


def _duration_seconds(value: str) -> float:
    """Convert a lefthook duration such as '5m' or '90s' to seconds."""
    units = {"h": 3600.0, "m": 60.0, "s": 1.0}
    if value[-1] in units:
        return float(value[:-1]) * units[value[-1]]
    return float(value)


def test_the_worst_case_report_fits_inside_its_lefthook_timeout() -> None:
    """The budget and the job cap must not drift into a push-rejecting pair.

    The report mutates nothing, and the job's ``|| echo`` guard absorbs every
    non-zero exit, so the one remaining way this job can reject a push is by
    being killed at the lefthook cap. That kill happens to the job's shell, so
    the guard cannot absorb it (measured: a job with ``sleep 10 || true`` under
    ``timeout: 2s`` still exits lefthook non-zero). Issue 4257 rules out buying
    room by raising the cap, so the constants below must fit under it instead.

    Worst case is the two setup git calls made before the deadline is even
    established, plus the budget itself, plus one final inspection that started
    just under the deadline and makes up to three git calls.
    """
    from scripts.maintenance.gc_worktrees import (
        _DEFAULT_TIME_BUDGET_SECONDS,
        _GIT_TIMEOUT_SECONDS,
    )

    setup_git_calls = 2
    git_calls_per_inspection = 3
    worst_case = (
        setup_git_calls * _GIT_TIMEOUT_SECONDS
        + _DEFAULT_TIME_BUDGET_SECONDS
        + git_calls_per_inspection * _GIT_TIMEOUT_SECONDS
    )
    cap = _duration_seconds(str(_lefthook_job("worktree-gc-report")["timeout"]))
    assert worst_case < cap, f"worst case {worst_case}s does not fit inside the {cap}s job timeout"


def test_the_job_cap_was_not_raised_to_buy_headroom() -> None:
    """Issue 4257 acceptance criterion 5: the cap is not the fix.

    Pinned as a ceiling rather than an equality so a future reduction stays
    legal while the specific regression this PR was reviewed for cannot recur.
    """
    cap = _duration_seconds(str(_lefthook_job("worktree-gc-report")["timeout"]))
    assert cap <= 120.0, f"job cap {cap}s exceeds the 2m ceiling issue 4257 fixed in place"


def _guarded_command(stub: str) -> str:
    """Return the real lefthook ``run`` string with the script call replaced.

    Substituting only the invocation keeps the guard exactly as shipped, so the
    test exercises the operator that has to do the work rather than a
    hand-written copy of it that could drift from the config.
    """
    run = _lefthook_job("worktree-gc-report")["run"]
    invocation = "uv run --frozen python scripts/maintenance/gc_worktrees.py"
    assert invocation in run, f"job no longer invokes the reporter directly: {run!r}"
    return run.replace(invocation, stub)


def test_a_failing_report_does_not_fail_the_push() -> None:
    """Issue 4257 acceptance criterion 1, exercised rather than asserted.

    Runs the shipped ``run`` string with the reporter swapped for a stub that
    exits non-zero, and requires the shell to still exit 0. A substring check
    against lefthook.yml would prove the guard is spelled correctly, not that
    it absorbs the failure.
    """
    completed = subprocess.run(
        _guarded_command("sh -c 'exit 2'"),
        shell=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr


def test_a_failing_report_says_so_instead_of_failing_silently() -> None:
    """Swallowing without disclosing would hide a broken reporter forever."""
    completed = subprocess.run(
        _guarded_command("sh -c 'exit 2'"),
        shell=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert "worktree-gc-report" in completed.stdout
    assert "4257" in completed.stdout


def test_without_the_guard_the_same_failure_does_fail_the_push() -> None:
    """Issue 4257 acceptance criterion 3: the isolating negative control.

    Strips the ``|| ...`` guard from the shipped string and reruns the same
    stub. This must fail, otherwise the two tests above would pass whether or
    not the guard exists and would prove nothing about it.
    """
    unguarded = _guarded_command("sh -c 'exit 2'").split("||")[0].strip()
    completed = subprocess.run(
        unguarded,
        shell=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert completed.returncode != 0, "the guard is not load-bearing; the tests above are vacuous"


def test_a_slow_report_is_still_absorbed_when_it_exits_non_zero() -> None:
    """The slow case reaches the guard whenever the script yields the exit.

    A lefthook kill at the cap is the one path the guard cannot absorb, which
    is why ``test_the_worst_case_report_fits_inside_its_lefthook_timeout``
    keeps the worst case under it. Everything short of that kill, including a
    run that overruns its own internal budget and then errors, arrives here as
    an ordinary non-zero exit and must not reject the push.
    """
    completed = subprocess.run(
        _guarded_command("sh -c 'sleep 1; exit 3'"),
        shell=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
