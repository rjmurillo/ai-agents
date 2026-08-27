"""Regression coverage for pr-comment-responder comment-map status greps.

Issue #4034: the workflow greps searched for ``Status: [X]`` while the
comment-map detail field emits ``**Status**: [X]``. The old patterns counted
zero pending, complete, and wontfix comments, which made the gates dead.

Issue #4054: the vocabulary was published twice, the two copies both omitted
``[DUPLICATE]`` and ``[DEFERRED]``, and the two gate families disagreed about
what an unlisted status meant. Gate 4 and Gate 5 enumerated pending statuses,
so any status outside their list was silently treated as non-pending and the
gate passed; Phase 8.1 subtracted the terminal statuses, so the same status
blocked. Every gate now derives pending by subtracting the terminal count, so
an unrecognized status fails closed everywhere.
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

# The two shell regexes every carrier must publish, quoted verbatim from
# templates/agents/pr-comment-responder.shared.md. TOTAL counts every rendered
# status field; TERMINAL counts the ones the table marks terminal. Pending is
# the difference, never an enumeration, so an unlisted status stays pending.
STATUS_LINE_PATTERN = r"^\*\*Status\*\*: "
TERMINAL_PATTERN = (
    r"^\*\*Status\*\*: "
    r"(\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[0-9]+)"
)
REQUIRED_PATTERN_TEXT = (STATUS_LINE_PATTERN, TERMINAL_PATTERN)

# A status field reference that is not the emitted bold form. Matches the
# escaped shell-regex spelling (``Status: \[NEW\]``) and the bare spelling
# (``Status: [NEW]``) regardless of what precedes it, so an alternative buried
# in a ``|`` chain is still caught. The emitted form reads ``**Status**: [NEW]``
# and cannot match, because ``Status`` there is followed by ``**``.
DEAD_STATUS_FIELD_RE = re.compile(
    r"Status: (?:\\?\[(?:NEW|ACKNOWLEDGED|COMPLETE|WONTFIX|DUPLICATE|DEFERRED)\\?\]"
    r"|pending)"
)

# The fail-closed derivation published in the vocabulary section.
FAIL_CLOSED_DERIVATION = "PENDING=$((TOTAL - TERMINAL))"

# Any quoted argument to a grep invocation, whatever the flags.
GREP_ANY_PATTERN_RE = re.compile(r"grep [^\"\n]*\"([^\"]+)\"")
# Only the counting greps, used to read the vocabulary section's derivation.
GREP_COUNT_PATTERN_RE = re.compile(r'grep -Ec "([^"]+)"')

# A grep argument that enumerates pending statuses instead of subtracting the
# terminal ones. This is the fail-open shape issue #4054 reports.
ENUMERATED_PENDING_RE = re.compile(r"\\\[(?:NEW|ACKNOWLEDGED)\\\]|Status\\?\*?\*?: pending")

# One rendered comment map. Eight detail entries: four terminal, and four that
# must stay pending, including a bare [DEFERRED] with no tracking reference and
# an invented [BOGUS] status that appears in no table.
SAMPLE_COMMENT_MAP_LINES = (
    "| 123 | @reviewer | review | file.py#12 | pending | TBD | - |",
    "**Status**: [NEW]",
    "**Status**: [ACKNOWLEDGED]",
    "**Status**: [COMPLETE]",
    "**Status**: [WONTFIX]",
    "**Status**: [DUPLICATE]",
    "**Status**: [DEFERRED] Refs #4054",
    "**Status**: [DEFERRED]",
    "**Status**: [BOGUS]",
)
SAMPLE_TOTAL_STATUS_LINES = 8
SAMPLE_TERMINAL_LINES = 4

VOCABULARY_ROW_RE = re.compile(
    r"^\| `\[(?P<status>[A-Z]+)\][^`]*` \| [^|]+ \| (?P<terminal>[^|]+)\|"
)
TABLE_HEADER = "| Status | Meaning |"


def _count_matching(lines: tuple[str, ...], pattern: str) -> int:
    compiled = re.compile(pattern)
    return sum(1 for line in lines if compiled.search(line))


def _vocabulary_section(text: str) -> str:
    start = text.index(VOCABULARY_HEADING)
    next_heading = text.find("\n## ", start + len(VOCABULARY_HEADING))
    end = len(text) if next_heading == -1 else next_heading
    return text[start:end]


def _vocabulary_carriers() -> tuple[Path, ...]:
    return tuple(
        path for path in CARRIER_PATHS if VOCABULARY_HEADING in path.read_text(encoding="utf-8")
    )


def _terminal_statuses_in_pattern(pattern: str) -> set[str]:
    return set(re.findall(r"\\\[([A-Z]+)\\\]", pattern))


def test_status_regexes_match_emitted_comment_map_fields() -> None:
    """The shell regexes must match rendered comment-map status fields."""
    assert _count_matching(SAMPLE_COMMENT_MAP_LINES, STATUS_LINE_PATTERN) == (
        SAMPLE_TOTAL_STATUS_LINES
    )
    assert _count_matching(SAMPLE_COMMENT_MAP_LINES, TERMINAL_PATTERN) == (
        SAMPLE_TERMINAL_LINES
    )
    assert _count_matching(SAMPLE_COMMENT_MAP_LINES, r"Status: \[COMPLETE\]") == 0
    assert _count_matching(SAMPLE_COMMENT_MAP_LINES, r"Status: \[NEW\]") == 0


def test_bare_deferred_is_not_terminal() -> None:
    """[DEFERRED] without a tracking reference must stay pending."""
    assert _count_matching(("**Status**: [DEFERRED]",), TERMINAL_PATTERN) == 0
    assert _count_matching(("**Status**: [DEFERRED] Refs #4054",), TERMINAL_PATTERN) == 1
    assert _count_matching(("**Status**: [DEFERRED] Refs #",), TERMINAL_PATTERN) == 0


def test_dead_detector_flags_the_pattern_shipped_before_this_fix() -> None:
    """The detector must catch every alternative of the old dead example."""
    dead_line = '`grep -Ec "Status: \\[NEW\\]|Status: \\[ACKNOWLEDGED\\]|Status: pending"`.'
    assert DEAD_STATUS_FIELD_RE.findall(dead_line) == [
        "Status: \\[NEW\\]",
        "Status: \\[ACKNOWLEDGED\\]",
        "Status: pending",
    ]
    assert DEAD_STATUS_FIELD_RE.search("Status: [DUPLICATE]")
    assert DEAD_STATUS_FIELD_RE.search("Status: [DEFERRED]")
    assert not DEAD_STATUS_FIELD_RE.search("**Status**: [NEW]")
    assert DEAD_STATUS_FIELD_RE.search("**Status: [NEW]")


def test_enumerated_pending_detector_flags_the_shape_shipped_before_this_fix() -> None:
    """The detector must catch the fail-open greps issue #4054 reports."""
    gate_five = (
        r"^\*\*Status\*\*: pending|^\*\*Status\*\*: \[ACKNOWLEDGED\]"
        r"|^\*\*Status\*\*: \[NEW\]"
    )
    assert ENUMERATED_PENDING_RE.search(gate_five)
    assert ENUMERATED_PENDING_RE.search(r"^\*\*Status\*\*: \[NEW\]")
    assert not ENUMERATED_PENDING_RE.search(TERMINAL_PATTERN)
    assert not ENUMERATED_PENDING_RE.search(STATUS_LINE_PATTERN)


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
            f"status pattern {pattern_text!r} for issues #4034 and #4054"
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
    CARRIER_PATHS,
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_no_carrier_enumerates_pending_statuses(path: Path) -> None:
    """No gate may enumerate pending statuses; an unlisted status must block."""
    text = path.read_text(encoding="utf-8")

    offenders = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), 1)
        for pattern in GREP_ANY_PATTERN_RE.findall(line)
        if ENUMERATED_PENDING_RE.search(pattern)
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} still enumerates pending statuses, so a "
        f"status outside the table is counted as non-pending and the gate passes "
        f"(issue #4054): {offenders}"
    )


