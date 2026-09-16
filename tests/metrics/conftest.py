"""Shared fixtures for the gate_latency test modules (REQ-027).

These lived in test_gate_latency.py while it was one module. Splitting that
module to mirror the source layout would have copied the block three times,
so it moves here instead: pytest collects a conftest for every sibling
module, and the captured lefthook output below has exactly one definition.

Every captured string here is real output from this repository's own hooks or
from a disposable negative control, never invented.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.metrics.gate_latency_classes import CHANGE_CLASSES
from tests.gc_real_git import git

# --- Fixtures ---------------------------------------------------------------

_DIVIDER = "\x1b[38;2;56;56;56m" + "─" * 40 + "\x1b[0m"

# Real captured output, this session: `.venv/bin/lefthook run pre-merge-commit
# --no-tty --colors off --force --no-stage-fixed` against this repository's own
# lefthook.yml. A divider line carries a truecolor escape that --colors off
# does not strip; the summary line and job line follow. The pass marker is
# bare U+2713, not the U+2714 U+FE0F an earlier draft of this module assumed
# on the strength of an unverified claim (see lefthook_summary.py's module
# docstring for both captures and the correction).
REAL_CAPTURED_STDOUT = (
    f"{_DIVIDER}\n"
    "summary: (done in 0.20 seconds)\n"
    "✓ security-suppressions-staged (0.20 seconds)\n"
)

# Real captured output, this session, from a disposable throwaway repo (never
# committed to this repository) whose pre-commit hook declared one job that
# exits 0 and one that exits 1: `✓` for the pass, `✗` for the fail.
NEGATIVE_CONTROL_STDOUT = (
    "summary: (done in 0.01 seconds)\n"
    "✓ good-job (0.00 seconds)\n"
    "✗ bad-job (0.00 seconds)\n"
)

# Not observed in this environment (see lefthook_summary.py's module
# docstring): U+2714 with the emoji-style variation selector, a documented
# synonym this module accepts defensively. Tests classification robustness,
# not a ground-truth capture.
UNVERIFIED_SYNONYM_MARKER_STDOUT = (
    "summary: (done in 0.05 seconds)\n"
    "✔️ some-other-job (0.05 seconds)\n"
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
    for rel in CHANGE_CLASSES.values():
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


def _dispatching_fake(
    responses: dict[tuple[str, ...], _FakeCompleted],
    default_git: _FakeCompleted | None = None,
) -> object:
    """A ``subprocess.run`` fake dispatched on argv, per testing.md SHOULD-11."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        key = tuple(cmd)
        if key in responses:
            return responses[key]
        if cmd and cmd[0] == "git" and default_git is not None:
            return default_git
        raise AssertionError(f"unstubbed subprocess call: {cmd!r}")

    return _fake


def expected_lefthook_cmd(
    hook: str, *, lefthook_cmd: tuple[str, ...] = ("lefthook",), files: tuple[str, ...] = ()
) -> tuple[str, ...]:
    """The argument vector _run_repetition builds for a natural (unforced) run.

    One definition, because three tests asserted the same vector and a change
    to the flag set would otherwise have to be made in each of them.
    """
    file_args: tuple[str, ...] = ()
    for rel in files:
        file_args += ("--file", rel)
    return (
        *lefthook_cmd,
        "run",
        hook,
        "--no-tty",
        "--colors",
        "off",
        "--no-stage-fixed",
        *file_args,
    )


def stub_lefthook(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    *,
    porcelain: Callable[[int], str] | None = None,
) -> None:
    """Route git calls to a stub and every other call to one lefthook stdout.

    Five tests repeated this patch-and-dispatch block with only the stdout and
    the porcelain sequence differing, which is the redundancy the
    code-qualities axis scores. The tests keep their own distinct assertions;
    only the setup is shared.

    ``porcelain`` receives the 1-based ``git status`` call index and returns
    that call's output, which is how a test drives ``tree_mutated`` without
    writing its own dispatcher.
    """
    calls = {"status": 0}

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd[:2] == ["git", "status"]:
            calls["status"] += 1
            return _FakeCompleted(0, "" if porcelain is None else porcelain(calls["status"]))
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        return _FakeCompleted(0, stdout)

    monkeypatch.setattr(subprocess, "run", _fake)


def stub_lefthook_expecting(
    monkeypatch: pytest.MonkeyPatch, expected_cmd: tuple[str, ...], stdout: str
) -> None:
    """Stub lefthook for exactly one argument vector, failing loudly on any other.

    The dispatch-on-argv shape testing.md SHOULD-11 asks for: an unstubbed
    command raises a named AssertionError instead of silently borrowing another
    call's response. Shared because two tests need the same setup and differ
    only in what they assert afterwards.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        _dispatching_fake(
            {expected_cmd: _FakeCompleted(0, stdout)},
            default_git=_FakeCompleted(0, ""),
        ),
    )

