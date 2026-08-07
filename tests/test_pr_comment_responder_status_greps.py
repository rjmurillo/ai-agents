"""Regression coverage for pr-comment-responder comment-map status greps.

Issue #4034: the workflow greps searched for ``Status: [X]`` while the
comment-map detail field emits ``**Status**: [X]``. The old patterns counted
zero pending, complete, and wontfix comments, which made the gates dead.

PR #4277 review follow-up: the ``Comment Map Status Vocabulary`` section still
published one dead example, ``grep -Ec "Status: \\[NEW\\]|Status:
\\[ACKNOWLEDGED\\]|Status: pending"``. The first detector here missed it twice:
it never listed ``[NEW]``, and it required a quote immediately before each
status token, so alternatives after a ``|`` were invisible. The detector below
flags any unbolded status field anywhere in a carrier.
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

# Carriers that document the status vocabulary. The .prompt.md carrier and the
# gates references carry the greps but not the vocabulary section.
VOCABULARY_HEADING = "## Comment Map Status Vocabulary"

PENDING_STATUS_PATTERNS = (
    r"^\*\*Status\*\*: \[ACKNOWLEDGED\]",
    r"^\*\*Status\*\*: pending",
)
TERMINAL_STATUS_PATTERNS = (
    r"^\*\*Status\*\*: \[COMPLETE\]",
    r"^\*\*Status\*\*: \[WONTFIX\]",
)
REQUIRED_PATTERN_TEXT = (*PENDING_STATUS_PATTERNS, *TERMINAL_STATUS_PATTERNS)

# A status field reference that is not the emitted bold form. Matches the
# escaped shell-regex spelling (``Status: \[NEW\]``) and the bare spelling
# (``Status: [NEW]``) regardless of what precedes it, so an alternative buried
# in a ``|`` chain is still caught. The emitted form reads ``**Status**: [NEW]``
# and cannot match, because ``Status`` there is followed by ``**``.
DEAD_STATUS_FIELD_RE = re.compile(
    r"Status: (?:\\?\[(?:NEW|ACKNOWLEDGED|COMPLETE|WONTFIX)\\?\]|pending)"
)

# The fail-closed derivation published in the vocabulary section: pending is
# whatever is not terminal, so a status outside the table stays in the count.
FAIL_CLOSED_DERIVATION = "REMAINING=$((TOTAL - ADDRESSED - WONTFIX))"

GREP_PATTERN_RE = re.compile(r'grep -Ec "([^"]+)"')

# One rendered comment map. Five detail entries, one of them carrying a status
# outside the documented table.
SAMPLE_COMMENT_MAP_LINES = (
    "| 123 | @reviewer | review | file.py#12 | pending | TBD | - |",
    "**Status**: [NEW]",
    "**Status**: [ACKNOWLEDGED]",
    "**Status**: [COMPLETE]",
    "**Status**: [WONTFIX]",
    "**Status**: [ESCALATED]",
)
SAMPLE_TOTAL_COMMENTS = 5


def _count_status(lines: tuple[str, ...] | list[str], patterns: tuple[str, ...]) -> int:
    compiled = [re.compile(pattern) for pattern in patterns]
    return sum(any(pattern.search(line) for pattern in compiled) for line in lines)


def _vocabulary_section(text: str) -> str:
    start = text.index(VOCABULARY_HEADING)
    next_heading = text.find("\n## ", start + len(VOCABULARY_HEADING))
    end = len(text) if next_heading == -1 else next_heading
    return text[start:end]


def _vocabulary_carriers() -> tuple[Path, ...]:
    return tuple(
        path for path in CARRIER_PATHS if VOCABULARY_HEADING in path.read_text(encoding="utf-8")
    )


def test_status_regexes_match_emitted_comment_map_fields() -> None:
    """The shell regexes must match rendered comment-map status fields."""
    assert _count_status(SAMPLE_COMMENT_MAP_LINES, PENDING_STATUS_PATTERNS) == 1
    assert _count_status(SAMPLE_COMMENT_MAP_LINES, TERMINAL_STATUS_PATTERNS) == 2
    assert _count_status(SAMPLE_COMMENT_MAP_LINES, (r"Status: \[ACKNOWLEDGED\]",)) == 0
    assert _count_status(SAMPLE_COMMENT_MAP_LINES, (r"Status: \[COMPLETE\]",)) == 0
    assert _count_status(SAMPLE_COMMENT_MAP_LINES, (r"Status: \[NEW\]",)) == 0


def test_dead_detector_flags_the_pattern_shipped_before_this_fix() -> None:
    """The detector must catch every alternative of the old dead example."""
    dead_line = '`grep -Ec "Status: \\[NEW\\]|Status: \\[ACKNOWLEDGED\\]|Status: pending"`.'
    assert DEAD_STATUS_FIELD_RE.findall(dead_line) == [
        "Status: \\[NEW\\]",
        "Status: \\[ACKNOWLEDGED\\]",
        "Status: pending",
    ]
    assert not DEAD_STATUS_FIELD_RE.search("**Status**: [NEW]")
    assert DEAD_STATUS_FIELD_RE.search("**Status: [NEW]")


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

    dead = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), 1)
        if DEAD_STATUS_FIELD_RE.search(line)
    ]
    assert not dead, (
        f"{path.relative_to(REPO_ROOT)} still references an unbolded status "
        f"field that greps zero rows: {dead}"
    )


@pytest.mark.parametrize(
    "path",
    _vocabulary_carriers(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_vocabulary_section_publishes_fail_closed_derivation(path: Path) -> None:
    """The vocabulary section must show how pending is derived, fail closed."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))

    assert FAIL_CLOSED_DERIVATION in section, (
        f"{path.relative_to(REPO_ROOT)} vocabulary section must publish "
        f"{FAIL_CLOSED_DERIVATION!r}, not an enumerating pending grep"
    )
    assert sorted(GREP_PATTERN_RE.findall(section)) == sorted(TERMINAL_STATUS_PATTERNS), (
        f"{path.relative_to(REPO_ROOT)} vocabulary section must grep only the "
        f"terminal statuses {TERMINAL_STATUS_PATTERNS}"
    )


@pytest.mark.parametrize(
    "path",
    _vocabulary_carriers(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_published_greps_count_a_rendered_comment_map(path: Path) -> None:
    """Run the published patterns: they must count real rows, fail closed."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))
    patterns = tuple(GREP_PATTERN_RE.findall(section))

    terminal = _count_status(SAMPLE_COMMENT_MAP_LINES, patterns)
    remaining = SAMPLE_TOTAL_COMMENTS - terminal

    assert terminal == 2, (
        f"{path.relative_to(REPO_ROOT)} publishes patterns that count "
        f"{terminal} terminal rows in a rendered comment map, expected 2"
    )
    # [NEW], [ACKNOWLEDGED], and the undocumented [ESCALATED] all remain.
    assert remaining == 3
