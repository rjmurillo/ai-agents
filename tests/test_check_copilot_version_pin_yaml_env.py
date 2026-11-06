"""Tests for the Copilot CLI version-pin guard reading a YAML ``env:`` pin.

The CLI smoke workflow pins ``COPILOT_CLI_VERSION`` as a YAML env entry, the
second form the guard accepts beside the shell ``COPILOT_VERSION`` assignment
covered in ``test_check_copilot_version_pin.py``.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation import check_copilot_version_pin as mod


def test_extract_version_reads_yaml_env_pin(tmp_path: Path) -> None:
    workflow = tmp_path / "wf.yml"
    workflow.write_text(
        "env:\n  # renovate: datasource=npm depName=@github/copilot\n"
        "  COPILOT_CLI_VERSION: '1.0.90'\n",
        encoding="utf-8",
    )
    assert mod.extract_pinned_version(workflow) == "1.0.90"


def test_yaml_env_pin_known_bad_fails(tmp_path: Path) -> None:
    workflow = tmp_path / "wf.yml"
    workflow.write_text("env:\n  COPILOT_CLI_VERSION: '0.0.397'\n", encoding="utf-8")
    assert mod.check_action(workflow) == mod.EXIT_LOGIC


def test_extract_version_reads_package_json_pin(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text(
        '{\n  "private": true,\n  "dependencies": {\n    "@github/copilot": "1.0.105"\n  }\n}\n',
        encoding="utf-8",
    )
    assert mod.extract_pinned_version(manifest) == "1.0.105"
    assert mod.check_action(manifest) == mod.EXIT_OK


def test_package_json_known_bad_pin_fails(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text('{"dependencies": {"@github/copilot": "0.0.397"}}\n', encoding="utf-8")
    assert mod.check_action(manifest) == mod.EXIT_LOGIC


def test_default_target_is_the_committed_copilot_manifest() -> None:
    assert mod._DEFAULT_ACTION.name == "package.json"
    assert mod._DEFAULT_ACTION.parent.name == "copilot"
    assert mod.check_action(mod._DEFAULT_ACTION) == mod.EXIT_OK


def test_package_json_without_the_dependency_fails(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text('{"dependencies": {"left-pad": "1.0.0"}}\n', encoding="utf-8")
    assert mod.check_action(manifest) == mod.EXIT_LOGIC


def test_package_json_invalid_json_fails(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text("{not json", encoding="utf-8")
    assert mod.check_action(manifest) == mod.EXIT_LOGIC


def test_package_json_known_bad_pin_is_rejected_by_the_denylist(tmp_path: Path) -> None:
    """The one-line manifest parses, so the failure is the denylist, not a missing pin."""
    manifest = tmp_path / "package.json"
    manifest.write_text('{"dependencies": {"@github/copilot": "0.0.397"}}\n', encoding="utf-8")
    assert mod.extract_pinned_version(manifest) == "0.0.397"
    assert mod.check_action(manifest) == mod.EXIT_LOGIC
