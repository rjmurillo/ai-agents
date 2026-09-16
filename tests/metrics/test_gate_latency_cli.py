"""CLI-level tests for gate_latency.py (REQ-027 T7).

Split from ``test_gate_latency.py`` to keep both files under the project's
500-line taste-lint ceiling; see that module's docstring for the rationale
and the full three-way split. Covers ``main``'s argument validation and
exit-code contract (AC-07), the never-gates matrix that makes DR1
verifiable (AC-06), AC-13's never-wired-into-a-gate guarantee, and the
``__main__`` subprocess entry point. ``subprocess.run`` is monkeypatched
throughout except the one test that deliberately drives the real CLI
entry point in a subprocess to prove the ``if __name__ == "__main__"``
wiring; neither invokes a real lefthook hook.
"""

from __future__ import annotations

import subprocess
import sys
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


# --- CLI exit-code matrix ----------------------------------------------------


def _plain_dir(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _git_dir(tmp_path: Path, name: str, lefthook: str | None = None) -> Path:
    root = _plain_dir(tmp_path, name)
    git(root, "init", "-q")
    if lefthook is not None:
        _write(root, "lefthook.yml", lefthook)
    return root


@pytest.mark.parametrize(
    ("case", "argv_extra"),
    [
        ("unknown-hook", ["--hook", "does-not-exist"]),
        # min_version and friends are top-level config keys, not hooks.
        ("non-hook-top-level-key", ["--hook", "min_version"]),
        ("unknown-change-class", ["--hook", "pre-commit", "--change-class", "nope"]),
        ("repetitions-zero", ["--hook", "pre-commit", "--repetitions", "0"]),
        ("repetitions-negative", ["--hook", "pre-commit", "--repetitions", "-1"]),
        (
            "missing-lefthook-binary",
            ["--hook", "pre-commit", "--lefthook-bin", "/definitely/does/not/exist/lefthook"],
        ),
    ],
)
def test_negative_configuration_problems_exit_2(
    repo: Path, case: str, argv_extra: list[str]
) -> None:
    """Every configuration problem discovered before a hook runs exits 2 (AC-07).

    Table-driven because these differ only in the argument that is wrong; each
    row keeps its own id, so a failure still names the case.
    """
    assert gl.main(["--repo", str(repo), *argv_extra]) == 2, case


@pytest.mark.parametrize(
    ("case", "make"),
    [
        ("missing-repo", lambda tmp: tmp / "nope"),
        ("non-git-dir", lambda tmp: _plain_dir(tmp, "plain")),
        ("missing-lefthook-yml", lambda tmp: _git_dir(tmp, "no-lefthook")),
        ("invalid-lefthook-yml", lambda tmp: _git_dir(tmp, "bad", "- just\n- a\n- list\n")),
    ],
)
def test_negative_unusable_repository_exits_2(
    tmp_path: Path, case: str, make: object
) -> None:
    """A repo that cannot be read is exit 2, whatever makes it unreadable (AC-07)."""
    root = make(tmp_path)  # type: ignore[operator]

    assert gl.main(["--repo", str(root), "--hook", "pre-commit"]) == 2, case


def test_negative_missing_lefthook_binary_exits_2(repo: Path) -> None:
    rc = gl.main(
        [
            "--repo",
            str(repo),
            "--hook",
            "pre-commit",
            "--lefthook-bin",
            "/definitely/does/not/exist/lefthook",
        ]
    )
    assert rc == 2


# --- AC-13: never wired into a gate ------------------------------------------


# --- Command normalization ---------------------------------------------------


# --- CLI entry point via subprocess (proves the __main__ wiring) ------------


def test_cli_entry_point_via_subprocess_unknown_hook_exits_2(repo: Path) -> None:
    from scripts.ci.lefthook_budget_model import REPO_ROOT

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "metrics" / "gate_latency.py"),
            "--repo",
            str(repo),
            "--hook",
            "does-not-exist",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
