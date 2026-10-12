"""Staged-file collection tests for scan_vulnerabilities (issue #6174)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import PROJECT_ROOT, import_skill_script

SCRIPT_RELATIVE = ".claude/skills/security-scan/scripts/scan_vulnerabilities.py"
SCRIPT = PROJECT_ROOT / SCRIPT_RELATIVE
mod = import_skill_script(SCRIPT_RELATIVE, "scan_vulnerabilities_staged_under_test")

CLEAN_SH = "#!/bin/bash\necho hello\n"
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VULNERABILITIES = 10


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with two committed shell scripts."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "gone.sh").write_text(CLEAN_SH)
    (tmp_path / "stays.sh").write_text(CLEAN_SH)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    return tmp_path


def _run_cli(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--git-staged", "--format", "json"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_staged_deletion_is_excluded_from_collection(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "rm", "-q", "gone.sh")
    monkeypatch.chdir(repo)
    assert mod.get_staged_files() == []


def test_staged_modification_is_still_collected(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "stays.sh").write_text(CLEAN_SH + "echo more\n")
    _git(repo, "add", "stays.sh")
    monkeypatch.chdir(repo)
    assert mod.get_staged_files() == ["stays.sh"]


def test_staged_addition_is_still_collected(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "new.sh").write_text(CLEAN_SH)
    _git(repo, "add", "new.sh")
    monkeypatch.chdir(repo)
    assert mod.get_staged_files() == ["new.sh"]


def test_staged_rename_collects_new_path_only(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(repo, "mv", "gone.sh", "renamed.sh")
    monkeypatch.chdir(repo)
    assert mod.get_staged_files() == ["renamed.sh"]


def test_deletion_alongside_modification_collects_only_the_survivor(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "rm", "-q", "gone.sh")
    (repo / "stays.sh").write_text(CLEAN_SH + "echo more\n")
    _git(repo, "add", "stays.sh")
    monkeypatch.chdir(repo)
    assert mod.get_staged_files() == ["stays.sh"]


def test_cli_exits_zero_when_only_a_deletion_is_staged(repo: Path) -> None:
    _git(repo, "rm", "-q", "gone.sh")
    proc = _run_cli(repo)
    assert proc.returncode == EXIT_SUCCESS, proc.stdout + proc.stderr
    assert "Error reading" not in proc.stdout + proc.stderr


def test_cli_scans_survivor_and_ignores_deletion(repo: Path) -> None:
    _git(repo, "rm", "-q", "gone.sh")
    (repo / "stays.sh").write_text('#!/bin/bash\neval "$1"\n')
    _git(repo, "add", "stays.sh")
    proc = _run_cli(repo)
    payload = json.loads(proc.stdout)
    assert proc.returncode == EXIT_VULNERABILITIES, proc.stdout + proc.stderr
    assert payload["files_scanned"] == 1
    assert not payload["errors"]


def test_unreadable_surviving_file_still_errors(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "stays.sh").write_text(CLEAN_SH + "echo more\n")
    _git(repo, "add", "stays.sh")
    (repo / "stays.sh").unlink()
    monkeypatch.chdir(repo)
    assert mod.get_staged_files() == ["stays.sh"]
    _, messages = mod.scan_file("stays.sh")
    assert messages
    assert messages[0].startswith("Error reading stays.sh")
    proc = _run_cli(repo)
    assert proc.returncode == EXIT_ERROR, proc.stdout + proc.stderr


def test_git_failure_message_names_the_filtered_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(mod.GitEnumerationError, match="--diff-filter=d failed"):
        mod.get_staged_files()
