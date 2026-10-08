"""Pre-push runs pytest collection only, with no test selection.

Issue #6239 AC5: the default pre-push pytest step runs the existing collection
command over ``tests/``, in one process, and a collection error fails the push.
Issue #6239 AC1: nothing in the hook module imports the selector.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_collection_helpers import (
    collection,
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
)

pytestmark = pytest.mark.usefixtures("default_environment")


def test_the_hook_module_does_not_import_the_selector() -> None:
    """AC1: neither an import statement nor a module attribute names the selector."""
    source = Path(inspect.getfile(git_hook_policy)).read_text(encoding="utf-8")
    imported = [
        name
        for node in ast.walk(ast.parse(source))
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or "", *(alias.name for alias in node.names)]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    ]
    assert not [name for name in imported if "test_selection" in name or "select_tests" in name]
    assert not hasattr(git_hook_policy, "select_tests")


def test_run_pytest_takes_no_changed_files_parameter() -> None:
    """AC5: the hook never receives a diff, so nothing can narrow the run."""
    assert list(inspect.signature(git_hook_policy.run_pytest).parameters) == ["repo_root"]
    assert list(inspect.signature(git_hook_policy._resolve_pytest_commands).parameters) == [
        "repo_root"
    ]


def test_default_pre_push_resolves_to_the_collection_command_only(tmp_path: Path) -> None:
    """AC5: one command, collect-only, over ``tests/``, with no worker pool."""
    commands = git_hook_policy._resolve_pytest_commands(tmp_path)
    assert commands == collection(tmp_path)
    (command,) = commands
    assert "--collect-only" in command
    assert command[-1] == str(tmp_path / "tests")
    assert "-n" not in command


def test_default_pre_push_runs_one_process_and_asks_git_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC5: ``run_pytest`` spawns the collection command once and consults no diff."""
    seen = record_runs(monkeypatch)
    monkeypatch.setattr(
        git_hook_policy,
        "_run_git",
        lambda *_a, **_k: pytest.fail("pre-push pytest must not ask git for a diff"),
    )
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert seen == collection(tmp_path)


@pytest.mark.parametrize("exit_code", [1, 2, 4])
def test_a_collection_error_fails_the_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exit_code: int
) -> None:
    """AC5: pytest exits nonzero on a collection error and the hook passes it on."""
    record_runs(monkeypatch, returncode=exit_code)
    assert git_hook_policy.run_pytest(tmp_path) == exit_code


def test_collection_command_runs_no_test_bodies(tmp_path: Path) -> None:
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert "--collect-only" in command
    assert "not integration" in command
    assert str(tmp_path / "tests") in command
    assert "-n" not in command


def test_collection_command_silences_the_node_listing(tmp_path: Path) -> None:
    """``pyproject.toml`` sets ``addopts = "-v ..."``, so one ``-q`` nets to zero.

    Measured: 31765 lines of node listing into the hook output with one ``-q``,
    878 with three. Hook output is a token cost this stand-in exists to cut.
    """
    assert git_hook_policy._pytest_collection_command(tmp_path).count("-q") == 3


def test_the_pytest_subcommand_rejects_a_path_argument() -> None:
    """AC5: argparse exits 2, so no caller can hand the hook a subset to run."""
    result = subprocess.run(
        [sys.executable, inspect.getfile(git_hook_policy), "pytest", "somefile.py"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: somefile.py" in result.stderr
