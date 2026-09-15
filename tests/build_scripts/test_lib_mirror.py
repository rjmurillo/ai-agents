"""Tests for build/scripts/lib_mirror.py (ADR-109 B5, TASK-035).

Covers the copy-logic relocation from `scripts/sync_plugin_lib.py`: the
directory sync with relative-import rewrite (`sync_pair`), the single-file
byte copy with self-contained-import rejection (`sync_file`), and the
`compile_all` orchestrator that renders every package and file pair into
both lib plugin trees.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import lib_mirror  # noqa: E402

# --- sync_pair (directory sync, import rewrite) -----------------------------


def test_sync_pair_creates_missing_destination(tmp_path: Path) -> None:
    src = tmp_path / "scripts" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("X = 1\n", encoding="utf-8")

    changes, had_errors = lib_mirror.sync_pair(
        tmp_path, "scripts/pkg", "dst/pkg", check_only=False
    )

    assert had_errors is False, changes
    assert (tmp_path / "dst" / "pkg" / "mod.py").read_text(encoding="utf-8") == "X = 1\n"


def test_sync_pair_rewrites_absolute_imports(tmp_path: Path) -> None:
    # IMPORT_CONVERSIONS only rewrites the three registered package names
    # (hook_utilities, github_core, ai_review_common), not an arbitrary "pkg".
    hook_src = tmp_path / "scripts" / "hook_utilities"
    hook_src.mkdir(parents=True)
    (hook_src / "mod.py").write_text(
        "from scripts.hook_utilities.other import thing\n"
        "from scripts.hook_utilities import sibling\n",
        encoding="utf-8",
    )

    changes, had_errors = lib_mirror.sync_pair(
        tmp_path, "scripts/hook_utilities", "dst/hook_utilities", check_only=False
    )

    assert had_errors is False, changes
    out = (tmp_path / "dst" / "hook_utilities" / "mod.py").read_text(encoding="utf-8")
    assert out == "from .other import thing\nfrom . import sibling\n"


def test_sync_pair_check_mode_detects_drift_without_writing(tmp_path: Path) -> None:
    src = tmp_path / "scripts" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("X = 1\n", encoding="utf-8")
    dst = tmp_path / "dst" / "pkg"
    dst.mkdir(parents=True)
    (dst / "mod.py").write_text("X = 2\n", encoding="utf-8")

    changes, had_errors = lib_mirror.sync_pair(
        tmp_path, "scripts/pkg", "dst/pkg", check_only=True
    )

    assert had_errors is False
    assert any("updated" in c for c in changes)
    assert (dst / "mod.py").read_text(encoding="utf-8") == "X = 2\n"  # unchanged


def test_sync_pair_removes_stale_py_but_keeps_non_py(tmp_path: Path) -> None:
    src = tmp_path / "scripts" / "pkg"
    src.mkdir(parents=True)
    (src / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    dst = tmp_path / "dst" / "pkg"
    dst.mkdir(parents=True)
    (dst / "stale.py").write_text("STALE = 1\n", encoding="utf-8")
    (dst / "CLAUDE.md").write_text("hand-maintained sidecar\n", encoding="utf-8")

    changes, had_errors = lib_mirror.sync_pair(
        tmp_path, "scripts/pkg", "dst/pkg", check_only=False
    )

    assert had_errors is False, changes
    assert not (dst / "stale.py").exists()
    assert (dst / "CLAUDE.md").read_text(encoding="utf-8") == "hand-maintained sidecar\n"
    assert (dst / "keep.py").is_file()


def test_sync_pair_missing_source_dir_is_warning_not_error(tmp_path: Path) -> None:
    changes, had_errors = lib_mirror.sync_pair(
        tmp_path, "scripts/missing", "dst/missing", check_only=False
    )
    assert had_errors is False
    assert any("Source directory missing" in c for c in changes)


def test_sync_pair_rejects_source_escaping_repo_root(tmp_path: Path) -> None:
    changes, had_errors = lib_mirror.sync_pair(
        tmp_path, "../outside", "dst/pkg", check_only=False
    )
    assert had_errors is True
    assert any("escapes repo root" in c for c in changes)


# --- sync_file (single-file byte copy) --------------------------------------


def test_sync_file_creates_missing_dest(tmp_path: Path) -> None:
    src = tmp_path / "scripts" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text('"""Self-contained module."""\nX = 1\n', encoding="utf-8")

    changes, had_errors = lib_mirror.sync_file(
        tmp_path, "scripts/pkg/mod.py", "dst/mod.py", check_only=False
    )

    assert had_errors is False, changes
    dst = tmp_path / "dst" / "mod.py"
    assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_sync_file_check_detects_drift(tmp_path: Path) -> None:
    src = tmp_path / "scripts" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text('"""Canonical."""\nX = 1\n', encoding="utf-8")
    dst = tmp_path / "dst" / "mod.py"
    dst.parent.mkdir(parents=True)
    dst.write_text('"""Stale."""\nX = 2\n', encoding="utf-8")

    changes, had_errors = lib_mirror.sync_file(
        tmp_path, "scripts/pkg/mod.py", "dst/mod.py", check_only=True
    )

    assert had_errors is False, changes
    assert changes
    assert dst.read_text(encoding="utf-8") == '"""Stale."""\nX = 2\n'  # unchanged


@pytest.mark.parametrize(
    "import_line",
    [
        "from scripts.pkg.other import thing",
        "import scripts.pkg.other",
        "from scripts import other",
        "import scripts",
        "import scripts as s",
        "import os, scripts",
        'x = __import__("scripts.hook_utilities.bootstrap")',
        'import importlib\ny = importlib.import_module("scripts.pkg")',
        'from importlib import import_module\nq = import_module("scripts.pkg")',
    ],
)
def test_sync_file_rejects_scripts_import(tmp_path: Path, import_line: str) -> None:
    src = tmp_path / "scripts" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(f'"""Not self-contained."""\n{import_line}\n', encoding="utf-8")

    changes, had_errors = lib_mirror.sync_file(
        tmp_path, "scripts/pkg/mod.py", "dst/mod.py", check_only=False
    )

    assert had_errors is True
    assert any("scripts package" in c for c in changes), changes
    assert not (tmp_path / "dst" / "mod.py").exists()


@pytest.mark.parametrize(
    "import_line",
    ["import scripts_helper", "from scripts_util import thing", "import scriptsfoo"],
)
def test_sync_file_allows_lookalike_module(tmp_path: Path, import_line: str) -> None:
    """A module whose name merely starts with 'scripts' is not the scripts pkg."""
    src = tmp_path / "scripts" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(f'"""Self-contained."""\n{import_line}\n', encoding="utf-8")

    changes, had_errors = lib_mirror.sync_file(
        tmp_path, "scripts/pkg/mod.py", "dst/mod.py", check_only=False
    )

    assert had_errors is False, changes
    assert (tmp_path / "dst" / "mod.py").read_text(encoding="utf-8") == src.read_text(
        encoding="utf-8"
    )


def test_sync_file_missing_source_fails_closed(tmp_path: Path) -> None:
    changes, had_errors = lib_mirror.sync_file(
        tmp_path, "scripts/pkg/missing.py", "dst/missing.py", check_only=True
    )
    assert had_errors is True
    assert any("Registered source file missing" in c for c in changes), changes
    assert not (tmp_path / "dst" / "missing.py").exists()


def test_sync_file_preserves_bytes_and_detects_newline_drift(tmp_path: Path) -> None:
    """CRLF-vs-LF is drift, not silent normalization."""
    src = tmp_path / "scripts" / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_bytes(b'"""Canonical."""\r\nX = 1\r\n')
    dst = tmp_path / "dst" / "mod.py"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b'"""Canonical."""\nX = 1\n')

    check_changes, check_errors = lib_mirror.sync_file(
        tmp_path, "scripts/pkg/mod.py", "dst/mod.py", check_only=True
    )
    assert check_errors is False, check_changes
    assert check_changes, "CRLF/LF byte drift should be detected"
    assert dst.read_bytes() == b'"""Canonical."""\nX = 1\n'

    lib_mirror.sync_file(tmp_path, "scripts/pkg/mod.py", "dst/mod.py", check_only=False)
    assert dst.read_bytes() == b'"""Canonical."""\r\nX = 1\r\n'


# --- compile_all (orchestrator) ---------------------------------------------


def _write_full_sources(root: Path) -> None:
    for pkg in lib_mirror.PACKAGES:
        pkg_dir = root / "scripts" / pkg
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (root / "scripts" / "hook_utilities" / "bootstrap.py").write_text(
        '"""Bootstrap."""\n', encoding="utf-8"
    )
    validation = root / "scripts" / "validation"
    validation.mkdir(parents=True)
    (validation / "validate_review_marker.py").write_text('"""Marker."""\n', encoding="utf-8")


def test_compile_all_renders_every_package_into_both_plugin_roots(tmp_path: Path) -> None:
    _write_full_sources(tmp_path)

    result = lib_mirror.compile_all(tmp_path)

    assert not result.had_errors, result.errors
    for root in lib_mirror.PLUGIN_ROOTS:
        for pkg in lib_mirror.PACKAGES:
            assert (tmp_path / root / pkg / "__init__.py").is_file()
        assert (tmp_path / root / "bootstrap.py").is_file()
    assert (
        tmp_path / "src" / "claude" / "skills" / "review" / "scripts" / "validate_review_marker.py"
    ).is_file()


def test_compile_all_check_mode_writes_nothing(tmp_path: Path) -> None:
    _write_full_sources(tmp_path)

    result = lib_mirror.compile_all(tmp_path, check=True)

    assert not result.had_errors, result.errors
    assert not (tmp_path / "src" / "claude" / "lib").exists()


def test_compile_all_surfaces_missing_file_source_as_error(tmp_path: Path) -> None:
    result = lib_mirror.compile_all(tmp_path)
    assert result.had_errors
    assert any("Registered source file missing" in e for e in result.errors)


def test_sync_pairs_constant_matches_packages() -> None:
    """SYNC_PAIRS (validate_sync_registry.py's read-only source) covers every package."""
    assert {src for src, _ in lib_mirror.SYNC_PAIRS} == {
        f"scripts/{pkg}" for pkg in lib_mirror.PACKAGES
    }
    assert {dst for _, dst in lib_mirror.SYNC_PAIRS} == {
        f".claude/lib/{pkg}" for pkg in lib_mirror.PACKAGES
    }
