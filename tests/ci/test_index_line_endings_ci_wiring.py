"""The index-line-endings gate must run in CI, unfiltered (#5475).

The producer this gate exists for is the GraphQL `createCommitOnBranch` API:
it uploads file contents verbatim and runs no local hook, which is how two
CRLF blobs reached `main` under `* text=auto eol=lf` and aborted every merge
that touched them. A gate registered only in `pre_pr_sequence` is invisible to
that path, so the local wiring test is necessary and not sufficient.

Step-level assertions alone are not sufficient either. The gate first lived in
the `test` job, whose `if:` is `needs.check-paths.outputs.python-changed ==
'true'`. A CRLF blob under a `.md` path, which is exactly the incident, turns
that false and the whole job is skipped, so a step-level `if:` with no path
predicate still measured nothing. These tests pin the job as well: it carries
no `needs:` and no `if:`, and its result is required by the aggregator that
branch protection actually watches.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
SCRIPT = "scripts/validation/check_index_line_endings.py"
AGGREGATOR_JOB = "test-result"


def _jobs() -> dict[str, dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _gate_jobs() -> dict[str, dict]:
    """Select jobs by the script they run, not by job or step name.

    A name match would keep passing if the job were renamed while the command
    was swapped for something else.
    """
    return {
        job_id: job
        for job_id, job in _jobs().items()
        if any(SCRIPT in str(step.get("run", "")) for step in job.get("steps", []))
    }


def test_the_script_exists_at_the_path_ci_invokes() -> None:
    """A green workflow that shells to a missing file is not coverage."""
    assert (REPO_ROOT / SCRIPT).is_file()


def test_ci_runs_the_index_line_endings_gate() -> None:
    assert _gate_jobs(), (
        f"no job in {WORKFLOW.name} runs {SCRIPT}. The local pre_pr "
        "registration cannot see a createCommitOnBranch push."
    )


def test_the_gate_job_is_not_path_filtered() -> None:
    """The defect's own shape turns the Python path filter false.

    A CRLF blob under a `.md` path leaves `python-changed` false, so any job
    gated on it is skipped exactly when this gate is needed.
    """
    for job_id, job in _gate_jobs().items():
        assert "needs" not in job, (
            f"job '{job_id}' depends on {job.get('needs')}; a whole-tree guard "
            "must not inherit another job's path filter"
        )
        assert "if" not in job, (
            f"job '{job_id}' is conditional on {job.get('if')!r}; it must run "
            "on every supported event"
        )


def test_the_gate_step_is_not_conditional() -> None:
    """No matrix partition or event predicate on the step either."""
    for job in _gate_jobs().values():
        for step in job.get("steps", []):
            if SCRIPT in str(step.get("run", "")):
                assert "if" not in step, step.get("if")


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_the_workflow_still_triggers_on_the_events_that_matter(event: str) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses a bare `on:` key as the boolean True.
    triggers = workflow.get("on", workflow.get(True))

    assert event in triggers


def test_the_aggregator_requires_the_gate_job() -> None:
    """Branch protection watches the aggregator, not the guard job directly.

    Without this the guard could go red while `Run Python Tests` stayed green,
    which is a required check reporting success over a failed guard.
    """
    gate_ids = set(_gate_jobs())
    aggregator = _jobs()[AGGREGATOR_JOB]

    assert gate_ids <= set(aggregator["needs"]), (
        f"{AGGREGATOR_JOB} needs {aggregator['needs']}, missing {gate_ids}"
    )

    step = next(
        s for s in aggregator["steps"] if "require_job_results.py" in str(s.get("run", ""))
    )
    env = step["env"]
    result_vars = [
        name
        for name, value in env.items()
        if any(f"needs.{job_id}.result" in str(value) for job_id in gate_ids)
    ]
    assert result_vars, f"no env var carries the guard's result: {env}"
    for name in result_vars:
        assert f"--check {name} success" in str(step["run"]), (
            f"{name} is passed to the job but never checked"
        )
