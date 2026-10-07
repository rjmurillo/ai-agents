"""Shared helpers for the mypy ratchet tests: env isolation and a real git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.git_hook_policy import MYPY_RATCHET_BASE_REF_ENV

SAMPLE_PATH = "app/sample.py"
PRE_EXISTING_ERROR = 'def legacy() -> int:\n    return "not an int"\n'


def isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the variables the ratchet reads, and restore them after the test.

    main() writes MYPY_RATCHET_BASE_REF into os.environ. delenv on an absent
    key records nothing to restore, so setenv first: teardown then removes the
    value main() wrote instead of leaking it into later tests.
    """
    for name in ("GITHUB_EVENT_NAME", MYPY_RATCHET_BASE_REF_ENV):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def check_git(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def write(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    check_git(repo, "add", "-A")
    check_git(repo, "commit", "-qm", message)
    return check_git(repo, "rev-parse", "HEAD")


def make_repo_with_type_debt(tmp_path: Path) -> tuple[Path, str]:
    """Create a repository whose base commit already carries one mypy error."""
    repo = tmp_path / "repo"
    repo.mkdir()
    check_git(repo, "init", "-q", "-b", "main")
    check_git(repo, "config", "user.email", "test@example.com")
    check_git(repo, "config", "user.name", "Test")
    check_git(repo, "config", "commit.gpgsign", "false")
    write(repo, "pyproject.toml", '[tool.mypy]\npython_version = "3.14"\n')
    write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR)
    write(repo, "README.md", "fixture\n")
    return repo, commit(repo, "base with type debt")


def error_at(line: int) -> str:
    """Render the prefix mypy prints for an error in the fixture file."""
    return f"{SAMPLE_PATH}:{line}: error"
