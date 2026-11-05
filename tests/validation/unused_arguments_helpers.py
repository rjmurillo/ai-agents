"""Shared fixtures for the ``check_unused_arguments`` test modules."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from check_unused_arguments import BASELINE_RELPATH, REPO_ROOT, main, scan

BASELINE = REPO_ROOT / BASELINE_RELPATH
SCRIPT = "scripts/validation/check_unused_arguments.py"
UNUSED = "def f(path):\n    return 1\n"
UNUSED_KEY = "scripts/mod.py: ARG001 path"
BASELINE_LINE = re.compile(r"^\S[^:]*\.py: ARG00[1-5] \S+$")


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def make_repo(tmp_path: Path, *, source: str = UNUSED) -> Path:
    """Build a fixture git repo. Its files are staged; the gate reads the index."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "mod.py").write_text(source, encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    return tmp_path


def add_file(repo: Path, relpath: str, source: str) -> Path:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    git(repo, "add", "-A")
    return path


def write_baseline(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "baseline.txt"
    path.write_text("# comment\n\n" + "".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def run_gate(repo: Path, baseline: Path, *extra: str) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline), *extra])


def scan_keys(repo: Path) -> list[str]:
    return scan(repo).keys


def commit(repo: Path, message: str) -> None:
    git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        message,
    )


def commit_baseline(repo: Path, *lines: str) -> Path:
    """Write the default baseline in ``repo``, stage it, and return its path."""
    path = repo / BASELINE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    git(repo, "add", "-A")
    return path


def fake_run(
    real_run: Callable[..., subprocess.CompletedProcess[str]],
    *,
    git: object = None,
    ruff: object = None,
) -> Callable[..., object]:
    """Return a ``subprocess.run`` stand-in that replaces git and/or ruff calls."""

    def run(argv: list[str], *args: object, **kwargs: object) -> object:
        override = git if argv[0] == "git" else ruff
        if override is None:
            return real_run(argv, *args, **kwargs)
        if isinstance(override, BaseException):
            raise override
        return override

    return run
