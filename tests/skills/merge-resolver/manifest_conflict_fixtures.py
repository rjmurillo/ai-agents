"""Real git merge-conflict fixtures for the plugin manifest resolver tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


MANIFEST = ".claude-plugin/plugin.json"


def make_manifest_conflict(
    repo: Path,
    base: str,
    ours: str,
    theirs: str,
    rel: str = MANIFEST,
) -> None:
    """Create a real merge conflict on the plugin manifest in a tmp repo.

    ``ours`` is the PR-branch content (checked out), ``theirs`` is the
    target-branch content being merged in, matching the resolver's merge
    direction (merge main into the PR branch).
    """
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    # Hermetic: a host-level commit.gpgsign with an unreachable signer would
    # fail every fixture commit and dissolve the conflict under test.
    git(repo, "config", "commit.gpgsign", "false")
    manifest = repo / rel
    manifest.parent.mkdir(parents=True)
    manifest.write_text(base, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")
    git(repo, "checkout", "-b", "pr")
    manifest.write_text(ours, encoding="utf-8")
    git(repo, "commit", "-am", "ours")
    git(repo, "checkout", "main")
    manifest.write_text(theirs, encoding="utf-8")
    git(repo, "commit", "-am", "theirs")
    git(repo, "checkout", "pr")
    merge = git(repo, "merge", "main")
    assert merge.returncode != 0, "expected a merge conflict"


def manifest_json(version: str, description: str = "toolkit") -> str:
    return (
        '{\n  "name": "project-toolkit",\n'
        f'  "description": "{description}",\n'
        f'  "version": "{version}"\n}}\n'
    )


def versionless_manifest_json(description: str = "toolkit") -> str:
    """The post-ADR-092 manifest shape: same keys, no version field."""
    return f'{{\n  "name": "project-toolkit",\n  "description": "{description}"\n}}\n'
