"""Shared fixtures for the dispatch closure tests (scripts/ci/verify_dispatch_closure.py)."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.ci import verify_dispatch_closure as vdc  # noqa: E402

GATE = vdc.GATE
CONFIG = vdc.CONFIG
VERIFIER = ".claude/skills/demo/scripts/verify.py"
HELPER = ".claude/skills/demo/scripts/helper.py"


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )


def write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def run(trees: tuple[Path, Path]) -> vdc.Report:
    base, head = trees
    return vdc.verify(base, head, "HEAD")


def rev(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def upstream_with_pr(base: Path, edit: dict[str, str], attributes: str = "") -> tuple[Path, str]:
    """A repository holding the base history plus one commit at refs/pull/1/head."""
    upstream = base.parent / "upstream"
    subprocess.run(
        ["git", "clone", "-q", str(base), str(upstream)], capture_output=True, check=True
    )
    git(upstream, "config", "user.email", "t@example.invalid")
    git(upstream, "config", "user.name", "t")
    for relative, body in edit.items():
        write(upstream, relative, body)
    if attributes:
        (upstream / ".gitattributes").write_text(attributes, encoding="utf-8")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "pull request")
    sha = rev(upstream)
    git(upstream, "update-ref", "refs/pull/1/head", sha)
    return upstream, sha
