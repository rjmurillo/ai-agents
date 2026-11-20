"""Shared fixtures for the doc-date-drift gate tests.

Every commit is stamped with ``COMMIT_WHEN`` so the header-pair rule, which
compares Next Review with the HEAD commit date, never depends on the clock the
suite runs under. A test that wants a different commit date passes ``when``.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path

import pytest

from scripts.validation import check_doc_date_drift as checker

COMMIT_WHEN = "2026-10-24T12:00:00+0000"
COMMIT_DATE = date(2026, 10, 24)


def _git(root: Path, *args: str, when: str = COMMIT_WHEN) -> None:
    env = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
    )


def write_files(root: Path, files: dict[str, str]) -> None:
    """Write each relative path with its text, creating parent directories."""
    for relpath, text in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path, base_files: dict[str, str] | None = None) -> Path:
    """Create a repo whose ``main`` holds ``base_files``, then branch ``feature``."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    write_files(root, {"README.md": "base\n", **(base_files or {})})
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def commit_head(root: Path, head_files: dict[str, str], when: str = COMMIT_WHEN) -> None:
    """Write ``head_files`` and commit them on the feature branch."""
    write_files(root, head_files)
    _git(root, "add", "-A", when=when)
    _git(root, "commit", "-q", "-m", "docs", when=when)


def drift(root: Path, head_date: date | None = None) -> list[checker.Finding]:
    """Return the findings of the gate's scan of ``main...HEAD``."""
    outcome = checker.find_doc_date_drift(root, "main", head_date=head_date)
    assert outcome is not None, "git failed while scanning the fixture repo"
    return outcome[0]


def run_cli(root: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
    """Run the CLI against ``main`` and return (exit code, stdout)."""
    code = checker.main(["--repo-root", str(root), "--base", "main", *extra])
    return code, capsys.readouterr().out


def cite(path: str, line: int) -> str:
    """Return the ``path:line:`` prefix a finding carries.

    Built at runtime so this tree's test sources never hold a literal
    ``path:line`` shape for the citation-freshness gate to resolve.
    """
    return f"{path}:{line}:"


def where(finding: checker.Finding) -> tuple[str, int]:
    """Return the flagged (path, line) of a finding."""
    return finding.path, finding.line


def rules(findings: list[checker.Finding]) -> set[str]:
    """Return the distinct rule ids among the findings."""
    return {finding.rule for finding in findings}
