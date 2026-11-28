"""Shared fixtures for count-ratchet tests."""

from __future__ import annotations

import shlex
from pathlib import Path

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from tests.ci.workflow_yaml import load_jobs

_REPO_ROOT = Path(__file__).resolve().parents[2]


def write_baseline_file(
    tmp_path: Path,
    filename: str,
    value: str,
    *,
    trailing_newline: bool = False,
) -> Path:
    path = tmp_path / filename
    text = f"{value}\n" if trailing_newline else value
    path.write_text(text, encoding="utf-8")
    return path


def make_baseline_writer(
    filename: str,
    *,
    trailing_newline: bool = False,
):
    def _write_baseline(tmp_path: Path, value: str) -> Path:
        return write_baseline_file(
            tmp_path,
            filename,
            value,
            trailing_newline=trailing_newline,
        )

    return _write_baseline


_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
RATCHET_WORKFLOWS = ("pytest.yml", "pr-validation.yml")
# The only step-level condition CI is allowed on a ratchet: ruff_ratchet.py runs
# on the primary matrix leg of the pytest job, which the required rollup covers.
ALLOWED_STEP_IF = {"scripts/ci/ruff_ratchet.py": "matrix.primary"}


def workflow_jobs(workflow: str) -> dict[str, dict]:
    return load_jobs(_WORKFLOWS / workflow)


def continues_on_error(node: dict) -> bool:
    """True when a job or step sets ``continue-on-error`` to anything but ``false``.

    An expression string counts: it can evaluate to true, and then a failure
    no longer fails the required context.
    """
    return node.get("continue-on-error") not in (None, False)


_RUN_AFTER_FAILURE = ("always()", "!cancelled()")
_PYTHON_LAUNCHERS = (
    "python",
    "python3",
    "uv run python",
    "uv run python3",
    "uv run --frozen python",
    "uv run --frozen python3",
    "uv run --frozen --extra dev python3",
)


def runs_python_command(step: dict, command: str) -> bool:
    """Recognize the direct Python invocations used by these CI jobs.

    This is a wiring assertion, not a general shell parser. A new command
    form requires review of its execution semantics before it qualifies.
    """
    lines = [line.split() for line in str(step.get("run", "")).splitlines()]
    prefixes = [launcher.split() + command.split() for launcher in _PYTHON_LAUNCHERS]
    return any(line[: len(prefix)] == prefix for line in lines for prefix in prefixes)


_STALENESS_CHECK = '''failed=0
if [ "$PATHS_RESULT" != "success" ]; then
  echo "::error::check-paths result: $PATHS_RESULT"
  failed=1
fi
if [ "$STALENESS_RESULT" != "success" ]; then
  echo "::error::build-all-staleness result: $STALENESS_RESULT"
  failed=1
fi
exit "$failed"'''


def _step_enforces(step: dict, job_id: str) -> bool:
    """Recognize the current result-checking command forms, not mere reads."""
    run = str(step.get("run", "")).strip()
    result = "${{ needs." + job_id + ".result }}"
    if run == f'test "{result}" = success':
        return True
    if run == "test \"${{ contains(needs.*.result, 'failure') }}\" = false":
        return True
    env = step.get("env") or {}
    if job_id == "build-all-staleness" and run == _STALENESS_CHECK:
        return env.get("STALENESS_RESULT") == result
    # The pytest rollup delegates failure propagation to the tested helper.
    try:
        argv = shlex.split(run)
    except ValueError:
        return False
    if argv[:2] != ["python", "scripts/ci/require_job_results.py"]:
        return False
    checks = argv[2:]
    if len(checks) % 4 or any(checks[i] != "--check" for i in range(0, len(checks), 4)):
        return False
    return any(
        env.get(checks[i + 1]) == result and checks[i + 2] == "success"
        for i in range(0, len(checks), 4)
    )


def _rollup_enforces(rollup: dict, job_id: str) -> bool:
    """True when a rollup still runs after ``job_id`` fails and reads its result.

    The job ``if:`` must be exactly ``always()`` or ``!cancelled()``. Any other
    term, such as ``&& needs.<job_id>.result == 'success'``, skips the rollup
    when the need fails, and GitHub counts a skipped required check as passing.
    An unconditional step must check the result using a recognized enforcement
    form. Mere logging does not count. Neither job nor step may continue on error.
    """
    condition = str(rollup.get("if", "")).strip()
    if condition.startswith("${{") and condition.endswith("}}"):
        condition = condition[3:-2]
    if "".join(condition.split()) not in _RUN_AFTER_FAILURE:
        return False
    return not continues_on_error(rollup) and any(
        _step_enforces(step, job_id)
        for step in rollup.get("steps", [])
        if step.get("if") is None and not continues_on_error(step)
    )


def _is_required_job(jobs: dict[str, dict], job_id: str) -> bool:
    """True when the job's name is a required context, or a required rollup that
    needs it runs after a failure and reads its result."""
    if str(jobs[job_id].get("name")) in REQUIRED_CONTEXTS:
        return True
    for other in jobs.values():
        needs = other.get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        if (
            job_id in needs
            and str(other.get("name")) in REQUIRED_CONTEXTS
            and _rollup_enforces(other, job_id)
        ):
            return True
    return False


def ci_owners_of(script: str) -> list[str]:
    """Return ``<workflow> <job-id>`` for every required, unconditional job that runs ``script``.

    A job qualifies when a ``run:`` step names the script, the job has no
    job-level ``if:``, the step has no ``if:`` except the one ``ALLOWED_STEP_IF``
    names, neither the job nor the step sets ``continue-on-error``, and the job
    (or a rollup that needs it) is in ``REQUIRED_CONTEXTS``.
    """
    owners: list[str] = []
    for workflow in RATCHET_WORKFLOWS:
        jobs = workflow_jobs(workflow)
        for job_id, job in jobs.items():
            if job.get("if") is not None or continues_on_error(job):
                continue
            if not _is_required_job(jobs, job_id):
                continue
            for step in job.get("steps", []):
                if not runs_python_command(step, script):
                    continue
                if step.get("if") not in (None, ALLOWED_STEP_IF.get(script)):
                    continue
                if continues_on_error(step):
                    continue
                owners.append(f"{workflow} {job_id}")
    return owners