@pytest.mark.parametrize(
    "path",
    _vocabulary_carriers(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_vocabulary_is_published_exactly_once(path: Path) -> None:
    """One table, one vocabulary. A second copy is how statuses go missing."""
    text = path.read_text(encoding="utf-8")
    assert text.count(TABLE_HEADER) == 1, (
        f"{path.relative_to(REPO_ROOT)} publishes {text.count(TABLE_HEADER)} status "
        f"vocabulary tables; issue #4054 requires exactly one"
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
    assert sorted(GREP_COUNT_PATTERN_RE.findall(section)) == sorted(REQUIRED_PATTERN_TEXT), (
        f"{path.relative_to(REPO_ROOT)} vocabulary section must count only the "
        f"status-line total and the terminal statuses {REQUIRED_PATTERN_TEXT}"
    )


@pytest.mark.parametrize(
    "path",
    _vocabulary_carriers(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_table_terminal_column_agrees_with_the_terminal_grep(path: Path) -> None:
    """Every status the table calls terminal must be in the terminal grep."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))

    tabled_terminal: set[str] = set()
    tabled_pending: set[str] = set()
    for line in section.splitlines():
        match = VOCABULARY_ROW_RE.match(line)
        if match is None:
            continue
        target = (
            tabled_terminal
            if match.group("terminal").strip().startswith("Yes")
            else tabled_pending
        )
        target.add(match.group("status"))

    assert tabled_terminal, f"{path.relative_to(REPO_ROOT)} table parsed no terminal rows"
    assert tabled_terminal == _terminal_statuses_in_pattern(TERMINAL_PATTERN), (
        f"{path.relative_to(REPO_ROOT)} table marks {sorted(tabled_terminal)} terminal "
        f"but the grep matches {sorted(_terminal_statuses_in_pattern(TERMINAL_PATTERN))}"
    )
    assert not tabled_pending & tabled_terminal
    assert tabled_pending == {"NEW", "ACKNOWLEDGED"}


@pytest.mark.parametrize(
    "path",
    _vocabulary_carriers(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_published_greps_count_a_rendered_comment_map(path: Path) -> None:
    """Run the published patterns: they must count real rows, fail closed."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))
    patterns = GREP_COUNT_PATTERN_RE.findall(section)

    total = _count_matching(SAMPLE_COMMENT_MAP_LINES, STATUS_LINE_PATTERN)
    terminal = _count_matching(SAMPLE_COMMENT_MAP_LINES, TERMINAL_PATTERN)
    assert set(patterns) == {STATUS_LINE_PATTERN, TERMINAL_PATTERN}

    pending = total - terminal

    assert total == SAMPLE_TOTAL_STATUS_LINES
    assert terminal == SAMPLE_TERMINAL_LINES
    # [NEW], [ACKNOWLEDGED], the untracked [DEFERRED], and the invented [BOGUS]
    # all remain pending. The unlisted status blocks instead of passing.
    assert pending == 4
