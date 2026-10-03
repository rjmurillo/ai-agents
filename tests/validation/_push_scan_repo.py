"""Shared repository scaffolding for the pre-push infrastructure scan suites (issue #6076).

Each suite drives ``git_hook_policy.main(["pre-push"])`` against a real clone
of a local bare ``origin``, so the hook's own ``git fetch`` runs for real.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR = ".claude/skills/security-detection/detect_infrastructure.py"
MARKER_VALIDATOR = "scripts/validation/validate_review_marker.py"
REVIEW_REFERENCES = ".claude/skills/review/references"
ZERO = "0" * 40
WORKFLOW = ".github/workflows/ci.yml"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # subprocess-encoding: strict-ok
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def configure(repo: Path, hooks: Path) -> None:
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "user@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "core.hooksPath", str(hooks))


def commit(repo: Path, relative_path: str, content: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    git(repo, "add", "--", relative_path)
    git(repo, "commit", "-qm", f"test: {relative_path}")
    return git(repo, "rev-parse", "HEAD")


def marker(repo: Path) -> str:
    parent = git(repo, "rev-parse", "HEAD")
    git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: /review PASS marker",
        "--trailer",
        f"Reviewed-By: /review@analyst,security on {parent}",
    )
    return git(repo, "rev-parse", "HEAD")


def install_scripts(repo: Path, *, detector: bool = True) -> None:
    """Place the scripts and review axis prompts the hook reads, untracked."""
    names = [MARKER_VALIDATOR, *([DETECTOR] if detector else [])]
    for name in names:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, target)
    shutil.copytree(REPO_ROOT / REVIEW_REFERENCES, repo / REVIEW_REFERENCES, dirs_exist_ok=True)
    exclude = repo / ".git/info/exclude"
    exclude.write_text("scripts/\n.claude/\n", encoding="utf-8")


class Origin:
    """A bare ``origin`` plus a seed clone that advances ``main`` on it."""

    def __init__(self, tmp_path: Path) -> None:
        self.hooks = tmp_path / "no-hooks"
        self.hooks.mkdir()
        self.bare = tmp_path / "origin.git"
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(self.bare)],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        self.seed = tmp_path / "seed"
        self.clone(self.seed)
        commit(self.seed, "README.md", "base\n")
        git(self.seed, "push", "-q", "origin", "HEAD:main")

    def clone(self, target: Path) -> Path:
        subprocess.run(
            ["git", "clone", "-q", str(self.bare), str(target)],
            check=True,
            capture_output=True,
        )
        configure(target, self.hooks)
        return target

    def advance_main(self, relative_path: str) -> str:
        git(self.seed, "pull", "-q", "--ff-only", "origin", "main")
        sha = commit(self.seed, relative_path, f"{relative_path}\n")
        git(self.seed, "push", "-q", "origin", "HEAD:main")
        return sha


def work_clone(origin: Origin, tmp_path: Path, *, detector: bool = True) -> Path:
    work = origin.clone(tmp_path / "work")
    install_scripts(work, detector=detector)
    return work


def pre_push(repo: Path, payload: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    return policy.main(["--repo-root", str(repo), "pre-push"])


def new_branch_line(branch: str, sha: str) -> str:
    return f"refs/heads/{branch} {sha} refs/heads/{branch} {ZERO}\n"
