"""Tests for the shared CLI smoke path list (REQ-047 AC10, issue #6069).

One module feeds the lefthook gate and the CI path filter. This file covers the
glob tuples and the match decision; ``test_cli_smoke_paths_diff.py``,
``test_cli_smoke_paths_cli.py``, and ``test_cli_smoke_paths_drift.py`` cover the
diff, the CLI, and the lefthook and workflow drift guards.
"""

from __future__ import annotations

import pytest

from scripts.validation import cli_smoke_paths as paths


def _should_run(changed: list[str]) -> bool:
    return bool(paths.matched_paths(changed))


def test_union_contains_every_hook_and_plugin_glob() -> None:
    assert set(paths.HOOK_E2E_GLOBS) <= set(paths.SMOKE_PATH_GLOBS)
    assert set(paths.PLUGIN_E2E_GLOBS) <= set(paths.SMOKE_PATH_GLOBS)


def test_union_has_no_duplicates() -> None:
    assert len(paths.SMOKE_PATH_GLOBS) == len(set(paths.SMOKE_PATH_GLOBS))


@pytest.mark.parametrize(
    "changed",
    [
        ".claude-plugin/marketplace.json",
        "src/claude/.claude-plugin/plugin.json",
        "src/claude/skills/build/SKILL.md",
        "src/copilot-cli/hooks/hooks.json",
        "src/copilot-cli/agents/analyst.agent.md",
        ".claude/skills/build/SKILL.md",
        ".claude/hooks/pre_tool_use.py",
        "tests/e2e/test_plugin_load_smoke.py",
        "tests/e2e/test_cli_hook_e2e.py",
        ".github/workflows/plugin-cli-smoke.yml",
        "scripts/validation/cli_smoke_paths.py",
        ".github/plugin/marketplace.json",
        "scripts/validation/assert_smoke_ran.py",
        "scripts/validation/smoke_quota_report.py",
        "scripts/validation/assert_trusted_smoke_context.py",
        "scripts/validation/smoke_result.py",
        "tests/integration/test_e2e_install.py",
        "tests/e2e/copilot_hook_probe.py",
        "tests/e2e/smoke_skip_policy.py",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_smoke_paths_trigger_a_run(changed: str) -> None:
    assert _should_run([changed]) is True


@pytest.mark.parametrize(
    "changed",
    [
        "README.md",
        "docs/COST-GOVERNANCE.md",
        "scripts/ci/invoke_claude_review.py",
        ".github/workflows/pytest.yml",
        ".github/workflows/claude.yml",
        "tests/test_something.py",
    ],
)
def test_non_smoke_paths_do_not_trigger_a_run(changed: str) -> None:
    assert _should_run([changed]) is False


def test_empty_change_list_does_not_run() -> None:
    assert _should_run([]) is False


def test_one_matching_path_among_many_triggers_a_run() -> None:
    assert _should_run(["README.md", "src/claude/skills/x.md", "docs/a.md"]) is True
