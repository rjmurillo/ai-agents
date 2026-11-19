"""``hook_templates`` routes repo-only entries straight to ``.claude/hooks/``.

ADR-109 amendment 2026-11-11 (issue #7231). The ``hooks`` binplace row's
``repo_only`` list decides each name's render target.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
if str(_REPO_ROOT / "build" / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

import hook_templates  # noqa: E402

_MANIFEST = (
    'schemaVersion: "1.0"\nprovider: claude\nrows:\n'
    "  - class: hooks\n"
    "    source: templates/hooks\n"
    "    plugin_tree: src/claude/hooks\n"
    "    install_tree: .claude/hooks\n"
    "    repo_only:\n"
    "      - SessionStart\n"
    "      - session-start.sh\n"
)


def _repo(tmp_path: Path, manifest: str = _MANIFEST) -> Path:
    (tmp_path / ".git").mkdir()
    hooks = tmp_path / "templates" / "hooks"
    (hooks / "SessionStart").mkdir(parents=True)
    (hooks / "Stop").mkdir()
    (hooks / "SessionStart" / "invoke_a.py").write_bytes(b"print('a')\n")
    (hooks / "Stop" / "invoke_b.py").write_bytes(b"print('b')\n")
    script = hooks / "session-start.sh"
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o755)
    (hooks / "invoke_dispatch_claude.py").write_bytes(b"print('d')\n")
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "binplace.yaml").write_text(manifest, encoding="utf-8")
    return tmp_path


def test_repo_only_name_renders_to_install_tree_not_plugin_tree(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    assert (
        root / ".claude" / "hooks" / "SessionStart" / "invoke_a.py"
    ).read_bytes() == b"print('a')\n"
    assert not (root / "src" / "claude" / "hooks" / "SessionStart").exists()


def test_shipped_name_still_renders_to_plugin_tree(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    hook_templates.compile_all(root, validate=False)

    assert (
        root / "src" / "claude" / "hooks" / "Stop" / "invoke_b.py"
    ).read_bytes() == b"print('b')\n"
    assert (root / "src" / "claude" / "hooks" / "invoke_dispatch_claude.py").is_file()
    assert not (root / ".claude" / "hooks" / "Stop").exists()


def test_repo_only_file_keeps_executable_mode(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    hook_templates.compile_all(root, validate=False)

    assert (root / ".claude" / "hooks" / "session-start.sh").stat().st_mode & 0o777 == 0o755
    assert not (root / "src" / "claude" / "hooks" / "session-start.sh").exists()


def test_validate_reports_drift_against_install_tree_target(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    hook_templates.compile_all(root, validate=False)
    (root / ".claude" / "hooks" / "SessionStart" / "invoke_a.py").write_bytes(b"edited\n")

    result = hook_templates.compile_all(root, validate=True)

    assert result.exit_code == 1
    assert result.drifted == [str(root / ".claude" / "hooks" / "SessionStart" / "invoke_a.py")]


def test_without_a_manifest_every_name_renders_to_plugin_tree(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "templates" / "platforms" / "binplace.yaml").unlink()

    hook_templates.compile_all(root, validate=False)

    assert (root / "src" / "claude" / "hooks" / "SessionStart" / "invoke_a.py").is_file()


def test_malformed_repo_only_list_exits_2_and_writes_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path, _MANIFEST.replace("      - session-start.sh\n", "      - Missing\n"))

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert not (root / "src").exists()
    assert not (root / ".claude").exists()


def test_owned_targets_maps_repo_only_names_to_install_tree(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    owned = hook_templates.owned_targets(root)

    assert root / ".claude" / "hooks" / "SessionStart" / "invoke_a.py" in owned
    assert root / "src" / "claude" / "hooks" / "Stop" / "invoke_b.py" in owned
    assert root / "src" / "claude" / "hooks" / "SessionStart" / "invoke_a.py" not in owned
