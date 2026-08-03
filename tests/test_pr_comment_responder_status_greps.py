"""Regression coverage for pr-comment-responder comment-map status greps.

Issue #4034: the workflow greps searched for ``Status: [X]`` while the
comment-map detail field emits ``**Status**: [X]``. The old patterns counted
zero pending, complete, and wontfix comments, which made the gates dead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The shared template generates VS Code and Copilot CLI source copies via
# build/generate_agents.py. src/claude and installed agent copies are
# hand-maintained per ADR-036 and install-parity rules. The skill reference is
# generated from .claude/skills/pr-comment-responder/ by build_all.py.
CARRIER_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "templates/agents/pr-comment-responder.shared.md",
    REPO_ROOT / ".claude/agents/pr-comment-responder.md",
    REPO_ROOT / ".github/agents/pr-comment-responder.agent.md",
    REPO_ROOT / ".github/agents/pr-comment-responder.prompt.md",
    REPO_ROOT / "src/claude/pr-comment-responder.md",
    REPO_ROOT / "src/copilot-cli/agents/pr-comment-responder.agent.md",
    REPO_ROOT / "src/vs-code-agents/pr-comment-responder.agent.md",
    REPO_ROOT / ".claude/skills/pr-comment-responder/references/gates.md",
    REPO_ROOT / "src/copilot-cli/skills/pr-comment-responder/references/gates.md",
)

PENDING_STATUS_PATTERNS = (
    r"^\*\*Status\*\*: \[ACKNOWLEDGED\]",
    r"^\*\*Status\*\*: pending",
)
TERMINAL_STATUS_PATTERNS = (
    r"^\*\*Status\*\*: \[COMPLETE\]",
    r"^\*\*Status\*\*: \[WONTFIX\]",
)
REQUIRED_PATTERN_TEXT = (*PENDING_STATUS_PATTERNS, *TERMINAL_STATUS_PATTERNS)

DEAD_GREP_PATTERNS = (
    r'grep[^\n]*"Status: \\[ACKNOWLEDGED\\]',
    r'grep[^\n]*"Status: pending',
    r'grep[^\n]*"Status: \\[COMPLETE\\]',
    r'grep[^\n]*"Status: \\[WONTFIX\\]',
)


def _count_status(lines: list[str], patterns: tuple[str, ...]) -> int:
    compiled = [re.compile(pattern) for pattern in patterns]
    return sum(any(pattern.search(line) for pattern in compiled) for line in lines)


def test_status_regexes_match_emitted_comment_map_fields() -> None:
    """The shell regexes must match rendered comment-map status fields."""
    comment_map_lines = [
        "| 123 | @reviewer | review | file.py#12 | pending | TBD | - |",
        "**Status**: [ACKNOWLEDGED]",
        "**Status**: pending",
        "**Status**: [COMPLETE]",
        "**Status**: [WONTFIX]",
    ]

    assert _count_status(comment_map_lines, PENDING_STATUS_PATTERNS) == 2
    assert _count_status(comment_map_lines, TERMINAL_STATUS_PATTERNS) == 2
    assert _count_status(comment_map_lines, (r"Status: \[ACKNOWLEDGED\]",)) == 0
    assert _count_status(comment_map_lines, (r"Status: \[COMPLETE\]",)) == 0


@pytest.mark.parametrize(
    "path",
    CARRIER_PATHS,
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_status_greps_anchor_to_bold_comment_map_field(path: Path) -> None:
    """Every carrier must grep the emitted bold status field, not dead text."""
    assert path.exists(), f"Expected carrier at {path.relative_to(REPO_ROOT)}"
    text = path.read_text(encoding="utf-8")

    for pattern_text in REQUIRED_PATTERN_TEXT:
        assert pattern_text in text, (
            f"{path.relative_to(REPO_ROOT)} must use anchored comment-map "
            f"status pattern {pattern_text!r} for issue #4034"
        )

    for dead_pattern in DEAD_GREP_PATTERNS:
        assert not re.search(dead_pattern, text), (
            f"{path.relative_to(REPO_ROOT)} still has an unanchored dead "
            f"status grep matching {dead_pattern!r}"
        )
