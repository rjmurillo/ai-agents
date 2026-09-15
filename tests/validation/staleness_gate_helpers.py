"""Shared stubs and fixtures for the generated-staleness gate tests.

Split out when round-5 coverage pushed ``test_check_generated_staleness.py``
past the 500-line test file-size ceiling: the termination and budget tests
now live in ``test_check_generated_staleness_termination.py``, and both
modules build their fake repositories and env hygiene from here so the
knowledge exists once (`.claude/rules/pragmatic-programmer.md`, DRY).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend
# ``scripts/validation`` to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_generated_staleness

__all__ = [
    "REPO_ROOT",
    "build_all_invoked_with_check",
    "build_all_ran",
    "check_generated_staleness",
    "fake_repo",
    "no_ambient_outer_cap",
    "stub",
]


@pytest.fixture(autouse=True)
def no_ambient_outer_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer shell exporting the clamp variable must not skew tests
    that reason about the unclamped aggregate budget. Autouse in every
    module that imports it by name."""
    monkeypatch.delenv(check_generated_staleness._OUTER_CAP_ENV, raising=False)


def stub(path: Path, body: str) -> None:
    """Write an executable-by-interpreter stub at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"import sys\n{body}\n", encoding="utf-8")


def fake_repo(tmp_path: Path, build_exit: int) -> Path:
    """A root holding a stub at the one real script path the gate invokes.

    ADR-109 B5: the gate used to run `scripts/sync_plugin_lib.py --check`
    before `build_all.py --check`, two scripts whose order mattered. B5
    folded the first hop into `build_all.py`'s own lib step, so the gate
    now runs one child.
    """
    stub(
        tmp_path / "build" / "scripts" / "build_all.py",
        "from pathlib import Path\n"
        # Records the argv it was actually invoked with, not just "ran",
        # so a test can assert --check was really passed through rather
        # than trusting the child's --check-labeled diagnostic name alone
        # (CodeRabbit, PR #5787 review: a stub that always exits 0
        # regardless of its arguments would make a dropped --check flag,
        # which lets the staleness gate run build_all.py in write mode,
        # invisible to this suite).
        "Path(__file__).with_name('build_all_ran.marker')"
        ".write_text(' '.join(sys.argv[1:]))\n"
        f"sys.exit({build_exit})",
    )
    return tmp_path


def build_all_ran(repo_root: Path) -> bool:
    return (repo_root / "build" / "scripts" / "build_all_ran.marker").is_file()


def build_all_invoked_with_check(repo_root: Path) -> bool:
    """Return whether the recorded invocation's argv contains --check."""
    marker = repo_root / "build" / "scripts" / "build_all_ran.marker"
    if not marker.is_file():
        return False
    return "--check" in marker.read_text(encoding="utf-8").split()
