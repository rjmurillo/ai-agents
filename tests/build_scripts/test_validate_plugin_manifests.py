"""Tests for build/scripts/validate_plugin_manifests.py.

Covers the regression class from PR #1773 (broken plugin install for
all consumers due to invalid `agents`/`hooks` shapes in plugin.json),
plus positive cases that match real-world working plugins (caveman).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_plugin_manifests as vpm  # noqa: E402


def _write(tmp_path: Path, manifest: dict) -> Path:
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    target = plugin_dir / "plugin.json"
    target.write_text(json.dumps(manifest), encoding="utf-8")
    return target


# --- Positive cases ---------------------------------------------------------


def test_minimal_valid_manifest(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "test-plugin"})
    assert vpm.validate_manifest(target) == []


def test_caveman_shaped_manifest_passes(tmp_path: Path) -> None:
    """Real-world working plugin shape from caveman/plugin.json."""
    target = _write(
        tmp_path,
        {
            "name": "caveman",
            "description": "Compressed mode",
            "author": {"name": "Julius"},
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "node hooks/activate.js",
                                "timeout": 5,
                            }
                        ]
                    }
                ]
            },
        },
    )
    assert vpm.validate_manifest(target) == []


def test_path_field_as_string_valid(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "agents": "./agents"})
    assert vpm.validate_manifest(target) == []


def test_path_field_as_array_of_strings_valid(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "agents": ["./agents", "./more"]})
    assert vpm.validate_manifest(target) == []


def test_path_field_root_dot_slash_valid(tmp_path: Path) -> None:
    """`./` (plugin root) is a valid path; src/claude and src/copilot-cli use this."""
    target = _write(tmp_path, {"name": "p", "agents": "./"})
    assert vpm.validate_manifest(target) == []


def test_path_field_without_dot_slash_prefix_rejected(tmp_path: Path) -> None:
    """Per Anthropic plugin rules, paths must start with './'."""
    target = _write(tmp_path, {"name": "p", "agents": "agents"})
    errors = vpm.validate_manifest(target)
    assert any("must start with './'" in e for e in errors)


def test_path_field_with_traversal_rejected(tmp_path: Path) -> None:
    """`..` traversal is forbidden in plugin manifest paths."""
    target = _write(tmp_path, {"name": "p", "agents": "./../agents"})
    errors = vpm.validate_manifest(target)
    assert any("'..'" in e for e in errors)


def test_hooks_as_string_path_to_json_valid(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "hooks": "./hooks/hooks.json"})
    assert vpm.validate_manifest(target) == []


def test_hooks_string_path_must_have_dot_slash(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "hooks": "hooks/hooks.json"})
    errors = vpm.validate_manifest(target)
    assert any("must start with './'" in e for e in errors)


def test_hooks_string_path_no_traversal(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "hooks": "./../hooks.json"})
    errors = vpm.validate_manifest(target)
    assert any("'..'" in e for e in errors)


def test_manifest_read_error_returns_clean_message(tmp_path: Path) -> None:
    """Missing file must return clean error, not crash with FileNotFoundError."""
    missing = tmp_path / "nope.json"
    errors = vpm.validate_manifest(missing)
    assert any("read error" in e.lower() for e in errors)


def test_hooks_string_ref_validates_referenced_file(tmp_path: Path) -> None:
    """When `hooks` is a string ref and the file exists, its content is checked."""
    plugin_root = tmp_path
    plugin_dir = plugin_root / ".claude-plugin"
    plugin_dir.mkdir()
    manifest = plugin_dir / "plugin.json"
    manifest.write_text(json.dumps({"name": "p", "hooks": "./hooks.json"}), encoding="utf-8")
    # Valid wrapped hooks.json
    (plugin_root / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]}}),
        encoding="utf-8",
    )
    assert vpm.validate_manifest(manifest) == []


def test_hooks_string_ref_rejects_invalid_referenced_file(tmp_path: Path) -> None:
    """Referenced hooks.json with unknown event must surface error."""
    plugin_root = tmp_path
    plugin_dir = plugin_root / ".claude-plugin"
    plugin_dir.mkdir()
    manifest = plugin_dir / "plugin.json"
    manifest.write_text(json.dumps({"name": "p", "hooks": "./hooks.json"}), encoding="utf-8")
    (plugin_root / "hooks.json").write_text(
        json.dumps({"hooks": {"NotARealEvent": [{"hooks": [{"type": "command", "command": "x"}]}]}}),
        encoding="utf-8",
    )
    errors = vpm.validate_manifest(manifest)
    assert any("NotARealEvent" in e for e in errors)


def test_referenced_hooks_must_have_top_level_wrapper(tmp_path: Path) -> None:
    """Bare events object (no `hooks` wrapper) is rejected — Claude Code does not load events without it."""
    plugin_root = tmp_path
    plugin_dir = plugin_root / ".claude-plugin"
    plugin_dir.mkdir()
    manifest = plugin_dir / "plugin.json"
    manifest.write_text(json.dumps({"name": "p", "hooks": "./hooks.json"}), encoding="utf-8")
    # Bare events shape — INVALID per production plugin examples
    (plugin_root / "hooks.json").write_text(
        json.dumps({"PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]}),
        encoding="utf-8",
    )
    errors = vpm.validate_manifest(manifest)
    assert any("top-level" in e and "hooks" in e for e in errors)


def test_manifest_decode_error_returns_clean_message(tmp_path: Path) -> None:
    """Non-UTF8 manifest must surface as validation error, not crash."""
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    target = plugin_dir / "plugin.json"
    target.write_bytes(b"\xff\xfe\x00invalid utf8")
    errors = vpm.validate_manifest(target)
    assert any("decode error" in e.lower() for e in errors)


def test_referenced_hooks_decode_error_caught(tmp_path: Path) -> None:
    """Non-UTF8 referenced hooks.json must surface error, not crash."""
    plugin_root = tmp_path
    plugin_dir = plugin_root / ".claude-plugin"
    plugin_dir.mkdir()
    manifest = plugin_dir / "plugin.json"
    manifest.write_text(json.dumps({"name": "p", "hooks": "./hooks.json"}), encoding="utf-8")
    (plugin_root / "hooks.json").write_bytes(b"\xff\xfe\x00")
    errors = vpm.validate_manifest(manifest)
    assert any("unreadable" in e.lower() for e in errors)


def test_find_manifests_prunes_node_modules(tmp_path: Path) -> None:
    """Walk must not descend into excluded dirs (perf: avoid huge node_modules)."""
    (tmp_path / "node_modules" / "deep" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "node_modules" / "deep" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (tmp_path / "real" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "real" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    found = vpm.find_manifests(tmp_path)
    assert len(found) == 1
    assert "node_modules" not in str(found[0])


def test_hooks_string_ref_skipped_when_file_missing(tmp_path: Path) -> None:
    """Missing referenced file does not crash; path-shape check still applied."""
    plugin_root = tmp_path
    plugin_dir = plugin_root / ".claude-plugin"
    plugin_dir.mkdir()
    manifest = plugin_dir / "plugin.json"
    manifest.write_text(json.dumps({"name": "p", "hooks": "./missing-hooks.json"}), encoding="utf-8")
    # No referenced file written. Should pass (path shape OK, content check skipped).
    assert vpm.validate_manifest(manifest) == []


# --- Regression: PR #1773 bug -----------------------------------------------


def test_regression_hooks_as_dict_of_strings_rejected(tmp_path: Path) -> None:
    """PR #1773 bug: pointing hook events at directories breaks plugin install."""
    target = _write(
        tmp_path,
        {
            "name": "project-toolkit",
            "hooks": {
                "PreToolUse": "./hooks/PreToolUse",
                "SessionStart": "./hooks/SessionStart",
            },
        },
    )
    errors = vpm.validate_manifest(target)
    assert errors
    assert any("PR #1773" in e for e in errors)
    assert any("PreToolUse" in e for e in errors)


