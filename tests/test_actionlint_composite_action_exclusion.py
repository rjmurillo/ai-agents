#!/usr/bin/env python3
"""Regression test for issue #2346.

`.githooks/pre-commit` must not feed `.github/actions/**/action.yml` to
`actionlint`. actionlint validates workflows under `.github/workflows/`;
composite-action metadata produces spurious "missing jobs section" and
"missing on section" errors when scanned as a workflow.

The hook's `grep -E` pattern uses syntax that overlaps with Python `re`. This
test applies that shared subset to catch future edits that accidentally include
composite actions again without depending on an external grep binary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".githooks" / "pre-commit"


def _filter_regex() -> str:
    """Extract the workflow-file grep regex from the pre-commit hook."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"STAGED_WORKFLOW_FILES=\$\(echo \"\$STAGED_FILES\" \| grep -E '([^']+)'",
        text,
    )
    if not match:
        pytest.fail(
            "Could not locate STAGED_WORKFLOW_FILES grep filter in "
            f"{HOOK_PATH.relative_to(REPO_ROOT)}; update this test if the "
            "hook structure changed."
        )
    return match.group(1)


def _regex_matches(regex: str, paths: list[str]) -> list[str]:
    """Apply the hook's current filter pattern to path strings."""
    compiled = re.compile(regex)
    return [path for path in paths if compiled.search(path)]


class TestActionlintCompositeActionExclusion:
    """Issue #2346: composite action YAML must be excluded from actionlint."""

    def test_workflow_yaml_included(self) -> None:
        regex = _filter_regex()
        matched = _regex_matches(
            regex,
            [".github/workflows/ci.yml", ".github/workflows/release.yaml"],
        )
        assert matched == [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yaml",
        ]

    def test_composite_action_yml_excluded(self) -> None:
        """The core bug fix: action.yml must not be selected for actionlint."""
        regex = _filter_regex()
        matched = _regex_matches(
            regex,
            [
                ".github/actions/ai-review/action.yml",
                ".github/actions/agent-review/action.yml",
                ".github/actions/setup-code-env/action.yml",
            ],
        )
        assert matched == [], (
            "Composite action metadata must not be fed to actionlint "
            "(issue #2346). actionlint treats them as workflows and emits "
            "false 'jobs section missing' errors."
        )

    def test_mixed_staging_keeps_only_workflows(self) -> None:
        regex = _filter_regex()
        matched = _regex_matches(
            regex,
            [
                "README.md",
                ".github/workflows/ci.yml",
                ".github/actions/ai-review/action.yml",
                ".github/dependabot.yml",
                "src/main.py",
            ],
        )
        assert matched == [".github/workflows/ci.yml"]

    def test_real_composite_actions_present_in_repo(self) -> None:
        """Sanity check: this repo has composite actions to protect."""
        actions_dir = REPO_ROOT / ".github" / "actions"
        assert actions_dir.is_dir(), "expected .github/actions/ to exist"
        composite_files = list(actions_dir.glob("*/action.yml"))
        assert composite_files, (
            "expected at least one composite action.yml in .github/actions/; "
            "if none exist the bug surface is gone but the guard should stay."
        )
