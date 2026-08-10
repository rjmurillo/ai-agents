"""Shared fixtures for the pytest HEAD guard suites.

``tests/test_pytest_head_guard.py`` (trace/reflog/attribution behavior) and
``tests/test_pytest_head_fastpath.py`` (direct-read/path-safety fast path)
both load the root ``conftest.py`` by path and drive real throwaway git
repositories, so the loader and repo-builder helpers live here instead of
being duplicated across the two files.

Kept out of ``conftest.py`` because these helpers are specific to the HEAD
guard suites; a generic name in the package-wide conftest would be visible
to every test module.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_root_conftest():
    """Load the root ``conftest.py`` as a fresh, independent module object.

    Each call re-executes the module so a test that monkeypatches it never
    leaks state into another test's module instance.
    """
    path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location("root_conftest_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["root_conftest_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _run_git(repo: Path, *args: str, env=None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=10,
    )
    return result.stdout.strip()


def _commit_file(repo: Path, content: str, message: str, env=None) -> str:
    (repo / "file.txt").write_text(content, encoding="utf-8")
    _run_git(repo, "add", "file.txt")
    _run_git(
        repo,
        "-c",
        "user.name=pytest",
        "-c",
        "user.email=pytest@example.invalid",
        "commit",
        "--quiet",
        "-m",
        message,
        env=env,
    )
    return _run_git(repo, "rev-parse", "HEAD")


def _init_git_repo(repo: Path) -> str:
    repo.mkdir()
    _run_git(repo, "init", "--quiet")
    return _commit_file(repo, "initial\n", "initial")
