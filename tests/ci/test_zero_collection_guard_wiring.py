"""The gates behind issue #4494 are wired, and the harnesses reach them.

A guard proves only that the guard works. It cannot prove any caller reached
it (`.claude/rules/testing.md` SHOULD 6), and issue #4494 is a report about
exactly that gap: the baseline-ratchet mutation harness existed, ran nothing,
and was named by no gate.

Two claims are pinned here, one per gate:

1. ``check_zero_collection_tests.py`` is invoked by a named lefthook pre-push
   job and by a blocking step in ``pytest.yml``.
2. The mutation harnesses are reachable by the ``pytest (mutation)`` matrix
   leg: the partition exists in the workflow, the runner maps it to
   ``tests/mutation``, and each harness file contributes collectable tests.

Every assertion parses the YAML and asserts against the object graph. A
substring match on the file text passes when the step has been deleted and its
name survives in a comment (`.claude/rules/testing.md` MUST 9).
"""

from __future__ import annotations

import ast
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


def _workflow_steps() -> list[dict[str, Any]]:
    return _load(PYTEST_WORKFLOW)["jobs"]["test"]["steps"]


def test_a_named_pre_push_job_runs_the_zero_collection_guard() -> None:
    """Local pushes fail on a zero-collecting file before CI ever sees it."""
    matching = [
        job for job in _pre_push_jobs() if GUARD_SCRIPT in str(job.get("run", ""))
    ]

    assert len(matching) == 1, f"expected one pre-push job running {GUARD_SCRIPT}"
    assert matching[0]["name"] == "zero-collection-tests"


def test_the_workflow_step_running_the_guard_is_blocking() -> None:
    """continue-on-error would make the step a reporter, not a gate."""
    matching = [
        step for step in _workflow_steps() if GUARD_SCRIPT in str(step.get("run", ""))
    ]

    assert len(matching) == 1, f"expected one pytest.yml step running {GUARD_SCRIPT}"
    assert matching[0].get("continue-on-error") is not True


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
    """
    tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
    functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]

    assert functions, f"{relative} defines no module-level test_ function"
