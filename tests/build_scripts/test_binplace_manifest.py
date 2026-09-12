"""Tests for build/scripts/binplace_manifest.py.

Module docstring quotes the exit-code table from binplace_manifest.py:
  0 - the manifest has no rows with a non-null plugin_tree yet, or every
      such row's plugin tree matches its install tree
  2 - a byte mismatch between a plugin-tree file and its install-tree
      counterpart, in check=True mode only; a malformed or malicious
      manifest row is always exit 2, in either mode, at load() time

Covers manifest loading, validation, allowlist generation, and binplace ops.
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
    """Create a fake repository with git init."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_manifest(root: Path, yaml_content: str) -> None:
    """Write binplace.yaml manifest with required schemaVersion."""
    platforms_dir = root / "templates" / "platforms"
    platforms_dir.mkdir(parents=True, exist_ok=True)
    full_content = 'schemaVersion: "1.0"\nprovider: claude\n' + yaml_content
    (platforms_dir / "binplace.yaml").write_text(full_content, encoding="utf-8")


def test_load_empty_when_manifest_absent(tmp_path: Path) -> None:
    """Load: absent manifest returns empty list, not error."""
    root = fake_repo(tmp_path)

    rows = binplace_manifest.load(root)

    assert rows == []


def test_load_parses_valid_manifest(tmp_path: Path) -> None:
    """Load: parses valid manifest rows with all fields."""
    root = fake_repo(tmp_path)
    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    rows = binplace_manifest.load(root)

    assert len(rows) == 1
    assert rows[0].class_name == "agents"
    assert rows[0].source == root / "templates" / "agents"
    assert rows[0].plugin_tree == root / "src" / "claude" / "agents"
    assert rows[0].install_tree == root / ".claude" / "agents"


def test_load_rejects_path_with_double_dot(tmp_path: Path) -> None:
    """Load: path with .. traversal raises BinplaceConfigError."""
    root = fake_repo(tmp_path)
    write_manifest(
        root,
        "rows:\n"
        "  - class: bad\n"
        "    source: templates/../bad\n"
        "    plugin_tree: null\n"
        "    install_tree: .claude/bad\n"
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)


def test_load_rejects_absolute_path(tmp_path: Path) -> None:
    """Load: absolute path raises BinplaceConfigError."""
    root = fake_repo(tmp_path)
    write_manifest(
        root,
        "rows:\n"
        "  - class: bad\n"
        "    source: /absolute/path\n"
        "    plugin_tree: null\n"
        "    install_tree: .claude/bad\n"
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)


def test_load_rejects_path_resolving_outside_repo(tmp_path: Path) -> None:
    """Load: path resolving outside repo raises BinplaceConfigError."""
    root = fake_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link-to-outside"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_manifest(
        root,
        "rows:\n"
        "  - class: bad\n"
        "    source: link-to-outside\n"
        "    plugin_tree: null\n"
        "    install_tree: .claude/bad\n"
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)


