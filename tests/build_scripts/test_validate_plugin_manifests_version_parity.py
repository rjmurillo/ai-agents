"""Tests for build/scripts/validate_plugin_manifests_version_parity.py.

Covers version parity enforcement between .claude and src/copilot-cli plugin
manifests, ensuring both declare identical `version` fields.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_plugin_manifests_version_parity as vpmp  # noqa: E402


def _write_manifest(tmp_path: Path, rel_path: str, version: str | None) -> Path:
    """Write a minimal plugin.json with the given version."""
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"name": "test-plugin"}
    if version is not None:
        manifest["version"] = version
    target.write_text(json.dumps(manifest), encoding="utf-8")
    return target


# --- Positive cases ---------------------------------------------------------


def test_matching_versions_pass(tmp_path: Path) -> None:
    """Both manifests with identical versions should pass."""
    _write_manifest(tmp_path, ".claude/.claude-plugin/plugin.json", "1.2.3")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "1.2.3")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is True
    assert errors == []


def test_main_returns_zero_on_match(tmp_path: Path) -> None:
    """CLI should exit 0 when versions match."""
    _write_manifest(tmp_path, ".claude/.claude-plugin/plugin.json", "0.5.32")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "0.5.32")
    assert vpmp.main(["--root", str(tmp_path)]) == 0


# --- Negative cases: version mismatch ----------------------------------------


def test_version_mismatch_fails(tmp_path: Path) -> None:
    """Mismatched versions should fail with clear diff."""
    _write_manifest(tmp_path, ".claude/.claude-plugin/plugin.json", "0.3.0")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "0.4.0")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("mismatch" in e.lower() for e in errors)
    assert any("0.3.0" in e for e in errors)
    assert any("0.4.0" in e for e in errors)


def test_main_returns_two_on_mismatch(tmp_path: Path) -> None:
    """CLI should exit 2 when versions differ."""
    _write_manifest(tmp_path, ".claude/.claude-plugin/plugin.json", "1.0.0")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "2.0.0")
    assert vpmp.main(["--root", str(tmp_path)]) == 2


def test_version_mismatch_reports_both_paths(tmp_path: Path) -> None:
    """Error message should show which manifest has which version."""
    _write_manifest(tmp_path, ".claude/.claude-plugin/plugin.json", "1.2.3")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "1.2.4")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    joined = "\n".join(errors)
    assert ".claude/.claude-plugin/plugin.json" in joined
    assert "src/copilot-cli/.claude-plugin/plugin.json" in joined


# --- Negative cases: missing manifest ---------------------------------------


def test_missing_manifest_fails(tmp_path: Path) -> None:
    """Missing manifest file should fail validation."""
    _write_manifest(tmp_path, ".claude/.claude-plugin/plugin.json", "1.0.0")
    # Second manifest deliberately not created
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("not found" in e.lower() for e in errors)


def test_both_manifests_missing_fails(tmp_path: Path) -> None:
    """No valid manifests should fail with clear message."""
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("not found" in e.lower() for e in errors)


# --- Negative cases: malformed JSON -----------------------------------------


def test_malformed_json_fails(tmp_path: Path) -> None:
    """Invalid JSON should surface parse error."""
    target = tmp_path / ".claude/.claude-plugin/plugin.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json", encoding="utf-8")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "1.0.0")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("parse error" in e.lower() for e in errors)


def test_non_utf8_manifest_fails(tmp_path: Path) -> None:
    """Non-UTF8 manifest should surface read error."""
    target = tmp_path / ".claude/.claude-plugin/plugin.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xfe\x00invalid")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "1.0.0")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("read error" in e.lower() for e in errors)


def test_top_level_must_be_object(tmp_path: Path) -> None:
    """Manifest top-level value must be a JSON object."""
    target = tmp_path / ".claude/.claude-plugin/plugin.json"
    target.parent.mkdir(parents=True)
    target.write_text("[]", encoding="utf-8")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "1.0.0")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("object" in e.lower() for e in errors)


# --- Negative cases: missing version field ----------------------------------


def test_missing_version_field_fails(tmp_path: Path) -> None:
    """Manifest without `version` field should fail."""
    target = tmp_path / ".claude/.claude-plugin/plugin.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"name": "test"}), encoding="utf-8")
    _write_manifest(tmp_path, "src/copilot-cli/.claude-plugin/plugin.json", "1.0.0")
    parity, errors = vpmp.validate_version_parity(tmp_path)
    assert parity is False
    assert any("missing `version`" in e.lower() for e in errors)


def test_version_must_be_non_empty_string(tmp_path: Path) -> None:
    """`version` value must be a non-empty string, not int/null/whitespace."""
    for idx, bad in enumerate((123, None, "", "   ")):
        sub = tmp_path / f"case-{idx}"
        sub.mkdir()
        target = sub / ".claude/.claude-plugin/plugin.json"
        target.parent.mkdir(parents=True)
        manifest = {"name": "test", "version": bad}
        target.write_text(json.dumps(manifest), encoding="utf-8")
        _write_manifest(sub, "src/copilot-cli/.claude-plugin/plugin.json", "1.0.0")
        parity, errors = vpmp.validate_version_parity(sub)
        assert parity is False, f"bad value {bad!r} should be rejected, got parity={parity}"
        assert any("`version`" in e for e in errors), (
            f"bad value {bad!r} should mention `version`, got errors={errors}"
        )


# --- Real repo manifests ----------------------------------------------------


def test_actual_repo_manifests_have_parity() -> None:
    """Committed manifests in the repo must have matching versions."""
    parity, errors = vpmp.validate_version_parity(REPO_ROOT)
    assert parity is True, f"Version parity violation in repo: {errors}"
