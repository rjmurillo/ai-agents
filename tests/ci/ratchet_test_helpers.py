"""Shared fixtures for count-ratchet tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

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
    data = yaml.safe_load((_WORKFLOWS / workflow).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    jobs = data.get("jobs")
    assert isinstance(jobs, dict)
    return jobs


def _is_required_job(jobs: dict[str, dict], job_id: str) -> bool:
    """True when the job's name, or a rollup job that needs it, is a required context."""
    if str(jobs[job_id].get("name")) in REQUIRED_CONTEXTS:
        return True
    for other in jobs.values():
        needs = other.get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        if job_id in needs and str(other.get("name")) in REQUIRED_CONTEXTS:
            return True
    return False


def ci_owners_of(script: str) -> list[str]:
    """Return ``<workflow> <job-id>`` for every required, unconditional job that runs ``script``.

    A job qualifies when a ``run:`` step names the script, the job has no
    job-level ``if:``, the step has no ``if:`` except the one ``ALLOWED_STEP_IF``
    names, and the job (or a rollup that needs it) is in ``REQUIRED_CONTEXTS``.
    """
    owners: list[str] = []
    for workflow in RATCHET_WORKFLOWS:
        jobs = workflow_jobs(workflow)
        for job_id, job in jobs.items():
            if job.get("if") is not None or not _is_required_job(jobs, job_id):
                continue
            for step in job.get("steps", []):
                if script not in str(step.get("run", "")):
                    continue
                if step.get("if") not in (None, ALLOWED_STEP_IF.get(script)):
                    continue
                owners.append(f"{workflow} {job_id}")
    return owners
