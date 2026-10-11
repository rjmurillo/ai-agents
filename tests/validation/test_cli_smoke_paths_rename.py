"""Rename handling of the CLI smoke path filter, against a real git repository.

Rename detection lists only the new path. Moving a smoke path out of the filter
would then skip the smoke, so both sides of a rename must be listed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation import cli_smoke_paths as paths

_OLD = "src/claude/skills/x/SKILL.md"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_rename_out_of_a_smoke_path_still_matches_the_old_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src/claude/skills/x").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / _OLD).write_text("skill body that is long enough to be detected as a rename\n" * 5)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", _OLD, "docs/x.md")
    _git(repo, "commit", "-q", "-m", "move")
    head = _git(repo, "rev-parse", "HEAD")

    changed = paths.changed_files(base, head, repo)

    assert _OLD in changed
    assert "docs/x.md" in changed
    assert paths.matched_paths(changed) == [_OLD]
