"""The index-line-endings gate must run in CI, unfiltered (#5475).

The producer this gate exists for is the GraphQL `createCommitOnBranch` API:
it uploads file contents verbatim and runs no local hook, which is how two
CRLF blobs reached `main` under `* text=auto eol=lf` and aborted every merge
that touched them. A gate registered only in `pre_pr_sequence` is invisible to
that path, so the local wiring test is necessary and not sufficient.

Step-level assertions alone are not sufficient either. The gate first lived in
the `test` job, whose `if:` is `needs.check-paths.outputs.python-changed ==
'true'`, so a step-level `if:` with no path predicate still measured nothing
whenever that job was skipped.

`.md` is not the example, and the earlier version of this docstring was wrong
to use it: the `python` filter carries `**/*.md`, so the two incident handoffs
would have turned `python-changed` true. The gap is the text paths the filter
omits. `.gitattributes` applies `* text=auto eol=lf` to every tracked file;
measured against the filter, `**/*.xml` has no glob at all (7 tracked files),
and of the 16 tracked `.sh` files only `scripts/bootstrap-vm.sh` is listed
while `.gitattributes` declares `*.sh text eol=lf`.

These tests pin the job as well: it carries no `needs:` and no `if:`, and its
result is required by every job that publishes the required check, not only
the one that runs when Python changed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.test_selection import path_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
SCRIPT = "scripts/validation/check_index_line_endings.py"

# Two jobs carry this name and they are mutually exclusive: `test-result` when
# the change touched Python, `skip-tests` when it did not. Branch protection
# watches the name, so whichever one runs is the required check, and both have
# to gate on the guard. Selected by name rather than by id, so a third leg
# added later is covered the day it appears.
REQUIRED_CHECK_NAME = "Run Python Tests"


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
    """A whole-tree gate must not inherit a diff-shaped condition.

    Not `.md`: `test_the_filter_gap_this_job_exists_for_is_real` below proves
    `**/*.md` is in the filter, so a Markdown-only change does run the
    filtered job. The uncovered text paths are the ones that matter here,
    `**/*.xml` and 15 of the 16 tracked `.sh` files, and a job gated on
    `python-changed` is skipped for exactly those.
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


def _required_check_jobs() -> dict[str, dict]:
    """Every job reporting the required status check, by id."""
    jobs = {
        job_id: job
        for job_id, job in _jobs().items()
        if job.get("name") == REQUIRED_CHECK_NAME
    }
    assert jobs, f"no job renders as {REQUIRED_CHECK_NAME!r} in {WORKFLOW.name}"
    return jobs


@pytest.mark.parametrize("job_id", sorted(_required_check_jobs()))
def test_every_required_check_leg_requires_the_gate_job(job_id: str) -> None:
    """The guard's own context is not required; the aggregator's is.

    So a leg that reports `Run Python Tests` without waiting on the guard
    reports success over a red guard. `test-result` and `skip-tests` are
    mutually exclusive on `python-changed`, and `skip-tests` is the leg that
    runs on exactly the change this gate exists for: a CRLF blob under a
    non-Python path. Gating only `test-result` therefore left the reported
    bypass open one level up from where it was found.
    """
    gate_ids = set(_gate_jobs())
    job = _required_check_jobs()[job_id]

    assert gate_ids <= set(job["needs"]), (
        f"{job_id} needs {job['needs']}, missing {gate_ids}"
    )


@pytest.mark.parametrize("job_id", sorted(_required_check_jobs()))
def test_every_required_check_leg_asserts_the_gate_result(job_id: str) -> None:
    """`needs` alone is not enough under `!cancelled()`.

    Both legs run even when a dependency failed, by design, so that the
    required context reports failed rather than going missing. That makes the
    explicit result assertion the thing that actually fails the check.
    """
    gate_ids = set(_gate_jobs())
    job = _required_check_jobs()[job_id]

    step = next(
        s for s in job["steps"] if "require_job_results.py" in str(s.get("run", ""))
    )
    env = step["env"]
    result_vars = [
        name
        for name, value in env.items()
        if any(f"needs.{job_id}.result" in str(value) for job_id in gate_ids)
    ]
    assert result_vars, f"no env var in {job_id} carries the guard's result: {env}"
    for name in result_vars:
        assert f"--check {name} success" in str(step["run"]), (
            f"{name} is passed to {job_id} but never checked"
        )


def _python_filter() -> set[str]:
    """The `python` path filter this workflow's `check-paths` job publishes.

    Issue #5318 moved the list into `scripts/test_selection/path_policy.yml`,
    which `check-paths` names as its `filters:` input and `select_tests.py`
    reads too. `_filter_input_names_the_policy_file` below pins that wiring, so
    reading the policy through its loader here still describes this job.
    """
    return set(path_policy.load_patterns())


def _filter_input() -> str:
    for step in _jobs()["check-paths"]["steps"]:
        raw = step.get("with", {}).get("filters")
        if raw:
            return str(raw)
    raise AssertionError("check-paths publishes no `filters` input")


def test_the_filter_input_names_the_policy_file() -> None:
    """The gate and the local selector must read the same document.

    Without this, `_python_filter` could go on describing a list the workflow
    stopped using, and every assertion below it would measure the wrong file.
    """
    named = _filter_input().strip()
    assert named == "scripts/test_selection/path_policy.yml", named
    assert (REPO_ROOT / named).is_file(), f"{named} is named by pytest.yml but absent"


def _tracked(pattern: str) -> list[str]:
    return [
        line
        for line in subprocess.run(
            ["git", "ls-files", pattern],
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=True,
        ).stdout.splitlines()
        if line
    ]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_filter_gap_this_job_exists_for_is_real() -> None:
    """Pin the rationale so the comment above the job cannot rot into fiction.

    An earlier version of this rationale used `.md` as the example. The filter
    carries `**/*.md`, so that was wrong and the review caught it. The gap is
    the text paths the filter omits, and `.gitattributes` applies
    `* text=auto eol=lf` to all of them.

    If this ever fails because the filter widened, the guard job is still
    correct: a whole-tree gate must not depend on a diff. Update the rationale
    to name whatever remains uncovered, or state that nothing does.
    """
    python_filter = _python_filter()

    assert "**/*.md" in python_filter, "the .md counter-example no longer holds"
    assert not [glob for glob in python_filter if "xml" in glob]
    assert len(_tracked("*.xml")) > 0, "no tracked .xml left to demonstrate the gap"

    shell_globs = [glob for glob in python_filter if glob.endswith(".sh")]
    assert shell_globs == ["scripts/bootstrap-vm.sh"]
    assert len(_tracked("*.sh")) > len(shell_globs)
