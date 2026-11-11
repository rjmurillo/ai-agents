"""Loader and allowlist tests for the ``hooks`` row's ``repo_only`` list.

ADR-109 amendment 2026-11-11 (issue #7231). ``repo_only`` names top-level
``templates/hooks/`` entries that render straight to ``.claude/hooks/`` and
are skipped by the ``hooks`` copy row. A malformed list is a config error:
``binplace_manifest.BinplaceConfigError`` (exit 2 at load).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
if str(_REPO_ROOT / "build" / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

import binplace_manifest  # noqa: E402

_HOOKS_ROW = (
    "  - class: hooks\n"
    "    source: templates/hooks\n"
    "    plugin_tree: src/claude/hooks\n"
    "    install_tree: .claude/hooks\n"
)


def _repo(tmp_path: Path, repo_only_yaml: str) -> Path:
    """A fake repo with templates/hooks entries and a hooks row carrying ``repo_only_yaml``."""
    (tmp_path / ".git").mkdir()
    hooks = tmp_path / "templates" / "hooks"
    (hooks / "SessionStart").mkdir(parents=True)
    (hooks / "SessionStart" / "invoke_a.py").write_text("x = 1\n", "utf-8")
    (hooks / "SessionStart" / "__pycache__").mkdir()
    (hooks / "SessionStart" / "__pycache__" / "invoke_a.cpython-314.pyc").write_bytes(b"\x00")
    (hooks / "session-start.sh").write_text("#!/bin/sh\n", "utf-8")
    for shipped in (
        "hooks.json",
        "dispatch_groups.json",
        "invoke_dispatch_claude.py",
        "settings.tmpl",
    ):
        (hooks / shipped).write_text("{}\n", "utf-8")
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "binplace.yaml").write_text(
        'schemaVersion: "1.0"\nprovider: claude\nrows:\n' + _HOOKS_ROW + repo_only_yaml,
        encoding="utf-8",
    )
    return tmp_path


def _list(*names: str) -> str:
    return "    repo_only:\n" + "".join(f"      - {name}\n" for name in names)


def test_hooks_row_parses_repo_only_list(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("SessionStart", "session-start.sh"))

    (row,) = binplace_manifest.load(root)

    assert row.repo_only == frozenset({"SessionStart", "session-start.sh"})


def test_row_without_repo_only_defaults_to_empty(tmp_path: Path) -> None:
    root = _repo(tmp_path, "")

    (row,) = binplace_manifest.load(root)

    assert row.repo_only == frozenset()


def test_repo_only_template_files_skips_bytecode_and_lists_files(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("SessionStart", "session-start.sh"))
    (row,) = binplace_manifest.load(root)

    assert binplace_manifest.repo_only_template_files(row) == [
        "SessionStart/invoke_a.py",
        "session-start.sh",
    ]


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        ("''", "non-empty"),
        ("'  '", "non-empty"),
        ("'.'", "dot name"),
        ("'..'", "dot name"),
        ("SessionStart/invoke_a.py", "plain top-level name"),
        ("'Session\\\\Start'", "plain top-level name"),
        ("Missing", "does not exist"),
        ("hooks.json", "cannot be repo-only"),
        ("dispatch_groups.json", "cannot be repo-only"),
        ("invoke_dispatch_claude.py", "cannot be repo-only"),
        ("settings.tmpl", "cannot be repo-only"),
        ("5", "non-empty string"),
    ],
)
def test_loader_rejects_bad_entry(tmp_path: Path, entry: str, reason: str) -> None:
    root = _repo(tmp_path, _list(entry))

    with pytest.raises(binplace_manifest.BinplaceConfigError, match=reason):
        binplace_manifest.load(root)


def test_loader_rejects_duplicate_entries(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("SessionStart", "SessionStart"))

    with pytest.raises(binplace_manifest.BinplaceConfigError, match="duplicate"):
        binplace_manifest.load(root)


@pytest.mark.parametrize(
    "value", ["    repo_only: []\n", "    repo_only: SessionStart\n", "    repo_only:\n"]
)
def test_loader_rejects_empty_or_non_list(tmp_path: Path, value: str) -> None:
    root = _repo(tmp_path, value)

    with pytest.raises(binplace_manifest.BinplaceConfigError, match="non-empty list"):
        binplace_manifest.load(root)


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)
def test_loader_rejects_symlinked_entry(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("linked"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "templates" / "hooks" / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(binplace_manifest.BinplaceConfigError, match="symlink"):
        binplace_manifest.load(root)


def test_loader_rejects_repo_only_on_other_classes(tmp_path: Path) -> None:
    root = _repo(tmp_path, "")
    (root / "templates" / "rules").mkdir()
    manifest = root / "templates" / "platforms" / "binplace.yaml"
    manifest.write_text(
        manifest.read_text("utf-8")
        + "  - class: rules\n"
        + "    source: templates/rules\n"
        + "    plugin_tree: src/claude/rules\n"
        + "    install_tree: .claude/rules\n"
        + _list("SessionStart"),
        encoding="utf-8",
    )

    with pytest.raises(
        binplace_manifest.BinplaceConfigError, match="only valid on the 'hooks' row"
    ):
        binplace_manifest.load(root)


def test_repo_local_names_for_hooks_row_adds_repo_only(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("SessionStart"))
    (row,) = binplace_manifest.load(root)

    assert binplace_manifest._repo_local_names(root, row) == frozenset(
        {"hooks.json", "SessionStart"}
    )


def test_allowlist_includes_repo_only_install_paths_and_excludes_bytecode(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("SessionStart", "session-start.sh"))

    allow = binplace_manifest.claude_allowlist(root)

    assert root / ".claude" / "hooks" / "SessionStart" / "invoke_a.py" in allow
    assert root / ".claude" / "hooks" / "session-start.sh" in allow
    assert not any("__pycache__" in path.parts for path in allow)


def test_allowlist_omits_repo_only_paths_when_list_absent(tmp_path: Path) -> None:
    root = _repo(tmp_path, "")

    assert (
        root / ".claude" / "hooks" / "session-start.sh"
        not in binplace_manifest.claude_allowlist(root)
    )


def test_binplace_leaves_stale_plugin_copy_of_repo_only_entry_alone(tmp_path: Path) -> None:
    root = _repo(tmp_path, _list("SessionStart"))
    stale = root / "src" / "claude" / "hooks" / "SessionStart"
    stale.mkdir(parents=True)
    (stale / "invoke_a.py").write_text("stale\n", "utf-8")

    result = binplace_manifest.binplace(root, check=False)

    assert not (root / ".claude" / "hooks" / "SessionStart" / "invoke_a.py").exists()
    assert result.exit_code == 0