def test_regression_agents_dict_shape_rejected(tmp_path: Path) -> None:
    """`agents` must be string or list of strings, not a dict or other shape."""
    target = _write(tmp_path, {"name": "p", "agents": {"path": "./agents"}})
    errors = vpm.validate_manifest(target)
    assert any("`agents`" in e for e in errors)


def test_hooks_string_must_end_with_json(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "hooks": "./hooks"})
    errors = vpm.validate_manifest(target)
    assert any(".json" in e for e in errors)


def test_unknown_hook_event_rejected(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        {"name": "p", "hooks": {"NotAnEvent": [{"hooks": [{"type": "command", "command": "x"}]}]}},
    )
    errors = vpm.validate_manifest(target)
    assert any("NotAnEvent" in e for e in errors)


def test_hook_command_missing_rejected(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        {"name": "p", "hooks": {"PreToolUse": [{"hooks": [{"type": "command"}]}]}},
    )
    errors = vpm.validate_manifest(target)
    assert any("command" in e.lower() for e in errors)


def test_hook_type_must_be_command(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        {
            "name": "p",
            "hooks": {
                "PreToolUse": [{"hooks": [{"type": "script", "command": "x"}]}]
            },
        },
    )
    errors = vpm.validate_manifest(target)
    assert any("'command'" in e for e in errors)


