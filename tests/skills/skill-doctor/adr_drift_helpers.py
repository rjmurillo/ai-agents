"""Fixture repositories and a CLI runner for the adr_drift tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import adr_drift
import pytest

ADR_DIR = ".project-toolkit/architecture"


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={**os.environ, **env} if env else None,
    )
    return proc.stdout.strip()


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "commit.gpgsign", "false")
    return path


def commit(repo: Path, files: dict[str, str | None], message: str, date: str | None = None) -> str:
    """Write (or delete, for None) files, commit them, and return the full SHA."""
    for rel, text in files.items():
        target = repo / rel
        if text is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else None
    git(repo, "commit", "-q", "-m", message, env=env)
    return git(repo, "rev-parse", "HEAD")


def adr_text(
    number: int,
    title: str = "Decision",
    status: str = "accepted",
    body: str = "",
    frontmatter: str = "",
    h1: str | None = None,
) -> str:
    heading = h1 if h1 is not None else f"# ADR-{number:03d}: {title}"
    return (
        f"---\nid: ADR-{number:03d}\nstatus: {status}\ndate: 2025-01-01\n"
        f"supersedes: []\nsuperseded-by: null\n{frontmatter}---\n\n"
        f"{heading}\n\n## Status\n\n{status}\n\n## Context\n\n{body}\n\n## Decision\n\nDone.\n"
    )


def adr_path(number: int, slug: str = "decision") -> str:
    return f"{ADR_DIR}/ADR-{number:03d}-{slug}.md"


def seeded_repo(path: Path, adrs: dict[str, str] | None = None) -> Path:
    """A repo with one initial commit holding the given ADR files (rel path to text)."""
    repo = init_repo(path)
    files = adrs if adrs is not None else {adr_path(1): adr_text(1)}
    commit(repo, {**files}, "docs: seed")
    return repo


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = adr_drift.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def scan(
    capsys: pytest.CaptureFixture[str], repo: Path, *extra: str, name: str = "scan.json"
) -> dict[str, Any]:
    """Run `scan` into a file beside the repo and return the parsed result."""
    out = repo.parent / "out" / name
    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out), *extra)
    assert code == 0, err
    result: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return result


def kinds(result: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [f for f in result["findings"] if f["kind"] == kind]


def symlink_or_skip(link: Path, target: Path) -> None:
    """Create a file or directory symlink, or skip where the platform denies symlinks."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
