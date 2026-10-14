"""Tests for ``repair_clone_defaults`` in scripts/bootstrap-vm.sh.

Fresh remote-container clones are often shallow and have no ``origin/HEAD``.
The first blocks ``push-ref-policy``; the second defeats the merge exemption in
``branch-context-policy`` (issue #5288). The bootstrap repairs both, so these
tests run the shipped function verbatim against real temporary repositories.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **_GIT_ENV},
    )
    return result.stdout.strip()


def _extract() -> str:
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
    start = text.index("repair_clone_defaults() {")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    """Run the function under the bootstrap's own ``set -euo pipefail``."""
    script = f"set -euo pipefail\n{_extract()}\nrepair_clone_defaults\necho reached-end\n"
    return subprocess.run(
        ["bash", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, **_GIT_ENV},
    )


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    """A non-bare upstream with three commits on ``main``."""
    path = tmp_path / "upstream"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    for index in range(3):
        (path / "f.txt").write_text(f"{index}\n", encoding="utf-8")
        _git(path, "add", "f.txt")
        _git(path, "commit", "-q", "-m", f"c{index}")
    return path


def _clone(upstream: Path, tmp_path: Path, *extra: str) -> Path:
    dest = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", *extra, upstream.as_uri(), str(dest))
    return dest


def _is_shallow(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--is-shallow-repository") == "true"


def _has_origin_head(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        cwd=repo,
        capture_output=True,
        check=False,
        env={**os.environ, **_GIT_ENV},
    )
    return result.returncode == 0


def _break_origin(repo: Path, tmp_path: Path) -> None:
    _git(repo, "remote", "set-url", "origin", (tmp_path / "gone").as_uri())


def test_unshallows_a_shallow_clone(upstream: Path, tmp_path: Path) -> None:
    clone = _clone(upstream, tmp_path, "--depth", "1")
    assert _is_shallow(clone)

    result = _run(clone)

    assert result.returncode == 0, result.stderr
    assert not _is_shallow(clone)
    assert _git(clone, "rev-list", "--count", "HEAD") == "3"


def test_sets_an_unset_origin_head(upstream: Path, tmp_path: Path) -> None:
    clone = _clone(upstream, tmp_path)
    _git(clone, "remote", "set-head", "origin", "-d")
    assert not _has_origin_head(clone)

    result = _run(clone)

    assert result.returncode == 0, result.stderr
    assert _git(clone, "symbolic-ref", "refs/remotes/origin/HEAD") == "refs/remotes/origin/main"


def test_repairs_both_defaults_in_one_run(upstream: Path, tmp_path: Path) -> None:
    clone = _clone(upstream, tmp_path, "--depth", "1")
    _git(clone, "remote", "set-head", "origin", "-d")

    result = _run(clone)

    assert result.returncode == 0, result.stderr
    assert not _is_shallow(clone)
    assert _has_origin_head(clone)


def test_a_healthy_clone_makes_no_network_call(upstream: Path, tmp_path: Path) -> None:
    """Complete history plus a set origin/HEAD must not touch the remote."""
    clone = _clone(upstream, tmp_path)
    _break_origin(clone, tmp_path)

    result = _run(clone)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "reached-end" in result.stdout


def test_a_failed_unshallow_warns_and_does_not_abort(upstream: Path, tmp_path: Path) -> None:
    clone = _clone(upstream, tmp_path, "--depth", "1")
    _break_origin(clone, tmp_path)

    result = _run(clone)

    assert result.returncode == 0, result.stderr
    assert "WARNING: 'git fetch --unshallow origin' failed" in result.stderr
    assert "reached-end" in result.stdout
    assert _is_shallow(clone)


def test_a_failed_set_head_warns_and_does_not_abort(upstream: Path, tmp_path: Path) -> None:
    clone = _clone(upstream, tmp_path)
    _git(clone, "remote", "set-head", "origin", "-d")
    _break_origin(clone, tmp_path)

    result = _run(clone)

    assert result.returncode == 0, result.stderr
    assert "WARNING: 'git remote set-head origin -a' failed" in result.stderr
    assert "reached-end" in result.stdout
    assert not _has_origin_head(clone)


def test_without_an_origin_remote_it_does_nothing(tmp_path: Path) -> None:
    repo = tmp_path / "no-origin"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    result = _run(repo)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "reached-end" in result.stdout


def test_bootstrap_calls_the_repair_after_origin_is_restored() -> None:
    """The repair needs an origin, so it must run after ``restore_origin_remote``."""
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
    restore_call = text.index("\nrestore_origin_remote\n")
    repair_call = text.index("\nrepair_clone_defaults\n")

    assert restore_call < repair_call
    assert repair_call < text.index('echo "=== Python uv ==="')
