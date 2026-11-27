"""Regression tests for uv isolation in ``validate_unused_dependencies``.

Host contention analysis (2026-11-26) found that ``validate_unused_dependencies``
in ``scripts/validation/checks_ci_parity.py`` invoked
``uv run --frozen --extra dev --extra eval python ...`` without ``--isolated``.
Because ``eval`` declares ``openai`` in ``pyproject.toml``, running
``pre_pr.py`` mutated the worktree's ``.venv`` in place and left ``openai``
installed. That caused ``pytest-testmon`` to detect a package-version mismatch
against CI's ``--extra dev`` seed DB and discard selection.

Coverage:
- positive: ``validate_unused_dependencies`` passes ``--isolated`` before
  ``--frozen`` and ``--extra`` flags to ``uv run`` and returns True on exit 0.
- negative: non-zero subprocess exit propagates as False, and a missing script
  in a repo with workflows returns False.
- edge: ``uv run --help`` accepts ``--isolated`` in the local toolchain so the
  flag cannot silently drift from the installed ``uv`` CLI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import checks_ci_parity


def _make_repo(tmp_path: Path, *, include_script: bool = True) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    if include_script:
        script = tmp_path / "scripts" / "validation" / "check_unused_dependencies.py"
        script.parent.mkdir(parents=True)
        script.write_text("# stub\n", encoding="utf-8")
    return tmp_path


def test_validate_unused_dependencies_uses_isolated_uv_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Positive: deptry runs in an isolated uv env so --extra eval never mutates .venv."""
    repo = _make_repo(tmp_path)
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: Any) -> tuple[int, str, str]:
        captured.append(list(cmd))
        return (0, "dependency usage: 0 findings\n", "")

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake_run)

    assert checks_ci_parity.validate_unused_dependencies(repo) is True
    assert len(captured) == 1
    cmd = captured[0]
    expected_prefix = [
        "uv",
        "run",
        "--isolated",
        "--frozen",
        "--extra",
        "dev",
        "--extra",
        "eval",
        "python",
    ]
    assert cmd[: len(expected_prefix)] == expected_prefix
    assert cmd[len(expected_prefix)] == str(
        repo / "scripts" / "validation" / "check_unused_dependencies.py"
    )


def test_validate_unused_dependencies_returns_false_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Negative: a failing isolated deptry invocation returns False."""
    repo = _make_repo(tmp_path)

    def fake_run(cmd: list[str], **_kwargs: Any) -> tuple[int, str, str]:
        return (1, "", "DEP002 unused dependency\n")

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake_run)

    assert checks_ci_parity.validate_unused_dependencies(repo) is False


def test_validate_unused_dependencies_fails_when_script_missing_with_workflows(
    tmp_path: Path,
) -> None:
    """Negative: deleting check_unused_dependencies.py while workflows exist fails closed."""
    repo = _make_repo(tmp_path, include_script=False)
    assert checks_ci_parity.validate_unused_dependencies(repo) is False


def test_uv_run_supports_isolated_flag() -> None:
    """Edge: confirm the installed uv binary supports ``uv run --isolated``."""
    uv_bin = shutil.which("uv")
    assert uv_bin is not None, "uv must be on PATH in this environment"
    result = subprocess.run(
        [uv_bin, "run", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=15,
    )
    assert "--isolated" in result.stdout
