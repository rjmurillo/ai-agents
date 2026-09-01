"""The gates behind issue #4494 are wired, and the harnesses reach them.

A guard proves only that the guard works. It cannot prove any caller reached
it (`.claude/rules/testing.md` SHOULD 6), and issue #4494 is a report about
exactly that gap: the baseline-ratchet mutation harness existed, ran nothing,
and was named by no gate.

Two claims are pinned here, one per gate:

1. ``check_zero_collection_tests.py`` is invoked by a named lefthook pre-push
   job and by a blocking step in an unconditional ``pytest.yml`` job (not
   gated behind a path filter: it examines the whole tree, not the diff).
2. The mutation harnesses are reachable by the ``pytest (mutation)`` matrix
   leg: the partition exists in the workflow, the runner maps it to
   ``tests/mutation``, and each harness file contributes collectable tests.

Every wiring assertion parses the YAML and asserts against the object graph. A
substring match on the file text passes when the step has been deleted and its
name survives in a comment (`.claude/rules/testing.md` MUST 9). The collection
claim is proved the same way, by running the thing rather than reading it: it
spawns pytest and reads the exit code, because an AST shape check asserts that
``def test_*`` nodes exist, which is a different claim from AC1's "collects at
least one test under pytest --collect-only".
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import run_pytest_selected

REPO_ROOT = Path(__file__).resolve().parents[2]
LEFTHOOK = REPO_ROOT / "lefthook.yml"
PYTEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
GUARD_SCRIPT = "scripts/validation/check_zero_collection_tests.py"
MUTATION_DIRECTORY = "tests/mutation"

# Inherited pytest state would reach the child run as extra options or as a
# worker identity it must not adopt (`.claude/rules/testing.md` SHOULD 12).
_STRIPPED_PYTEST_ENVIRONMENT = frozenset(
    {
        "PYTEST_ADDOPTS",
        "PYTEST_CURRENT_TEST",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
    }
)

HARNESS_FILES = (
    "tests/mutation/test_mutate_baseline_ratchet_integrity.py",
    "tests/mutation/test_worktree_path_mutations.py",
)


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_jobs(node: Any) -> list[dict[str, Any]]:
    """Flatten lefthook's nested job/group structure into a list of jobs."""
    jobs: list[dict[str, Any]] = []
    if isinstance(node, list):
        for entry in node:
            jobs.extend(_iter_jobs(entry))
        return jobs
    if not isinstance(node, dict):
        return jobs
    if "group" in node:
        jobs.extend(_iter_jobs(node["group"].get("jobs", [])))
        return jobs
    if "jobs" in node:
        jobs.extend(_iter_jobs(node["jobs"]))
    jobs.append(node)
    return jobs


def _pre_push_jobs() -> list[dict[str, Any]]:
    return _iter_jobs(_load(LEFTHOOK)["pre-push"]["jobs"])


def _workflow_job(name: str) -> dict[str, Any]:
    return _load(PYTEST_WORKFLOW)["jobs"][name]


def _workflow_steps(job_name: str = "test") -> list[dict[str, Any]]:
    return _workflow_job(job_name)["steps"]


def test_a_named_pre_push_job_runs_the_zero_collection_guard() -> None:
    """Local pushes fail on a zero-collecting file before CI ever sees it."""
    matching = [
        job for job in _pre_push_jobs() if GUARD_SCRIPT in str(job.get("run", ""))
    ]

    assert len(matching) == 1, f"expected one pre-push job running {GUARD_SCRIPT}"
    assert matching[0]["name"] == "zero-collection-tests"


def test_the_pre_push_job_running_the_guard_has_no_path_filter() -> None:
    """A ``glob`` here would silently narrow a whole-tree check to a diff.

    Copilot review round 9 (PR #5344): ``lefthook.yml``'s comment above this
    job makes the absence of a ``glob`` load-bearing (a lockfile-only or
    interpreter-only push changes the pytest environment this script
    measures), but nothing pinned that beyond the comment. A future edit
    could re-add ``glob: ["**/*.py", "pyproject.toml"]`` and this test suite
    would not notice.
    """
    matching = [
        job for job in _pre_push_jobs() if GUARD_SCRIPT in str(job.get("run", ""))
    ]

    assert len(matching) == 1, f"expected one pre-push job running {GUARD_SCRIPT}"
    assert "glob" not in matching[0], (
        "the zero-collection-tests pre-push job must not be gated behind a "
        "path filter; it is a whole-tree check, not a diff-scoped one"
    )


def test_the_workflow_step_running_the_guard_is_blocking() -> None:
    """continue-on-error would make the step a reporter, not a gate."""
    matching = [
        step
        for step in _workflow_steps("zero-collection-guard")
        if GUARD_SCRIPT in str(step.get("run", ""))
    ]

    assert len(matching) == 1, f"expected one pytest.yml step running {GUARD_SCRIPT}"
    assert matching[0].get("continue-on-error") is not True


