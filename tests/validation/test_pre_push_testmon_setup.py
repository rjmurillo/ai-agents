"""The dependency and ignore-file setup the testmon hook needs (issue #6239)."""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
)

pytestmark = pytest.mark.usefixtures("default_environment")

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_testmon_is_declared_in_both_dev_dependency_lists() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = data["project"]["optional-dependencies"]["dev"]
    group = data["dependency-groups"]["dev"]
    for name, entries in (("extra", extra), ("group", group)):
        assert any(entry.startswith("pytest-testmon") for entry in entries), name


def test_the_testmon_database_is_git_ignored() -> None:
    """``.testmondata`` is local state; its SQLite sidecars must not be committed either."""
    for name in (".testmondata", ".testmondata-shm", ".testmondata-wal"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", name],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, f"{name} is not ignored"


def test_the_hook_module_does_not_import_the_selector() -> None:
    """Neither an import statement nor a module attribute names the old selector."""
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
    """The hook never receives a diff: testmon, not the hook, decides what runs."""
    assert list(inspect.signature(git_hook_policy.run_pytest).parameters) == ["repo_root"]
    assert list(inspect.signature(git_hook_policy._resolve_pytest_commands).parameters) == [
        "repo_root"
    ]


def test_the_pytest_subcommand_rejects_a_path_argument() -> None:
    """argparse exits 2, so no caller can hand the hook a subset to run."""
    result = subprocess.run(
        [sys.executable, inspect.getfile(git_hook_policy), "pytest", "somefile.py"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: somefile.py" in result.stderr
