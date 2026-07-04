"""Subprocess timeout hardening, PR-B slice (issue #2811).

Wrappers that callers drive by returncode must convert a hung subprocess
into a synthetic nonzero result (exit 124) rather than raising, and the
merge-resolver must reject dash-leading refs before handing them to git.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[1]


def _import_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_resolver = _import_script(
    "resolve_pr_conflicts",
    _REPO / ".claude" / "skills" / "merge-resolver" / "scripts" / "resolve_pr_conflicts.py",
)

import scripts.invoke_batch_pr_review as batch  # noqa: E402
import scripts.invoke_session_start_gate as gate  # noqa: E402


def test_resolver_run_git_timeout_returns_synthetic_124() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=60)
    with patch("subprocess.run", side_effect=timeout):
        result = _resolver._run_git("fetch", "origin", "main")
    assert result.returncode == 124
    assert "timed out" in result.stderr


def test_resolver_rejects_dash_leading_branch() -> None:
    result = _resolver.resolve_conflicts_runner("--upload-pack=evil", "main")
    assert result["success"] is False
    assert "Invalid ref" in result["message"]


def test_resolver_rejects_dash_leading_target() -> None:
    result = _resolver.resolve_conflicts_runner("feature/x", "-otherflag")
    assert result["success"] is False
    assert "Invalid ref" in result["message"]


def test_batch_run_git_timeout_returns_synthetic_124() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=30)
    with patch("subprocess.run", side_effect=timeout):
        result = batch.run_git("fetch", "origin")
    assert result.returncode == 124


def test_batch_run_gh_timeout_returns_synthetic_124() -> None:
    timeout = subprocess.TimeoutExpired(cmd="gh", timeout=60)
    with patch("subprocess.run", side_effect=timeout):
        result = batch.run_gh("pr", "view", "1")
    assert result.returncode == 124


def test_gate_run_git_timeout_returns_synthetic_124() -> None:
    timeout = subprocess.TimeoutExpired(cmd="git", timeout=10)
    with patch("subprocess.run", side_effect=timeout):
        result = gate.run_git("rev-parse", "HEAD")
    assert result.returncode == 124
