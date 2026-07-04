"""Tests for get_staged_files git-enumeration error handling (issue #2807).

The scanner enumerates staged files via `git diff --staged --name-only`. When
that enumeration fails, get_staged_files MUST fail closed: return [] so the
caller (_collect_files_to_scan) prints "No files to scan" and exits EXIT_ERROR,
and emit a distinct stderr diagnostic instead of a raw traceback.

Canonical source mirrored by these tests:
`.claude/skills/security-scan/scripts/scan_vulnerabilities.py::get_staged_files`
(byte-identical mirror at
`src/copilot-cli/skills/security-scan/scripts/scan_vulnerabilities.py`). Loaded
by path, matching the loader in tests/test_security_scan_vulnerabilities.py; the
scanner imports only stdlib, so a path-based load is safe.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNER_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "security-scan"
    / "scripts"
    / "scan_vulnerabilities.py"
)


def _load_scanner() -> ModuleType:
    """Load the scanner module by path (it is not on the package tree)."""
    spec = importlib.util.spec_from_file_location(
        "scan_vulnerabilities_git_enum", SCANNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def test_get_staged_files_returns_filenames_from_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Happy path plus the blank-line edge: trailing empty entries are dropped.
    class _Result:
        stdout = "a.py\nb.py\n\n"

    monkeypatch.setattr(scanner.subprocess, "run", lambda *a, **k: _Result())
    assert scanner.get_staged_files() == ["a.py", "b.py"]


def test_get_staged_files_git_missing_returns_empty_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # git binary absent: FileNotFoundError must be caught, a distinct diagnostic
    # emitted, and [] returned so the caller fails closed (exits EXIT_ERROR).
    def _raise_not_found(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(scanner.subprocess, "run", _raise_not_found)
    result = scanner.get_staged_files()
    captured = capsys.readouterr()
    assert result == []
    assert "git executable not found" in captured.err


def test_get_staged_files_git_nonzero_returns_empty_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # git ran but exited non-zero: CalledProcessError must be reported and []
    # returned (fail-closed), not a raw traceback.
    def _raise_called_process(*_args: object, **_kwargs: object) -> object:
        raise subprocess.CalledProcessError(1, ["git", "diff", "--staged"])

    monkeypatch.setattr(scanner.subprocess, "run", _raise_called_process)
    result = scanner.get_staged_files()
    captured = capsys.readouterr()
    assert result == []
    assert "git staged-file enumeration failed" in captured.err
