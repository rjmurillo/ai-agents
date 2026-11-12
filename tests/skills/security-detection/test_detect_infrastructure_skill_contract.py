#!/usr/bin/env python3
"""Tests that SKILL.md usage matches the detect_infrastructure CLI contract."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import SKILL_PATH

_BUILD_SCRIPTS = Path(__file__).resolve().parents[3] / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

import plugin_run_launcher

TARGET = "skills/security-detection/detect_infrastructure.py"


def _locator_args(text: str) -> list[str]:
    """Return the argument text of every locator that runs the detect script."""
    return [
        match.args
        for line in text.splitlines()
        for match in plugin_run_launcher.find_locators(line)
        if match.script_rel == TARGET
    ]


def test_skill_usage_matches_cli_contract() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "--git-staged" not in text
    assert "--use-git-staged" in _locator_args(text)
    assert "detect_infrastructure.py --files .github/workflows/ci.yml src/auth/login.cs" in text
    ci_section = text.split("### CI Integration", maxsplit=1)[1]
    assert "--use-git-staged" not in ci_section
    assert "fetch-depth: 0" in ci_section
    assert 'git diff --no-renames --name-only -z "$BASE_SHA" "$HEAD_SHA"' in ci_section
    assert _locator_args(ci_section) == ["--files-from-stdin"]
    piped = [line for line in ci_section.splitlines() if "--files-from-stdin" in line]
    assert len(piped) == 1
    assert piped[0].lstrip().startswith("| ( for d in")


def test_skill_has_no_legacy_plugin_root_form() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "COPILOT_PLUGIN_ROOT:-" not in text
