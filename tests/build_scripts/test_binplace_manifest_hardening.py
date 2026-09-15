"""Hardening coverage for build/scripts/binplace_manifest.py (ADR-109 B4 review fixes).

Split out of test_binplace_manifest.py, which approaches the taste-lint
500-line file-size ceiling, mirroring the
test_hook_templates_symlink_security.py split precedent. Covers three
review-driven fixes, none of which the original file's tests exercised:

- Permission-only drift: matching bytes but a mismatched mode is still
  drift, in both check and write mode (binplace_manifest.py#L397-398 review
  finding).
- NO-REGEN honored before publication: a protected install path is skipped,
  not overwritten, and never allowlisted (binplace_manifest.py#L268-272
  review finding).
- Intermediate symlinked ancestors: a plugin_tree or install_tree ancestor
  that redirects to another IN-REPO path is rejected at load() time
  (binplace_manifest.py#L177-185 review finding).
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


# --- Permission-only drift (matching bytes, mismatched mode) --------------


def test_binplace_check_mode_reports_mode_only_drift(tmp_path: Path) -> None:
    """binplace check mode: matching bytes but a lost executable bit is still drift."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "hooks"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    src = plugin_dir / "session-start.sh"
    src.write_bytes(b"#!/bin/sh\necho hi\n")
    src.chmod(0o755)

    install_dir = root / ".claude" / "hooks"
    install_dir.mkdir(parents=True, exist_ok=True)
    dst = install_dir / "session-start.sh"
    dst.write_bytes(b"#!/bin/sh\necho hi\n")
    dst.chmod(0o644)  # lost +x, bytes match

    write_manifest(
        root,
        "rows:\n"
        "  - class: hooks\n"
        "    source: templates/hooks\n"
        "    plugin_tree: src/claude/hooks\n"
        "    install_tree: .claude/hooks\n",
    )

    result = binplace_manifest.binplace(root, check=True)

    assert result.exit_code == 2
    assert str(dst) in result.drifted
    assert dst.stat().st_mode & 0o777 == 0o644  # untouched in check mode


def test_binplace_write_mode_repairs_mode_only_drift(tmp_path: Path) -> None:
    """binplace write mode: matching bytes but a lost executable bit is repaired."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "hooks"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    src = plugin_dir / "session-start.sh"
    src.write_bytes(b"#!/bin/sh\necho hi\n")
    src.chmod(0o755)

    install_dir = root / ".claude" / "hooks"
    install_dir.mkdir(parents=True, exist_ok=True)
    dst = install_dir / "session-start.sh"
    dst.write_bytes(b"#!/bin/sh\necho hi\n")
    dst.chmod(0o644)

    write_manifest(
        root,
        "rows:\n"
        "  - class: hooks\n"
        "    source: templates/hooks\n"
        "    plugin_tree: src/claude/hooks\n"
        "    install_tree: .claude/hooks\n",
    )

    result = binplace_manifest.binplace(root, check=False)

    assert result.exit_code == 0
    assert str(dst) in result.written
    assert dst.stat().st_mode & 0o777 == 0o755


# --- NO-REGEN honored before publication -----------------------------------


def test_binplace_write_mode_skips_no_regen_target(tmp_path: Path) -> None:
    """binplace write mode: a NO-REGEN-sidecar-protected target is skipped, not overwritten."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "test.md").write_bytes(b"new\n")

    install_dir = root / ".claude" / "agents"
    install_dir.mkdir(parents=True, exist_ok=True)
    dst = install_dir / "test.md"
    dst.write_bytes(b"hand-protected\n")
    (install_dir / "test.md.noregen").write_text("", encoding="utf-8")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n",
    )

    result = binplace_manifest.binplace(root, check=False)

    assert result.exit_code == 1
    assert str(dst) in result.skipped
    assert dst.read_bytes() == b"hand-protected\n"


def test_claude_allowlist_excludes_no_regen_protected_path(tmp_path: Path) -> None:
    """claude_allowlist: a NO-REGEN-protected install path is never allowlisted."""
    root = fake_repo(tmp_path)
    plugin_dir = root / "src" / "claude" / "agents"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "protected.md").write_text("content\n", encoding="utf-8")
    (plugin_dir / "open.md").write_text("content\n", encoding="utf-8")

    install_dir = root / ".claude" / "agents"
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "protected.md.noregen").write_text("", encoding="utf-8")

    write_manifest(
        root,
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        "    plugin_tree: src/claude/agents\n"
        "    install_tree: .claude/agents\n",
    )

    allow = binplace_manifest.claude_allowlist(root)

    assert (root / ".claude" / "agents" / "open.md") in allow
    assert (root / ".claude" / "agents" / "protected.md") not in allow


# --- Intermediate symlinked ancestors (plugin_tree / install_tree) --------


def test_load_rejects_symlinked_ancestor_of_install_tree(tmp_path: Path) -> None:
    """Load: an existing symlinked ancestor of install_tree is rejected.

    A grandparent symlinked to another in-repo directory still resolves
    inside the repository root, so a containment check alone would accept
    it; only an explicit ancestor walk catches this redirect.
    """
    root = fake_repo(tmp_path)
    (root / ".claude").mkdir()
    real_target = root / "real-hooks-dir"
    real_target.mkdir()
    link = root / ".claude" / "hooks"
    try:
        link.symlink_to(real_target)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_manifest(
        root,
        "rows:\n"
        "  - class: hooks\n"
        "    source: templates/hooks\n"
        "    plugin_tree: src/claude/hooks\n"
        "    install_tree: .claude/hooks/nested\n",
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)


def test_load_rejects_symlinked_ancestor_of_plugin_tree(tmp_path: Path) -> None:
    """Load: an existing symlinked ancestor of plugin_tree is rejected."""
    root = fake_repo(tmp_path)
    (root / "src" / "claude").mkdir(parents=True)
    real_target = root / "real-plugin-dir"
    real_target.mkdir()
    link = root / "src" / "claude" / "hooks"
    try:
        link.symlink_to(real_target)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_manifest(
        root,
        "rows:\n"
        "  - class: hooks\n"
        "    source: templates/hooks\n"
        "    plugin_tree: src/claude/hooks/nested\n"
        "    install_tree: .claude/hooks/nested\n",
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError):
        binplace_manifest.load(root)
