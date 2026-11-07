"""Wiring tests for the pre-PR Copilot pin check on the package.json manifest (#6506).

The pin moved out of ``plugin-cli-smoke.yml`` into ``.github/cli-smoke/copilot/package.json``.
A wrapper still pointing at the workflow would find no pin and fail on every run. The
``scripts/validation`` path setup mirrors ``test_pre_pr_model_pin_wiring.py``: insert once
and leave it, because ``validate_copilot_version_pin`` imports its guard by bare name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr


def test_pre_pr_pin_check_reads_the_copilot_manifest(tmp_path: Path) -> None:
    """The pre-PR wrapper targets .github/cli-smoke/copilot/package.json (#6506).

    The pin moved out of plugin-cli-smoke.yml. A wrapper still pointing at the
    workflow would find no pin and fail on every run.
    """
    assert pre_pr.validate_copilot_version_pin(REPO_ROOT) is True

    manifest_dir = tmp_path / ".github" / "cli-smoke" / "copilot"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "package.json").write_text(
        '{"dependencies": {"@github/copilot": "0.0.397"}}\n', encoding="utf-8"
    )
    assert pre_pr.validate_copilot_version_pin(tmp_path) is False


def test_pre_pr_pin_check_skips_when_the_manifest_is_absent(tmp_path: Path) -> None:
    with pytest.raises(pre_pr.MissingScriptSkip):
        pre_pr.validate_copilot_version_pin(tmp_path)
