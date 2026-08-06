"""Regression guards for the pr-autofix late base-refresh recheck."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PR_AUTOFIX_CARRIERS = (
    REPO_ROOT / ".claude" / "commands" / "pr-autofix.md",
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-autofix" / "SKILL.md",
)


def _stale_merge_section(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index("- **Stale merge-state cache**:")
    end = text.index("- **Stale CI check**:", start)
    return text[start:end]


@pytest.mark.parametrize(
    "path",
    PR_AUTOFIX_CARRIERS,
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_late_base_refresh_has_terminal_state_recheck(path: Path) -> None:
    section = _stale_merge_section(path)

    live_check = section.index("check_pr_live_state.py")
    skip_gate = section.index('if [ "$LIVE_ACTION" = "SKIP" ]; then')
    release = section.index("pr_autofix_lease.py")
    refresh = section.index("Run a safe base-ref refresh")

    assert live_check < skip_gate < release < refresh
    assert "exit 0" in section[skip_gate:refresh]


@pytest.mark.parametrize(
    "path",
    PR_AUTOFIX_CARRIERS,
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_late_base_refresh_evidence_requires_live_state_output(path: Path) -> None:
    section = _stale_merge_section(path)

    assert "live-state recheck output" in section
