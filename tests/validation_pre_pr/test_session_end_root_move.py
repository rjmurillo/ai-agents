"""Pre-PR session gate ignores session logs the branch only moved (issue #5420)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation import checks_tooling

LOG = "2025-01-01-session-1.json"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path, before: str, after: str) -> Path:
    repo = tmp_path / "repo"
    (repo / ".agents" / "sessions").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "user.email", "t@example.com")
    (repo / ".agents" / "sessions" / LOG).write_text(before, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "feature")
    (repo / ".project-toolkit").mkdir()
    _git(repo, "mv", ".agents/sessions", ".project-toolkit/sessions")
    (repo / ".project-toolkit" / "sessions" / LOG).write_text(after, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "move")
    return repo


def test_pure_move_is_not_a_changed_log(tmp_path: Path) -> None:
    body = '{"workLog": [' + ", ".join(f'"step {n}"' for n in range(20)) + "]}\n"
    repo = _repo(tmp_path, body, body)

    destinations = checks_tooling._pure_rename_destinations(repo, "main")

    assert destinations == {f".project-toolkit/sessions/{LOG}"}


def test_moved_and_edited_log_stays_changed(tmp_path: Path) -> None:
    body = '{"workLog": [' + ", ".join(f'"step {n}"' for n in range(20)) + "]}\n"
    repo = _repo(tmp_path, body, body.replace("step 3", "edited"))

    assert checks_tooling._pure_rename_destinations(repo, "main") == set()


def test_failed_query_keeps_every_log(tmp_path: Path) -> None:
    assert checks_tooling._pure_rename_destinations(tmp_path, "main") == set()