# --- Schema basics ----------------------------------------------------------


def test_missing_name_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, {"description": "no name"})
    errors = vpm.validate_manifest(target)
    assert any("name" in e for e in errors)


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, {"name": "p", "garbage": True})
    errors = vpm.validate_manifest(target)
    assert any("garbage" in e for e in errors)


def test_invalid_json_rejected(tmp_path: Path) -> None:
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    target = plugin_dir / "plugin.json"
    target.write_text("{not json", encoding="utf-8")
    errors = vpm.validate_manifest(target)
    assert any("JSON parse error" in e for e in errors)


def test_top_level_must_be_object(tmp_path: Path) -> None:
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    target = plugin_dir / "plugin.json"
    target.write_text("[]", encoding="utf-8")
    assert any("object" in e for e in vpm.validate_manifest(target))


# --- Discovery + CLI --------------------------------------------------------


def test_find_manifests_skips_worktrees(tmp_path: Path) -> None:
    (tmp_path / "a" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "a" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (tmp_path / "worktrees" / "b" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "worktrees" / "b" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    found = vpm.find_manifests(tmp_path)
    assert len(found) == 1
    assert "worktrees" not in str(found[0])


def test_main_returns_zero_when_all_valid(tmp_path: Path, capsys) -> None:
    target = _write(tmp_path, {"name": "p"})
    assert vpm.main(["--manifest", str(target), "--root", str(tmp_path)]) == 0


def test_main_returns_one_on_failure(tmp_path: Path, capsys) -> None:
    target = _write(tmp_path, {"name": "p", "hooks": {"PreToolUse": "./d"}})
    assert vpm.main(["--manifest", str(target), "--root", str(tmp_path)]) == 1


def test_main_returns_two_when_no_manifests(tmp_path: Path) -> None:
    assert vpm.main(["--root", str(tmp_path)]) == 2


# --- Real repo manifests ----------------------------------------------------


def test_actual_repo_manifests_are_valid() -> None:
    """All committed plugin.json files in the repo must validate.

    This is the regression gate that prevents shipping broken manifests
    to plugin consumers (the PR #1773 incident).
    """
    manifests = vpm.find_manifests(REPO_ROOT)
    assert manifests, "Expected at least 1 manifest in the repo"
    failures: list[str] = []
    for manifest in manifests:
        errors = vpm.validate_manifest(manifest)
        if errors:
            failures.append(f"{manifest}: {errors}")
    assert not failures, "Invalid manifests:\n" + "\n".join(failures)
