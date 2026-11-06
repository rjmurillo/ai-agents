"""Tests for the Copilot CLI version-pin guard reading a YAML ``env:`` pin.

The guard still accepts the older ``COPILOT_CLI_VERSION`` YAML env form (the CLI
smoke workflow no longer uses it) beside the shell ``COPILOT_VERSION`` assignment
covered in ``test_check_copilot_version_pin.py``. The package.json form is covered
in ``test_check_copilot_version_pin_manifest.py``.
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
