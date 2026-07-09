#!/usr/bin/env python3
"""Behavioral tests for the pre-commit STAGED_SKILL_FILES selection filter.

The pre-commit hook selects which staged ``SKILL.md`` files get SkillForge
structural validation. It keeps real shipped skills and excludes two classes
that intentionally do not follow the SkillForge structure:

1. Copilot CLI command-mirror skills under
   ``src/copilot-cli/skills/{spec,plan,...}/SKILL.md`` (issue #2743).
2. Eval fixtures under ``evals/`` (issue #2936): the form-factor eval reuses an
   agent body verbatim as a skill body to isolate form from content, so a
   content-controlled fixture lacks Triggers/Process sections by construction.

The filter is a bash grep pipeline with no Python seam. To avoid duplicating
the pipeline (which would drift from the hook), this test extracts the exact
``STAGED_SKILL_FILES=...`` assignment from ``.githooks/pre-commit`` and runs it
under bash against sample staged-file lists.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"


def _extract_filter_block() -> str:
    """Return the STAGED_SKILL_FILES assignment lines from the hook.

    Extracts from the ``STAGED_SKILL_FILES=$(echo "$STAGED_FILES"`` line
    through the terminating ``|| true)`` line, inclusive.
    """
    lines = PRE_COMMIT.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith('STAGED_SKILL_FILES=$(echo "$STAGED_FILES"'):
            start = i
            break
    assert start is not None, "STAGED_SKILL_FILES assignment not found in hook"
    end = None
    for j in range(start, len(lines)):
        if "|| true)" in lines[j]:
            end = j
            break
    assert end is not None, "filter block terminator '|| true)' not found"
    return "\n".join(lines[start : end + 1])


def _run_filter(staged_files: str) -> list[str]:
    """Run the extracted filter with a given STAGED_FILES value.

    Returns the resulting STAGED_SKILL_FILES entries as a list.
    """
    block = _extract_filter_block()
    script = f'{block}\nprintf "%s" "$STAGED_SKILL_FILES"'
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - bash is present on CI and dev hosts
        pytest.skip("bash not available")
    result = subprocess.run(
        [bash, "-c", script],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env={**os.environ, "STAGED_FILES": staged_files},
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout.strip()
    return [line for line in out.splitlines() if line]


class TestSkillValidationFilter:
    def test_real_skill_is_selected(self):
        staged = ".claude/skills/security-review/SKILL.md"
        assert _run_filter(staged) == [staged]

    def test_eval_fixture_is_excluded(self):
        """Issue #2936: evals/ fixtures are harness inputs, not shipped skills."""
        staged = "evals/security-spike/skill-content-controlled/SKILL.md"
        assert _run_filter(staged) == []

    def test_command_mirror_is_excluded(self):
        """Issue #2743: Copilot CLI command-mirror skills are excluded."""
        staged = "src/copilot-cli/skills/spec/SKILL.md"
        assert _run_filter(staged) == []

    def test_mixed_list_keeps_only_real_skill(self):
        real = ".claude/skills/analyze/SKILL.md"
        staged = "\n".join(
            [
                real,
                "evals/security-spike/skill-content-controlled/SKILL.md",
                "src/copilot-cli/skills/plan/SKILL.md",
                "scripts/eval/eval-agent-vs-baseline.py",
            ]
        )
        assert _run_filter(staged) == [real]

    def test_non_skill_files_are_excluded(self):
        staged = "\n".join(
            [
                "scripts/foo.py",
                "docs/SKILL-AUTHORING.md",
                "README.md",
            ]
        )
        assert _run_filter(staged) == []

    def test_nested_eval_fixture_is_excluded(self):
        staged = "evals/deep/nested/dir/SKILL.md"
        assert _run_filter(staged) == []
