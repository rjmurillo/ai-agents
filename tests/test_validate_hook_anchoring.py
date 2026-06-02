#!/usr/bin/env python3
"""Tests for the plugin hook anchoring gate (issue #2205).

Covers both shipped plugin hook files. Copilot entries are compared against the
generator's anchored shape; Claude commands are checked against the
``${CLAUDE_PLUGIN_ROOT}`` invariant. Pins the PASS case (real artifacts) and the
FAIL cases (the regression shapes), plus the config-error path.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import validate_hook_anchoring as gate  # noqa: E402


def test_real_repo_passes_both_plugins() -> None:
    """Both committed plugin hook files anchor correctly (exit 0)."""
    code, messages = gate.validate(REPO_ROOT)
    assert code == 0, messages


# --- Copilot (generator-compared) -------------------------------------------


def _copilot_root(tmp_path: Path, mutate: Callable[[dict], None]) -> Path:
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "scripts").symlink_to(REPO_ROOT / "build" / "scripts")
    hooks_dir = tmp_path / "src" / "copilot-cli" / "hooks"
    hooks_dir.mkdir(parents=True)
    doc = json.loads((REPO_ROOT / gate._COPILOT_REL).read_text())
    mutate(doc)
    (hooks_dir / "hooks.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def test_copilot_bare_bash_path_fails(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        doc["hooks"]["sessionStart"][0]["bash"] = 'python3 -u "./hooks/sessionStart/x.py"'

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".bash" in v for v in violations)


def test_copilot_asymmetric_powershell_fails(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        doc["hooks"]["sessionStart"][0]["powershell"] = (
            'py -3 -u "$env:COPILOT_PLUGIN_ROOT/hooks/sessionStart/x.py"'
        )

    _, violations, config = gate._check_copilot(_copilot_root(tmp_path, mutate))
    assert config == 0
    assert any(".powershell" in v for v in violations)


# --- Claude (invariant against ${CLAUDE_PLUGIN_ROOT}) -----------------------


def test_claude_real_file_is_anchored() -> None:
    checked, violations, config = gate._check_claude(REPO_ROOT)
    assert config == 0
    assert checked > 0
    assert not violations


def test_claude_bare_path_fails(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    doc = {
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": 'python3 -u ".claude/hooks/x.py"'}]}
            ]
        }
    }
    (hooks_dir / "hooks.json").write_text(json.dumps(doc), encoding="utf-8")
    checked, violations, config = gate._check_claude(tmp_path)
    assert config == 0
    assert checked == 1
    assert violations and "not anchored" in violations[0]


def test_missing_files_are_config_error(tmp_path: Path) -> None:
    """Absent hook files are a config error (exit 2), not a false pass."""
    code, _ = gate.validate(tmp_path)
    assert code == 2
