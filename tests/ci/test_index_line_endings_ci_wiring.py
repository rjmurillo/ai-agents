"""The index-line-endings gate must run in CI, not only in local hooks (#5475).

The producer this gate exists for is the GraphQL `createCommitOnBranch` API:
it uploads file contents verbatim and runs no local hook, which is how two
CRLF blobs reached `main` under `* text=auto eol=lf` and aborted every merge
that touched them. A gate registered only in `pre_pr_sequence` is invisible to
that path, so the local wiring test is necessary and not sufficient.

These pin the CI half: the step exists, it runs unconditionally for the
partition it lives in rather than behind a path filter, and it invokes the
real script.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
SCRIPT = "scripts/validation/check_index_line_endings.py"
JOB_ID = "test"


def _steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert JOB_ID in jobs, f"job '{JOB_ID}' is gone from {WORKFLOW.name}: {sorted(jobs)}"
    return jobs[JOB_ID]["steps"]


def _gate_steps() -> list[dict]:
    """Select by the script it runs, not by step name.

    A name match would keep passing if the step were renamed while the command
    was swapped for something else.
    """
    return [step for step in _steps() if SCRIPT in str(step.get("run", ""))]


def test_the_script_exists_at_the_path_ci_invokes() -> None:
    """A green workflow that shells to a missing file is not coverage."""
    assert (REPO_ROOT / SCRIPT).is_file()


def test_ci_runs_the_index_line_endings_gate() -> None:
    gate_steps = _gate_steps()

    assert gate_steps, (
        f"no step in {WORKFLOW.name}:{JOB_ID} runs {SCRIPT}. The local "
        "pre_pr registration cannot see a createCommitOnBranch push."
    )


def test_the_gate_step_is_not_behind_a_path_filter() -> None:
    """A per-change filter would report green without reading the tree.

    The gate is absolute over every tracked blob, so its condition may select a
    partition but must not depend on which files a change touched.
    """
    for step in _gate_steps():
        condition = str(step.get("if", ""))
        assert "paths" not in condition, condition
        assert "changed" not in condition, condition


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_the_gate_step_condition_does_not_exclude_an_event(event: str) -> None:
    """Unlike the ratchets beside it, this gate needs no base-ref comparison.

    The ratchets split into pull_request and non-PR legs because they diff
    against a base. This one does not, so a condition naming an event would
    silently drop a whole class of push from coverage.
    """
    for step in _gate_steps():
        assert f"github.event_name != '{event}'" not in str(step.get("if", ""))
