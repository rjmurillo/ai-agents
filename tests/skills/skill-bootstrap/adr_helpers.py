"""Fixtures and runners shared by the ADR backfill tests (not collected by pytest)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_SKILL = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-bootstrap"
SKILL_SCRIPTS = _SKILL / "scripts"
CLI = SKILL_SCRIPTS / "bootstrap_adr.py"

_BASE_ENV = {
    "GIT_AUTHOR_NAME": "Ada",
    "GIT_AUTHOR_EMAIL": "ada@example.com",
    "GIT_COMMITTER_NAME": "Ada",
    "GIT_COMMITTER_EMAIL": "ada@example.com",
}


def git(repo: Path, *args: str, date: str | None = None, stdin: str | None = None) -> str:
    """Run git in ``repo`` with a fixed identity and no signing. Fails the test on error."""
    env = {**os.environ, **_BASE_ENV}
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        input=stdin,
        check=True,
        env=env,
    )
    return proc.stdout


def hash_commit(repo: Path, raw: str) -> str:
    """Write ``raw`` as a commit object with ``hash-object --literally``, as bytes."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-t", "commit", "-w", "--literally", "--stdin"],
        input=raw.encode("utf-8"),
        capture_output=True,
        check=True,
        env={**os.environ, **_BASE_ENV},
    )
    return proc.stdout.decode("ascii").strip()


def new_repo(path: Path) -> Path:
    """An empty repository on branch ``main``."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    return path.resolve()


def write(repo: Path, rel: str, text: str) -> Path:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def commit(
    repo: Path,
    message: str,
    rel: str = "f.txt",
    text: str | None = None,
    date: str = "2026-01-02T03:04:05+00:00",
) -> str:
    """Write a file, commit it with ``message`` and return the new SHA."""
    existing = (repo / rel).read_text(encoding="utf-8") if (repo / rel).exists() else ""
    write(repo, rel, text if text is not None else existing + f"{message}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty-message", "-F", "-", date=date, stdin=message)
    return git(repo, "rev-parse", "HEAD").strip()


def run_cli(
    *args: str, cwd: Path | None = None, env: dict[str, str] | None = None, script: Path = CLI
) -> tuple[int, dict[str, Any]]:
    """Run ``bootstrap_adr.py`` as a subprocess; return the exit code and the JSON it printed."""
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(f"not JSON: stdout={proc.stdout!r} stderr={proc.stderr!r}") from None
    return proc.returncode, payload
