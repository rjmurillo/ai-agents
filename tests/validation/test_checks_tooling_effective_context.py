"""Tests for the pre-PR path-local ratchet gate (issue #4880, REQ-6).

The gate calls ``effective_context.main`` in-process. An import edge, unlike
a ``python -m`` string, is one the script reachability guard can follow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context as ec
from scripts.validation import checks_tooling
from scripts.validation.checks_tooling import validate_effective_context_ratchet


def test_skips_when_the_module_is_absent(tmp_path: Path) -> None:
    """REQ-6: a downstream install without the module reports SKIP, not FAIL."""
    with pytest.raises(checks_tooling.MissingScriptSkip):
        validate_effective_context_ratchet(tmp_path)


@pytest.mark.parametrize(("exit_code", "expected"), [(0, True), (1, False), (3, False)])
def test_maps_the_ci_exit_code(
    monkeypatch: pytest.MonkeyPatch, exit_code: int, expected: bool
) -> None:
    """REQ-6: the gate passes only when ``--ci`` exits 0, and runs against ``repo_root``."""
    calls: list[tuple[list[str] | None, Path | None]] = []

    def _fake_main(argv: list[str] | None = None, *, repo_root: Path | None = None) -> int:
        calls.append((argv, repo_root))
        return exit_code

    monkeypatch.setattr(ec, "main", _fake_main)
    assert validate_effective_context_ratchet(REPO_ROOT) is expected
    assert calls == [(["--ci"], REPO_ROOT)]


def test_real_repository_passes_the_gate() -> None:
    """REQ-6: the committed ceilings hold for this repository."""
    assert validate_effective_context_ratchet(REPO_ROOT) is True
