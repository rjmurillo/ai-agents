"""Tests for scripts/validation/validate_sync_registry.py (Issue #1909).

Pins behaviour of the sync-registry provenance gate:

- pos: a tree whose lib packages and source roots are all registered passes
- neg: a `.claude/lib/` package with no SYNC_PAIRS destination fails (exit 1)
- neg: a source-root child package not registered as a SYNC_PAIRS source fails
- edge: an allowlisted lib package passes; `__pycache__` and non-package dirs
  are ignored; a missing repo root returns exit 2 (config error per ADR-035)
- integration: the real repo tree passes with the real SYNC_PAIRS
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "validate_sync_registry.py"

# Make the module importable for the unit tests that call find_unregistered
# directly. The script also self-inserts scripts/ on import to reach
# sync_plugin_lib.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import validate_sync_registry as vsr  # noqa: E402


def _make_package(parent: Path, name: str) -> Path:
    """Create a Python package directory (with __init__.py) under parent."""
    pkg = parent / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    return pkg


# ---- positive ----------------------------------------------------------------


def test_all_registered_passes(tmp_path: Path) -> None:
    """Lib packages and source roots all registered -> no errors."""
    _make_package(tmp_path / "scripts", "github_core")
    _make_package(tmp_path / "scripts", "hook_utilities")
    _make_package(tmp_path / ".claude" / "lib", "github_core")
    _make_package(tmp_path / ".claude" / "lib", "hook_utilities")
    sync_pairs = [
        ("scripts/github_core", ".claude/lib/github_core"),
        ("scripts/hook_utilities", ".claude/lib/hook_utilities"),
    ]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert errors == [], errors


# ---- negative ----------------------------------------------------------------


def test_unregistered_lib_package_fails(tmp_path: Path) -> None:
    """A `.claude/lib/` package with no destination produces an error."""
    _make_package(tmp_path / "scripts", "github_core")
    _make_package(tmp_path / ".claude" / "lib", "github_core")
    # newpkg is synced into lib but never registered as a destination.
    _make_package(tmp_path / ".claude" / "lib", "newpkg")
    sync_pairs = [("scripts/github_core", ".claude/lib/github_core")]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert any(".claude/lib/newpkg" in e for e in errors), errors


def test_unregistered_source_child_fails(tmp_path: Path) -> None:
    """A sub-package under a source root not in SYNC_PAIRS produces an error."""
    root = _make_package(tmp_path / "scripts", "github_core")
    # A nested package added later but never registered.
    _make_package(root, "nested")
    sync_pairs = [("scripts/github_core", ".claude/lib/github_core")]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert any("scripts/github_core/nested" in e for e in errors), errors


def test_unregistered_ai_review_common_child_fails(tmp_path: Path) -> None:
    """A sub-package under scripts/ai_review_common not in SYNC_PAIRS fails.

    Guards the Issue #1909 provenance gap: ai_review_common is a synced source
    root, so a nested package added beneath it must be registered too. Sync is
    non-recursive, so an unregistered subpackage would otherwise only surface as
    an install-time import error.
    """
    root = _make_package(tmp_path / "scripts", "ai_review_common")
    _make_package(root, "cache_guard")
    sync_pairs = [
        ("scripts/ai_review_common", ".claude/lib/ai_review_common"),
    ]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert any(
        "scripts/ai_review_common/cache_guard" in e for e in errors
    ), errors


def test_unregistered_source_root_fails(tmp_path: Path) -> None:
    """A source root present on disk but absent from SYNC_PAIRS fails."""
    _make_package(tmp_path / "scripts", "github_core")
    _make_package(tmp_path / "scripts", "hook_utilities")
    # Only github_core is registered; hook_utilities is not.
    sync_pairs = [("scripts/github_core", ".claude/lib/github_core")]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert any("scripts/hook_utilities" in e for e in errors), errors


# ---- edge --------------------------------------------------------------------


def test_allowlisted_lib_package_passes(tmp_path: Path) -> None:
    """A lib package named in the allowlist passes without a destination."""
    _make_package(tmp_path / "scripts", "github_core")
    _make_package(tmp_path / ".claude" / "lib", "github_core")
    _make_package(tmp_path / ".claude" / "lib", "vendored")
    sync_pairs = [("scripts/github_core", ".claude/lib/github_core")]

    errors = vsr.find_unregistered(
        tmp_path, sync_pairs, allowlist=frozenset({"vendored"})
    )

    assert errors == [], errors


def test_non_package_dirs_ignored(tmp_path: Path) -> None:
    """`__pycache__` and dirs without __init__.py are not flagged."""
    _make_package(tmp_path / "scripts", "github_core")
    lib = tmp_path / ".claude" / "lib"
    _make_package(lib, "github_core")
    # __pycache__ has no __init__.py; a bare dir has no __init__.py either.
    (lib / "__pycache__").mkdir(parents=True)
    (lib / "bare_dir").mkdir()
    sync_pairs = [("scripts/github_core", ".claude/lib/github_core")]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert errors == [], errors


def test_loose_lib_file_ignored(tmp_path: Path) -> None:
    """A loose `.py` file under `.claude/lib/` (e.g. bootstrap.py) is not a package."""
    _make_package(tmp_path / "scripts", "github_core")
    lib = tmp_path / ".claude" / "lib"
    _make_package(lib, "github_core")
    (lib / "bootstrap.py").write_text("# loose module\n", encoding="utf-8")
    sync_pairs = [("scripts/github_core", ".claude/lib/github_core")]

    errors = vsr.find_unregistered(tmp_path, sync_pairs)

    assert errors == [], errors


def test_missing_repo_root_returns_config_error(tmp_path: Path) -> None:
    """Per ADR-035: a missing repo root returns exit 2, not 1."""
    missing = tmp_path / "does-not-exist"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(missing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "repo root not found" in result.stderr


# ---- CLI / exit codes --------------------------------------------------------


def test_cli_passes_on_registered_tree(tmp_path: Path) -> None:
    """CLI exits 0 when the scaffolded tree matches the real SYNC_PAIRS.

    The CLI imports the real SYNC_PAIRS, so the synthetic tree mirrors the
    three registered destinations and the three source roots
    (github_core, hook_utilities, ai_review_common).
    """
    _make_package(tmp_path / "scripts", "github_core")
    _make_package(tmp_path / "scripts", "hook_utilities")
    _make_package(tmp_path / "scripts", "ai_review_common")
    for name in ("github_core", "hook_utilities", "ai_review_common"):
        _make_package(tmp_path / ".claude" / "lib", name)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PASS]" in result.stdout


def test_cli_fails_on_unregistered_lib(tmp_path: Path) -> None:
    """CLI exits 1 when a lib package has no registered destination."""
    _make_package(tmp_path / "scripts", "github_core")
    _make_package(tmp_path / ".claude" / "lib", "github_core")
    _make_package(tmp_path / ".claude" / "lib", "unregistered_pkg")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "unregistered_pkg" in result.stdout


# ---- integration -------------------------------------------------------------


def test_real_repo_registry_is_complete() -> None:
    """Regression: the actual repo tree satisfies the gate with real SYNC_PAIRS."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Real sync registry is incomplete:\n" + result.stdout + result.stderr
    )
