#!/usr/bin/env python3
"""Tests that SKILL.md usage matches the detect_infrastructure CLI contract."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import SKILL_PATH


def test_skill_usage_matches_cli_contract() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "--git-staged" not in text
    assert "detect_infrastructure.py --use-git-staged" in text
    assert (
        "detect_infrastructure.py --files .github/workflows/ci.yml "
        "src/auth/login.cs"
        in text
    )
    ci_section = text.split("### CI Integration", maxsplit=1)[1]
    assert "--use-git-staged" not in ci_section
    assert "fetch-depth: 0" in ci_section
    assert (
        'git diff --no-renames --name-only -z "$BASE_SHA" "$HEAD_SHA"'
        in ci_section
    )
    normalized_ci = " ".join(ci_section.split())
    assert (
        "| python .claude/skills/security-detection/detect_infrastructure.py "
        "--files-from-stdin"
        in normalized_ci
    )
