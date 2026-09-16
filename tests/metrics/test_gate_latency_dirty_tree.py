"""The working-tree precondition (REQ-027 AC-07).

A measurement taken over a dirty tree describes a tree nobody else has, so the
sampler refuses one with exit 1 unless the caller says --allow-dirty. Both
directions are here: the refusal, and the proceed that proves the flag is what
lifts it rather than the check being absent.

Split from test_gate_latency_cli.py, which held this alongside the exit-2
configuration matrix.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.metrics import gate_latency as gl
from tests.gc_real_git import git

_DIVIDER = "\x1b[38;2;56;56;56m" + "─" * 40 + "\x1b[0m"

# Real captured output, this session (see test_gate_latency.py's fixture of
# the same name for the full provenance note).
REAL_CAPTURED_STDOUT = (
    f"{_DIVIDER}\n"
    "summary: (done in 0.20 seconds)\n"
    "✓ security-suppressions-staged (0.20 seconds)\n"
)

_LEFTHOOK_YML = """\
pre-commit:
  piped: true
  jobs:
    - name: job-a
      run: echo a
      timeout: 10s
    - name: job-b
      run: echo b
      timeout: 5s
pre-push:
  piped: true
  jobs:
    - name: job-c
      group:
        parallel: true
        jobs:
          - name: job-c1
            run: echo c1
            timeout: 20s
          - name: job-c2
            run: echo c2
            timeout: 30s
"""


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small git repo with a real lefthook.yml and every change-class path."""
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    _write(root, "lefthook.yml", _LEFTHOOK_YML)
    for rel in gl.CHANGE_CLASSES.values():
        for path in rel:
            _write(root, path, "placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- Never-gates matrix (AC-06, AC-07, DR1) ----------------------------------


def test_negative_dirty_tree_without_allow_dirty_exits_1(repo: Path) -> None:
    _write(repo, "dirty.txt", "uncommitted\n")
    assert gl.main(["--repo", str(repo), "--hook", "pre-commit", "--repetitions", "1"]) == 1


def test_positive_dirty_tree_with_allow_dirty_proceeds(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    _write(repo, "dirty.txt", "uncommitted\n")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: (
            _FakeCompleted(0, " M dirty.txt\n")
            if cmd[:2] == ["git", "status"]
            else _FakeCompleted(0, REAL_CAPTURED_STDOUT)
        ),
    )
    rc = gl.main(
        ["--repo", str(repo), "--hook", "pre-commit", "--repetitions", "1", "--allow-dirty"]
    )
    assert rc == 0