def test_load_rejects_symlinked_path(tmp_path: Path) -> None:
    """Load: symlink at path raises BinplaceConfigError."""
    root = fake_repo(tmp_path)
    inside = root / "real-dir"
    inside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(inside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_manifest(
        root,
        "rows:\n"
        "  - class: bad\n"
        "    source: link\n"
        "    plugin_tree: null\n"
        "    install_tree: .claude/bad\n"
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)


def test_load_rejects_install_tree_not_under_prefix(tmp_path: Path) -> None:
    """Load: install_tree outside .claude/ and .github/ raises error."""
    root = fake_repo(tmp_path)
    write_manifest(
        root,
        "rows:\n"
        "  - class: bad\n"
        "    source: templates\n"
        "    plugin_tree: null\n"
        "    install_tree: random/path\n"
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)


def test_claude_allowlist_empty_for_manifest_without_claude_rows(tmp_path: Path) -> None:
    """claude_allowlist: empty when no .claude/-rooted rows."""
    root = fake_repo(tmp_path)
    write_manifest(
        root,
        "rows:\n"
        "  - class: github\n"
        "    source: templates/github\n"
        "    plugin_tree: src/copilot/github\n"
        "    install_tree: .github/github\n"
    )

    allow = binplace_manifest.claude_allowlist(root)

    assert allow == set()


def test_claude_allowlist_includes_plugin_tree_files(tmp_path: Path) -> None:
    """claude_allowlist: includes all files from plugin_tree."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "agent1.md").write_text("content\n", encoding="utf-8")
    (plugin_dir / "agent2.md").write_text("content\n", encoding="utf-8")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    allow = binplace_manifest.claude_allowlist(root)

    assert (root / ".claude" / "agents" / "agent1.md") in allow
    assert (root / ".claude" / "agents" / "agent2.md") in allow


def test_binplace_write_mode_copies_files(tmp_path: Path) -> None:
    """binplace write mode: copies each file byte-for-byte."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "test.md").write_bytes(b"agent content\n")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    result = binplace_manifest.binplace(root, check=False)

    assert result.exit_code == 0
    dst = root / ".claude" / "agents" / "test.md"
    assert dst.read_bytes() == b"agent content\n"
    assert str(dst) in result.written


def test_binplace_idempotent_second_run(tmp_path: Path) -> None:
    """binplace: second run with matching files reports nothing written."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "test.md").write_bytes(b"content\n")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    result1 = binplace_manifest.binplace(root, check=False)
    assert result1.exit_code == 0
    assert len(result1.written) == 1

    result2 = binplace_manifest.binplace(root, check=False)
    assert result2.exit_code == 0
    assert result2.written == []


def test_binplace_check_mode_reports_drift(tmp_path: Path) -> None:
    """binplace check mode: byte mismatch reports drift, exits 2, writes nothing."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "test.md").write_bytes(b"new\n")

    install_dir = root / ".claude" / "agents"
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "test.md").write_bytes(b"old\n")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    result = binplace_manifest.binplace(root, check=True)

    assert result.exit_code == 2
    assert (root / ".claude" / "agents" / "test.md") in [Path(p) for p in result.drifted]
    assert (root / ".claude" / "agents" / "test.md").read_bytes() == b"old\n"


def test_binplace_leaves_extra_file_unowned(tmp_path: Path) -> None:
    """binplace: extra file in install_tree not in plugin_tree stays and is reported."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "owned.md").write_bytes(b"owned\n")

    install_dir = root / ".claude" / "agents"
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "unowned.md").write_bytes(b"unowned\n")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    result = binplace_manifest.binplace(root, check=False)

    assert result.exit_code == 0
    unowned_path = root / ".claude" / "agents" / "unowned.md"
    assert str(unowned_path) in result.unowned
    assert unowned_path.read_bytes() == b"unowned\n"


def test_binplace_skip_row_with_null_plugin_tree(tmp_path: Path) -> None:
    """binplace: row with plugin_tree: null is skipped entirely."""
    root = fake_repo(tmp_path)
    src_dir = root / "templates" / "skills"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "test.md").write_bytes(b"skill content\n")

    write_manifest(
        root,
        "rows:\n"
        "  - class: skills\n"
        "    source: templates/skills\n"
        "    plugin_tree: null\n"
        "    install_tree: .claude/skills\n"
        "    compile: skill_templates\n"
    )

    result = binplace_manifest.binplace(root, check=False)

    assert result.exit_code == 0
    assert result.written == []
    dst = root / ".claude" / "skills" / "test.md"
    assert not dst.exists()


def test_binplace_replaces_symlinked_destination(tmp_path: Path) -> None:
    """binplace: symlink at destination is replaced, outside file untouched."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "test.md").write_bytes(b"new\n")

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "test.md"
    outside_file.write_bytes(b"outside content\n")

    install_dir = root / ".claude" / "agents"
    install_dir.mkdir(parents=True, exist_ok=True)
    link = install_dir / "test.md"
    try:
        link.symlink_to(outside_file)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n"
    )

    binplace_manifest.binplace(root, check=False)

    assert not link.is_symlink()
    assert link.read_bytes() == b"new\n"
    assert outside_file.read_bytes() == b"outside content\n"
