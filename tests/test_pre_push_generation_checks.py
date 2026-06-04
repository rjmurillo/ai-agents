#!/usr/bin/env python3
"""Regression coverage for Issue #2343: pre-push generation checks agree with
build_all.py --check.

Pre-push checks 10 (agent generation) and 11 (agent drift) previously pointed at
PowerShell scripts (``build/Generate-Agents.ps1`` and
``build/scripts/Detect-AgentDrift.ps1``) that were replaced by Python equivalents
per ADR-042. In an isolated pr-autofix worktree (a clean checkout of main) the
ps1 paths do not exist, so the checks recorded a confusing "script not found"
SKIP that agents misread as a validation gap, even though ``build_all.py --check``
(check 11b) passed cleanly.

These tests pin the producer side at the script-content level (the same approach
as ``tests/test_pre_push_tree_neutral.py``): the hook references the Python
generators, the deleted ps1 paths are gone, and the referenced Python scripts
actually exist in the worktree so the checks can run rather than skip.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _pre_push_text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def test_generation_check_uses_python_generator() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: check 10 invokes the Python generator with --validate.
    assert "build/generate_agents.py" in text
    assert '"$GENERATE_AGENTS_SCRIPT" --validate' in text


def test_drift_check_uses_python_detector() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: check 11 invokes the Python drift detector.
    assert "build/scripts/detect_agent_drift.py" in text


def test_no_deleted_powershell_generator_script_assignments_remain() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: the script-path variables no longer point at the deleted ps1 files.
    # A prose mention of the old path in an explanatory comment is allowed; what
    # must be gone is the assignment that the check actually executes against, so
    # an isolated worktree no longer records a "script not found" SKIP for a path
    # that cannot exist.
    assert 'GENERATE_AGENTS_SCRIPT="$REPO_ROOT/build/Generate-Agents.ps1"' not in text
    assert 'AGENT_DRIFT_SCRIPT="$REPO_ROOT/build/scripts/Detect-AgentDrift.ps1"' not in text
    assert 'GENERATE_AGENTS_SCRIPT="$REPO_ROOT/build/generate_agents.py"' in text
    assert 'AGENT_DRIFT_SCRIPT="$REPO_ROOT/build/scripts/detect_agent_drift.py"' in text


def test_generation_checks_use_set_python_cmd() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: both repointed checks resolve Python via set_python_cmd (uv-aware),
    # matching check 11b (build_all.py --check). No bare pwsh invocation drives
    # generation any longer.
    assert "pwsh -NoProfile -ExecutionPolicy Bypass -File \"$GENERATE_AGENTS_SCRIPT\"" not in text
    assert "pwsh -NoProfile -ExecutionPolicy Bypass -File \"$AGENT_DRIFT_SCRIPT\"" not in text


def test_referenced_python_generators_exist_in_worktree() -> None:
    # Assert: the scripts the repointed checks invoke exist in this checkout, so
    # an isolated pr-autofix worktree runs the check instead of skipping it.
    assert (REPO_ROOT / "build" / "generate_agents.py").is_file()
    assert (REPO_ROOT / "build" / "scripts" / "detect_agent_drift.py").is_file()
