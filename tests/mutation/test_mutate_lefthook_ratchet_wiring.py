"""Mutation checks for the CI-owned count ratchet contract (issue #5317, 2026-11-27 ruling)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree
from tests.mutation._nested_pytest import private_basetemp

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK_REL = Path("lefthook.yml")
_WORKFLOW_REL = Path(".github/workflows/pr-validation.yml")
_TEST_PATH = "tests/ci/test_lefthook_ratchet_wiring.py"
# A kept pre-push job; renaming it to a removed job reintroduces that job.
_KEPT_JOB = "          - name: python-lint-advisory"
_REMOVED_JOBS = ("count-ratchets", "plugin-scanner")


def _run_wiring_tests(repo_root: Path) -> tuple[int, str]:
    with private_basetemp() as basetemp:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", basetemp, _TEST_PATH, "-x", "-q"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            cwd=repo_root,
        )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    with isolated_mutation_worktree(_REPO_ROOT, [_LEFTHOOK_REL, _WORKFLOW_REL]) as workspace:
        yield workspace.root


@pytest.mark.parametrize(
    ("target", "old", "new", "should_fail"),
    [
        # Reintroducing either removed heavy job in the hook must fail.
        *((_LEFTHOOK_REL, _KEPT_JOB, f"          - name: {job}", True) for job in _REMOVED_JOBS),
        # Breaking CI ownership of one ratchet script must fail.
        (
            _WORKFLOW_REL,
            "scripts/ci/taste_count_ratchet.py --base-ref FETCH_HEAD",
            "scripts/ci/taste_count_ratchet_gone.py --base-ref FETCH_HEAD",
            True,
        ),
        # A job-level `if:` on the required job makes the ratchets conditional.
        (
            _WORKFLOW_REL,
            "  validate-pr:\n",
            "  validate-pr:\n    if: github.event_name == 'never'\n",
            True,
        ),
        (
            _LEFTHOOK_REL,
            "    # a ratchet or policy miss costs seconds, not semgrep and pre-pr-validation.",
            "    # an inert comment mutation must leave wiring tests green.",
            False,
        ),
    ],
)
def test_ci_ownership_mutations_fail_wiring_tests(
    mutation_repo: Path, target: Path, old: str, new: str, should_fail: bool
) -> None:
    lefthook = mutation_repo / target
    original = lefthook.read_text(encoding="utf-8")
    assert original.count(old) == 1

    try:
        lefthook.write_text(original.replace(old, new), encoding="utf-8")
        return_code, output = _run_wiring_tests(mutation_repo)
    finally:
        lefthook.write_text(original, encoding="utf-8")

    assert return_code != 4, f"Mutation suite did not collect:\n{output}"
    assert "no tests ran" not in output.lower(), output
    assert (return_code != 0) is should_fail, output
    assert lefthook.read_text(encoding="utf-8") == original
