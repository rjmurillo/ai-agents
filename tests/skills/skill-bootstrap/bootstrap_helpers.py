"""Shared CLI drivers for the skill-bootstrap tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import bootstrap_boundary
import pytest

ROOT = ".claude/skills"
Result = tuple[int, dict[str, Any]]


def run_git(repo: Path, *args: str) -> str:
    """Run git in `repo` and return stdout, failing the test on a non-zero exit."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> Result:
    """Call main() in process and return the exit code and parsed JSON payload."""
    code = bootstrap_boundary.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def plan(capsys: pytest.CaptureFixture[str], repo: Path, *extra: str, root: str = ROOT) -> Result:
    return run_cli(capsys, "plan", "--repo", str(repo), "--output-root", root, *extra)


def snapshot_result(
    capsys: pytest.CaptureFixture[str], repo: Path, out: Path, *extra: str, root: str = ROOT
) -> Result:
    return run_cli(
        capsys, "snapshot", "--repo", str(repo), "--output-root", root, "--out", str(out), *extra
    )


def take_snapshot(capsys: pytest.CaptureFixture[str], repo: Path, out: Path) -> Path:
    """Take a snapshot that must succeed and return its path."""
    code, _ = snapshot_result(capsys, repo, out)
    assert code == 0
    return out


def verify(
    capsys: pytest.CaptureFixture[str],
    repo: Path,
    snap: Path,
    *extra: str,
    root: str = ROOT,
) -> Result:
    """Run verify; pass `--name x`, `--update x`, `--also-allow p` in `extra`."""
    return run_cli(
        capsys,
        "verify",
        "--repo",
        str(repo),
        "--snapshot",
        str(snap),
        "--output-root",
        root,
        *extra,
    )


def write(repo: Path, rel: str, text: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ignore(repo: Path, pattern: str) -> None:
    """Add a .gitignore entry and commit it, so HEAD stays stable for later snapshots."""
    write(repo, ".gitignore", pattern + "\n")
    run_git(repo, "add", ".gitignore")
    run_git(repo, "commit", "-q", "-m", "chore: ignore")