def test_the_workflow_job_running_the_guard_is_unconditional() -> None:
    """A whole-tree guard MUST run without a path filter (`.claude/rules/ci-scripts.md`).

    Copilot review round 3 (PR #5344): this step used to live inside the
    ``test`` job's ``bulk`` partition, which is gated behind
    ``needs.check-paths.outputs.python-changed == 'true'``. A mainline push
    that touches no Python-matched path would then skip the whole job and
    publish the workflow's existing success, without the guard ever measuring
    the current tree. The step's own ``continue-on-error`` check above cannot
    see a skip one level up, at the job.
    """
    job = _workflow_job("zero-collection-guard")

    assert "if" not in job, (
        "the zero-collection-guard job must not be gated behind a path filter"
    )
    assert "needs" not in job, (
        "the zero-collection-guard job must not depend on check-paths, which "
        "would let its 'if' condition gate this job transitively"
    )


def test_the_required_pytest_context_checks_the_guard_result() -> None:
    """A failed guard MUST fail the "Run Python Tests" required context.

    Copilot review round 4 (PR #5344): ``zero-collection-guard`` runs
    unconditionally, but neither aggregator job that publishes the "Run
    Python Tests" required context (``test-result`` when Python inputs
    changed, ``skip-tests`` when they did not) named it. The guard could
    therefore fail while the required context still reported success.
    Both aggregators now depend on ``zero-collection-guard`` and gate their
    own success on its result via ``require_job_results.py``.
    """
    for job_name in ("test-result", "skip-tests"):
        job = _workflow_job(job_name)
        assert job["name"] == "Run Python Tests"
        assert "zero-collection-guard" in job["needs"], (
            f"{job_name} must depend on zero-collection-guard"
        )
        # !cancelled() (or another status function) is required: without one,
        # GitHub's default implicit success()-over-needs gate would silently
        # skip this aggregator on a guard failure instead of failing it,
        # leaving the required context missing rather than red.
        assert any(
            function in job["if"] for function in ("cancelled()", "always()", "failure()")
        ), f"{job_name}'s if must not rely on the implicit success()-over-needs gate"
        commands = " ".join(
            str(step.get("run", "")) for step in job["steps"]
        )
        assert "ZERO_COLLECTION_RESULT" in commands, (
            f"{job_name} must check needs.zero-collection-guard.result"
        )


def test_the_workflow_declares_a_mutation_partition() -> None:
    """AC4: the gate that invokes the mutation harnesses is a real matrix leg."""
    include = _load(PYTEST_WORKFLOW)["jobs"]["test"]["strategy"]["matrix"]["include"]

    assert "mutation" in {leg["partition"] for leg in include}


def test_the_run_pytest_step_passes_the_partition_to_the_runner() -> None:
    """The matrix leg only reaches tests/mutation through this argument."""
    matching = [
        step for step in _workflow_steps() if step.get("id") == "run-pytest"
    ]

    assert len(matching) == 1
    command = str(matching[0]["run"])
    assert "scripts/ci/run_pytest_selected.py" in command
    assert "--partition ${{ matrix.partition }}" in command
    assert matching[0].get("continue-on-error") is not True


def test_the_mutation_partition_covers_the_mutation_directory() -> None:
    """The runner, not the workflow, decides what the partition runs."""
    assert MUTATION_DIRECTORY in run_pytest_selected._PARTITION_FULL_ARGS["mutation"]


@pytest.mark.parametrize("relative", HARNESS_FILES)
def test_each_harness_is_routed_to_the_mutation_partition(relative: str) -> None:
    """A harness no partition claims is run by nobody."""
    assert run_pytest_selected.classify_partition(relative) == "mutation"


@pytest.mark.parametrize("relative", HARNESS_FILES)
def test_each_harness_defines_collectable_tests(relative: str) -> None:
    """AC1: living in testpaths is not the same as contributing a test.

    Both files carried the test_ prefix, sat inside testpaths, and defined no
    test function, so pytest collected nothing and exited 5, which every
    runner reads as success.

    AC1 says "collects at least one test under pytest --collect-only", so this
    runs the collection rather than inspecting the source. An AST shape check
    passes for a harness whose test functions exist and are never collected: a
    module-level skip, a collection error, and an import-mode shadowing all
    leave the ``def test_*`` nodes intact while collecting nothing. Exit 0 is
    the only outcome that means items were collected; 5 is nothing collected,
    2 a collection error, 4 a bad path.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in _STRIPPED_PYTEST_ENVIRONMENT
    }

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", relative, "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )

    assert completed.returncode == 0, (
        f"{relative} collected nothing under --collect-only "
        f"(exit {completed.returncode})\n{completed.stdout[-2000:]}\n"
        f"{completed.stderr[-2000:]}"
    )
