"""Tests that binplace never treats bytecode caches as plugin-tree files.

Running pytest or a skill script imports a lib plugin tree, and CPython writes
``__pycache__`` there. ``build_all.py --check`` used to report each cache file
as install-tree drift (exit 2), and write mode would copy it. Found while
shipping PR 6219. ``binplace_manifest.is_bytecode_artifact`` owns the rule.
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

import binplace_manifest  # noqa: E402


def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repository root."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_manifest(root: Path, yaml_content: str) -> None:
    """Write binplace.yaml with the required header."""
    platforms_dir = root / "templates" / "platforms"
    platforms_dir.mkdir(parents=True, exist_ok=True)
    full_content = 'schemaVersion: "1.0"\nprovider: claude\n' + yaml_content
    (platforms_dir / "binplace.yaml").write_text(full_content, encoding="utf-8")


_LIB_ROW = (
    "rows:\n"
    "  - class: lib\n"
    "    source: scripts/github_core\n"
    "    plugin_tree: src/claude/lib/github_core\n"
    "    install_tree: .claude/lib/github_core\n"
)


def _lib_trees(root: Path) -> tuple[Path, Path]:
    """Create matching plugin and install lib trees holding one source file."""
    plugin_dir = root / "src" / "claude" / "lib" / "github_core"
    install_dir = root / ".claude" / "lib" / "github_core"
    for tree in (plugin_dir, install_dir):
        tree.mkdir(parents=True, exist_ok=True)
        (tree / "api.py").write_bytes(b"def f():\n    return 1\n")
    write_manifest(root, _LIB_ROW)
    return plugin_dir, install_dir


@pytest.mark.parametrize(
    "relative",
    [
        "lib/__pycache__/api.cpython-314.pyc",
        "lib/__pycache__/coverage.data",
        "lib/api.pyc",
        "lib/api.pyo",
    ],
)
def test_is_bytecode_artifact_matches_caches(relative: str) -> None:
    """is_bytecode_artifact: any file under __pycache__, or any .pyc/.pyo."""
    assert binplace_manifest.is_bytecode_artifact(Path("/repo") / relative) is True


@pytest.mark.parametrize(
    "relative",
    [
        "lib/api.py",
        "lib/pycache_notes.md",
        "lib/__pycache__.md",
        "lib/api.pyc.txt",
    ],
)
def test_is_bytecode_artifact_rejects_real_files(relative: str) -> None:
    """is_bytecode_artifact: names that only resemble caches still count as files."""
    assert binplace_manifest.is_bytecode_artifact(Path("/repo") / relative) is False


def test_binplace_check_mode_ignores_plugin_tree_bytecode(tmp_path: Path) -> None:
    """Check mode: a __pycache__ written into the plugin tree is not drift (found in PR 6219)."""
    root = fake_repo(tmp_path)
    plugin_dir, install_dir = _lib_trees(root)
    cache = plugin_dir / "__pycache__"
    cache.mkdir()
    (cache / "api.cpython-314.pyc").write_bytes(b"\x00bytecode")

    result = binplace_manifest.binplace(root, check=True)

    assert result.exit_code == 0
    assert result.drifted == []
    assert not (install_dir / "__pycache__").exists()


def test_binplace_check_mode_still_reports_real_drift_beside_bytecode(tmp_path: Path) -> None:
    """Negative control: skipping bytecode must not hide drift in a real file."""
    root = fake_repo(tmp_path)
    plugin_dir, install_dir = _lib_trees(root)
    (plugin_dir / "__pycache__").mkdir()
    (plugin_dir / "__pycache__" / "api.cpython-314.pyc").write_bytes(b"\x00")
    (plugin_dir / "pycache_notes.md").write_bytes(b"real file\n")

    result = binplace_manifest.binplace(root, check=True)

    assert result.exit_code == 2
    assert [Path(p) for p in result.drifted] == [install_dir / "pycache_notes.md"]


def test_binplace_write_mode_does_not_copy_bytecode(tmp_path: Path) -> None:
    """Write mode: bytecode in the plugin tree is never copied to the install tree."""
    root = fake_repo(tmp_path)
    plugin_dir, install_dir = _lib_trees(root)
    (plugin_dir / "__pycache__").mkdir()
    (plugin_dir / "__pycache__" / "api.cpython-314.pyc").write_bytes(b"\x00")
    (plugin_dir / "stray.pyc").write_bytes(b"\x00")

    result = binplace_manifest.binplace(root, check=False)

    assert result.exit_code == 0
    assert result.written == []
    assert not (install_dir / "__pycache__").exists()
    assert not (install_dir / "stray.pyc").exists()


def test_binplace_does_not_report_install_tree_bytecode_unowned(tmp_path: Path) -> None:
    """Install-tree caches are runtime artifacts, not unowned files."""
    root = fake_repo(tmp_path)
    _plugin_dir, install_dir = _lib_trees(root)
    (install_dir / "__pycache__").mkdir()
    (install_dir / "__pycache__" / "api.cpython-314.pyc").write_bytes(b"\x00")

    result = binplace_manifest.binplace(root, check=True)

    assert result.exit_code == 0
    assert result.unowned == []


def test_claude_allowlist_excludes_plugin_tree_bytecode(tmp_path: Path) -> None:
    """claude_allowlist: bytecode under a plugin tree is not an allowed write target."""
    root = fake_repo(tmp_path)
    plugin_dir, install_dir = _lib_trees(root)
    (plugin_dir / "__pycache__").mkdir()
    (plugin_dir / "__pycache__" / "api.cpython-314.pyc").write_bytes(b"\x00")

    allow = binplace_manifest.claude_allowlist(root)

    assert install_dir / "api.py" in allow
    assert install_dir / "__pycache__" / "api.cpython-314.pyc" not in allow
