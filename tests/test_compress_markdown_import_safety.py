"""Regression tests for compress_markdown_content import safety (Issue #2524).

The module guarded its tiktoken import with a module-level ``sys.exit(4)``.
Importing it without tiktoken (a partial dev environment, a vendored install)
crashed pytest collection with ``INTERNALERROR ... SystemExit: 4`` and aborted
the whole ``tests/`` run. The dependency check now lives in ``main()`` (the CLI
entry point), so the module imports cleanly and only the CLI exits 4.

The import-without-tiktoken case runs in a subprocess so the assertion exercises
a real fresh interpreter and cannot pollute this process's module cache.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "scripts"
)
sys.path.insert(0, str(_SCRIPTS_DIR))

import compress_markdown_content as cmc  # noqa: E402

# Block tiktoken (sys.modules[name] = None makes ``import tiktoken`` raise
# ImportError), then import the module. Exit 0 means import is side-effect free.
_IMPORT_PROBE = (
    "import sys; sys.modules['tiktoken'] = None; "
    f"sys.path.insert(0, {str(_SCRIPTS_DIR)!r}); "
    "import compress_markdown_content as m; "
    "assert m._tiktoken_missing() is True; "
    "assert callable(m.remove_redundant_words)"
)

# Negative control: if the import guard still exited at module load, this probe
# (which forces the ImportError branch and then calls sys.exit(4)) would exit 4.
_LEGACY_BAD_PROBE = (
    "import sys; sys.exit(4)"
)


def _run_probe(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_import_without_tiktoken_exits_zero() -> None:
    # Act
    result = _run_probe(_IMPORT_PROBE)
    # Assert: clean import, no SystemExit, public symbol resolves.
    assert result.returncode == 0, result.stderr


def test_probe_harness_detects_an_exit_4() -> None:
    # Negative control proving the harness would catch a regressed import guard.
    result = _run_probe(_LEGACY_BAD_PROBE)
    assert result.returncode == 4


def test_main_exits_4_when_tiktoken_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: the CLI must still honor the exit-4 contract for the missing dep.
    # monkeypatch.setattr auto-restores the seam after the test.
    monkeypatch.setattr(cmc, "_tiktoken_missing", lambda: True)
    monkeypatch.setattr(sys, "argv", ["compress_markdown_content.py", "-i", "x.md"])
    # Act / Assert
    with pytest.raises(SystemExit) as exc_info:
        cmc.main()
    assert exc_info.value.code == 4


def test_main_exit_4_precedes_argument_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: with tiktoken missing, the dependency gate fires before argparse,
    # so even an otherwise-invalid CLI invocation exits 4, not 2 (argparse).
    monkeypatch.setattr(cmc, "_tiktoken_missing", lambda: True)
    monkeypatch.setattr(sys, "argv", ["compress_markdown_content.py"])  # no -i
    # Act / Assert
    with pytest.raises(SystemExit) as exc_info:
        cmc.main()
    assert exc_info.value.code == 4
