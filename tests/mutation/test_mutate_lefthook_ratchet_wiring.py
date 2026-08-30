"""Mutation checks for the aggregate pre-push ratchet job (issue #5317)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK_REL = Path("lefthook.yml")
_TEST_PATH = "tests/ci/test_lefthook_ratchet_wiring.py"


def _run_wiring_tests(repo_root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", _TEST_PATH, "-x", "-q"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        cwd=repo_root,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    with isolated_mutation_worktree(_REPO_ROOT, [_LEFTHOOK_REL]) as workspace:
        yield workspace.root


@pytest.mark.parametrize(
    ("old", "new", "should_fail"),
    [
        (
            "          - name: count-ratchets",
            "          - name: deleted-ratchets",
            True,
        ),
        (
            "            run: uv run --frozen python scripts/validation/checks_ratchet.py",
            "            run: echo MUTANT-DELETED",
            True,
        ),
        (
            "    # a ratchet or policy miss costs seconds, not a full pytest run.",
            "    # an inert comment mutation must leave wiring tests green.",
            False,
        ),
    ],
)
def test_aggregate_job_mutations_fail_wiring_tests(
    mutation_repo: Path, old: str, new: str, should_fail: bool
) -> None:
    lefthook = mutation_repo / _LEFTHOOK_REL
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
