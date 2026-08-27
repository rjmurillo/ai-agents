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

The counting tests read the quoted argument out of the carrier and hand it to a
real ``grep -Ec`` subprocess against a rendered comment map. A Python ``re``
mirror cannot catch a shell-side typo, because the engines disagree silently:
``\\d`` is a digit class in Python and a literal ``d`` in POSIX ERE. See
``test_python_regex_mirror_would_miss_an_ere_typo``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

GREP = shutil.which("grep")

# The shared template generates VS Code and Copilot CLI source copies via
# build/generate_agents.py. src/claude and installed agent copies are
# hand-maintained per ADR-036 and install-parity rules. The skill reference is
# generated from .claude/skills/pr-comment-responder/ by build_all.py.
#
# Every carrier that publishes the status greps AND the vocabulary table that
# defines them. Hardcoded, never discovered from file content: a carrier that
# loses its table must fail this suite, not quietly drop out of it.
VOCABULARY_CARRIERS: tuple[Path, ...] = (
    REPO_ROOT / "templates/agents/pr-comment-responder.shared.md",
    REPO_ROOT / ".claude/agents/pr-comment-responder.md",
    REPO_ROOT / ".github/agents/pr-comment-responder.agent.md",
    REPO_ROOT / ".github/agents/pr-comment-responder.prompt.md",
    REPO_ROOT / "src/claude/pr-comment-responder.md",
    REPO_ROOT / "src/copilot-cli/agents/pr-comment-responder.agent.md",
    REPO_ROOT / "src/vs-code-agents/pr-comment-responder.agent.md",
)

# Skill references that publish the greps and point at the agent's one table
# rather than restating it. They carry the gates, not the vocabulary.
GATE_REFERENCE_CARRIERS: tuple[Path, ...] = (
    REPO_ROOT / ".claude/skills/pr-comment-responder/references/gates.md",
    REPO_ROOT / "src/copilot-cli/skills/pr-comment-responder/references/gates.md",
)

CARRIER_PATHS: tuple[Path, ...] = VOCABULARY_CARRIERS + GATE_REFERENCE_CARRIERS

VOCABULARY_HEADING = "## Comment Map Status Vocabulary"

# The shell regexes every carrier must publish, quoted verbatim from
# templates/agents/pr-comment-responder.shared.md. TOTAL counts every rendered
# status field; TERMINAL counts the ones the table marks terminal. Pending is
# the difference, never an enumeration, so an unlisted status stays pending.
#
# The trailing ``[[:space:]]*$`` is load-bearing. Without it a matching prefix
# was enough, so ``[COMPLETE]oops`` and ``[DEFERRED] Refs #4054garbage``
# counted as terminal and cleared the gate.
STATUS_LINE_PATTERN = r"^\*\*Status\*\*: "
TERMINAL_BODY = r"(\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[0-9]+)"
END_ANCHOR = r"[[:space:]]*$"
TERMINAL_PATTERN = STATUS_LINE_PATTERN + TERMINAL_BODY + END_ANCHOR
# The failure diagnostic pipes through `grep -En`, which prefixes each line
# with `N:`, so the complement drops the `^` anchor and keeps everything else.
COMPLEMENT_PATTERN = r"\*\*Status\*\*: " + TERMINAL_BODY + END_ANCHOR
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

# The guard that proves the comment map exists before any gate counts it.
MAP_EXISTS_GUARD = 'if [ ! -f "$COMMENT_MAP" ]; then'

# Any quoted argument to a grep invocation, whatever the flags.
GREP_ANY_PATTERN_RE = re.compile(r"grep [^\"\n]*\"([^\"]+)\"")
# Counting greps, complement greps, and the two named assignments.
GREP_COUNT_PATTERN_RE = re.compile(r'grep -Ec "([^"]+)"')
GREP_COMPLEMENT_PATTERN_RE = re.compile(r'grep -Ev "([^"]+)"')
TERMINAL_ASSIGNMENT_RE = re.compile(r'TERMINAL=\$\(grep -Ec "([^"]+)"')
TOTAL_ASSIGNMENT_RE = re.compile(r'TOTAL=\$\(grep -Ec "([^"]+)"')

# A grep argument that enumerates pending statuses instead of subtracting the
# terminal ones. This is the fail-open shape issue #4054 reports.
ENUMERATED_PENDING_RE = re.compile(r"\\\[(?:NEW|ACKNOWLEDGED)\\\]|Status\\?\*?\*?: pending")

# One rendered comment map. Eleven detail entries: five terminal, six that must
# stay pending. The pending six cover every way a status can fail to be
# terminal: not yet worked ([NEW], [ACKNOWLEDGED]), a [DEFERRED] with no
# tracking reference, an invented [BOGUS] that appears in no table, and two
# malformed values whose valid prefix used to be enough to pass the gate.
SAMPLE_COMMENT_MAP_LINES: tuple[str, ...] = (
    "| 123 | @reviewer | review | file.py#12 | pending | TBD | - |",
    "**Status**: [NEW]",
    "**Status**: [ACKNOWLEDGED]",
    "**Status**: [COMPLETE]",
    "**Status**: [WONTFIX]",
    "**Status**: [DUPLICATE]",
    "**Status**: [DEFERRED] Refs #4054",
    "**Status**: [COMPLETE]  ",
    "**Status**: [DEFERRED]",
    "**Status**: [BOGUS]",
    "**Status**: [COMPLETE]oops",
    "**Status**: [DEFERRED] Refs #4054garbage",
)
SAMPLE_TOTAL_STATUS_LINES = 11
SAMPLE_TERMINAL_LINES = 5
SAMPLE_PENDING_LINES = SAMPLE_TOTAL_STATUS_LINES - SAMPLE_TERMINAL_LINES

VOCABULARY_ROW_RE = re.compile(
    r"^\| `\[(?P<status>[A-Z]+)\][^`]*` \| [^|]+ \| (?P<terminal>[^|]+)\|"
)
TABLE_HEADER = "| Status | Meaning |"

BASH_FENCE_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)

requires_grep = pytest.mark.skipif(GREP is None, reason="grep is not on PATH")


def _render_comment_map(tmp_path: Path, lines: Sequence[str]) -> Path:
    target = tmp_path / "comments.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _grep_count(pattern: str, comment_map: Path) -> int:
    """Run the published ``grep -Ec PATTERN FILE`` and return its real stdout.

    Exercises the shipped shell command, not a Python translation of it.
    ``grep -c`` exits 1 and prints ``0`` when nothing matches; exit 2 means
    grep refused the pattern, which is the failure this runner exists to
    surface.
    """
    assert GREP is not None
    proc = subprocess.run(
        [GREP, "-Ec", pattern, str(comment_map)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in (0, 1), (
        f"grep rejected the published pattern {pattern!r} "
        f"(exit {proc.returncode}): {proc.stderr.strip()}"
    )
    return int(proc.stdout.strip())


def _vocabulary_section(text: str) -> str:
    start = text.index(VOCABULARY_HEADING)
    next_heading = text.find("\n## ", start + len(VOCABULARY_HEADING))
    end = len(text) if next_heading == -1 else next_heading
    return text[start:end]


def _terminal_statuses_in_pattern(pattern: str) -> set[str]:
    return set(re.findall(r"\\\[([A-Z]+)\\\]", pattern))


def _carrier_id(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


# The published patterns, executed by the shell they are written for.


@requires_grep
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_published_greps_count_a_rendered_comment_map(path: Path, tmp_path: Path) -> None:
    """Run each carrier's own shell greps: they must count real rows.

    The patterns are read out of the carrier and handed to grep verbatim, so a
    typo in the shipped command fails here rather than shipping.
    """
    text = path.read_text(encoding="utf-8")
    comment_map = _render_comment_map(tmp_path, SAMPLE_COMMENT_MAP_LINES)

    published_total = TOTAL_ASSIGNMENT_RE.findall(text)
    published_terminal = TERMINAL_ASSIGNMENT_RE.findall(text)
    assert published_total, f"{_carrier_id(path)} publishes no TOTAL counting grep"
    assert published_terminal, f"{_carrier_id(path)} publishes no TERMINAL counting grep"

    for pattern in published_total:
        assert _grep_count(pattern, comment_map) == SAMPLE_TOTAL_STATUS_LINES

    for pattern in published_terminal:
        terminal = _grep_count(pattern, comment_map)
        assert terminal == SAMPLE_TERMINAL_LINES, (
            f"{_carrier_id(path)} TERMINAL grep counted {terminal}, expected "
            f"{SAMPLE_TERMINAL_LINES}; pattern {pattern!r}"
        )
        assert SAMPLE_TOTAL_STATUS_LINES - terminal == SAMPLE_PENDING_LINES


@requires_grep
def test_end_anchor_keeps_malformed_terminal_values_pending(tmp_path: Path) -> None:
    """Trailing garbage after a valid prefix must not count as terminal."""
    malformed = (
        "**Status**: [COMPLETE]oops",
        "**Status**: [DEFERRED] Refs #4054garbage",
        "**Status**: [WONTFIX] but actually not",
        "**Status**: [DEFERRED] Refs #",
        "**Status**: [DEFERRED]",
    )
    comment_map = _render_comment_map(tmp_path, malformed)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0

    well_formed = (
        "**Status**: [COMPLETE]",
        "**Status**: [WONTFIX]",
        "**Status**: [DUPLICATE]",
        "**Status**: [DEFERRED] Refs #4054",
        "**Status**: [COMPLETE]\t",
        "**Status**: [DEFERRED] Refs #4054 ",
    )
    comment_map = _render_comment_map(tmp_path, well_formed)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == len(well_formed)


@requires_grep
def test_unanchored_terminal_pattern_is_the_bug_the_anchor_fixes(tmp_path: Path) -> None:
    """Negative control: drop the anchor and the malformed values pass."""
    unanchored = STATUS_LINE_PATTERN + TERMINAL_BODY
    comment_map = _render_comment_map(tmp_path, SAMPLE_COMMENT_MAP_LINES)

    assert _grep_count(unanchored, comment_map) == SAMPLE_TERMINAL_LINES + 2
    assert _grep_count(TERMINAL_PATTERN, comment_map) == SAMPLE_TERMINAL_LINES


@requires_grep
def test_python_regex_mirror_would_miss_an_ere_typo(tmp_path: Path) -> None:
    """Why these tests shell out instead of mirroring the pattern in Python.

    ``\\d`` is a digit class to Python and a literal ``d`` to POSIX ERE. A
    Python mirror of the shipped command accepts the typo and reports the
    correct count; the shell that actually runs it reports zero. Neither
    engine errors, so only running the real command catches it.
    """
    typo = r"^\*\*Status\*\*: \[DEFERRED\] Refs #\d+"
    lines = ("**Status**: [DEFERRED] Refs #4054",)
    comment_map = _render_comment_map(tmp_path, lines)

    assert _grep_count(typo, comment_map) == 0
    assert sum(1 for line in lines if re.search(typo, line)) == 1


@requires_grep
def test_grep_runner_fails_loudly_on_a_pattern_grep_refuses(tmp_path: Path) -> None:
    """Negative control: an uncompilable ERE must fail, not read as zero."""
    comment_map = _render_comment_map(tmp_path, SAMPLE_COMMENT_MAP_LINES)
    with pytest.raises(AssertionError, match="grep rejected the published pattern"):
        _grep_count(r"^\*\*Status\*\*: [[:bogus:]]", comment_map)


# Every gate must publish the one canonical pattern, not a near copy.


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_gate_publishes_the_canonical_patterns(path: Path) -> None:
    """Per-gate, not per-file: one gate dropping [DUPLICATE] must fail.

    Asserting the canonical pattern appears somewhere in the file lets a second
    gate ship a narrower terminal list unnoticed. Every counting grep in the
    carrier is checked instead.
    """
    text = path.read_text(encoding="utf-8")

    counting = GREP_COUNT_PATTERN_RE.findall(text)
    assert counting, f"{_carrier_id(path)} publishes no counting grep"
    offenders = [p for p in counting if p not in REQUIRED_PATTERN_TEXT]
    assert not offenders, (
        f"{_carrier_id(path)} publishes counting grep(s) that are neither the "
        f"status-line total nor the canonical terminal pattern: {offenders}"
    )

    for pattern in TERMINAL_ASSIGNMENT_RE.findall(text):
        assert pattern == TERMINAL_PATTERN, (
            f"{_carrier_id(path)} assigns TERMINAL from {pattern!r}, not the "
            f"canonical {TERMINAL_PATTERN!r}"
        )
    for pattern in TOTAL_ASSIGNMENT_RE.findall(text):
        assert pattern == STATUS_LINE_PATTERN, (
            f"{_carrier_id(path)} assigns TOTAL from {pattern!r}, not the "
            f"canonical {STATUS_LINE_PATTERN!r}"
        )
    for pattern in GREP_COMPLEMENT_PATTERN_RE.findall(text):
        assert pattern == COMPLEMENT_PATTERN, (
            f"{_carrier_id(path)} diagnoses with {pattern!r}, which is not the "
            f"complement of the canonical terminal pattern"
        )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_counting_gate_proves_the_comment_map_exists(path: Path) -> None:
    """A missing map must block, not compute zero pending and pass.

    ``grep -Ec`` on an absent file exits non-zero and prints nothing, ``|| true``
    turns that into an empty string, and ``$(( ))`` reads an empty string as 0.
    Every fenced block that counts the map must prove it exists first.
    """
    text = path.read_text(encoding="utf-8")

    unguarded = []
    for block in BASH_FENCE_RE.findall(text):
        counting = [m for m in GREP_COUNT_PATTERN_RE.finditer(block) if '"$COMMENT_MAP"' in block]
        if not counting:
            continue
        first_count = min(m.start() for m in counting)
        guard = block.find(MAP_EXISTS_GUARD)
        if guard == -1 or guard > first_count:
            unguarded.append(block.strip().splitlines()[0])

    assert not unguarded, (
        f"{_carrier_id(path)} counts the comment map without proving it exists "
        f"first, so an absent map computes zero pending and clears the gate "
        f"(issue #4054): {unguarded}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_status_greps_anchor_to_bold_comment_map_field(path: Path) -> None:
    """Every carrier must grep the emitted bold status field, not dead text."""
    assert path.exists(), f"Expected carrier at {_carrier_id(path)}"
    text = path.read_text(encoding="utf-8")

    for pattern_text in REQUIRED_PATTERN_TEXT:
        assert pattern_text in text, (
            f"{_carrier_id(path)} must use anchored comment-map "
            f"status pattern {pattern_text!r} for issues #4034 and #4054"
        )

    dead = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), 1)
        if DEAD_STATUS_FIELD_RE.search(line)
    ]
    assert not dead, (
        f"{_carrier_id(path)} still references an unbolded status "
        f"field that greps zero rows: {dead}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
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
        f"{_carrier_id(path)} still enumerates pending statuses, so a "
        f"status outside the table is counted as non-pending and the gate passes "
        f"(issue #4054): {offenders}"
    )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_phase_eight_one_blocks_instead_of_warning(path: Path) -> None:
    """Phase 8.1 is a gate. A warning-only copy lets pending comments through."""
    text = path.read_text(encoding="utf-8")
    if "Phase 8.1" not in text:
        pytest.skip(f"{_carrier_id(path)} carries no Phase 8.1 sub-gate")

    assert "[WARNING] INCOMPLETE" not in text, (
        f"{_carrier_id(path)} Phase 8.1 warns instead of blocking, so pending "
        f"comments do not stop the run (issue #4054)"
    )
    assert "[BLOCKED] INCOMPLETE" in text, (
        f"{_carrier_id(path)} Phase 8.1 must print a [BLOCKED] diagnostic"
    )


# The vocabulary table is the single authority the greps are derived from.


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_vocabulary_is_published_exactly_once(path: Path) -> None:
    """One table, one vocabulary. A second copy is how statuses go missing."""
    text = path.read_text(encoding="utf-8")
    assert text.count(TABLE_HEADER) == 1, (
        f"{_carrier_id(path)} publishes {text.count(TABLE_HEADER)} status "
        f"vocabulary tables; issue #4054 requires exactly one"
    )


@pytest.mark.parametrize("path", GATE_REFERENCE_CARRIERS, ids=_carrier_id)
def test_gate_references_do_not_restate_the_vocabulary(path: Path) -> None:
    """The skill reference points at the agent's table; it never copies it."""
    text = path.read_text(encoding="utf-8")
    assert TABLE_HEADER not in text, (
        f"{_carrier_id(path)} restates the status vocabulary; a second copy is "
        f"how [DUPLICATE] and [DEFERRED] went missing (issue #4054)"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_vocabulary_section_publishes_fail_closed_derivation(path: Path) -> None:
    """The vocabulary section must show how pending is derived, fail closed."""
    section = _vocabulary_section(path.read_text(encoding="utf-8"))

    assert FAIL_CLOSED_DERIVATION in section, (
        f"{_carrier_id(path)} vocabulary section must publish "
        f"{FAIL_CLOSED_DERIVATION!r}, not an enumerating pending grep"
    )
    assert sorted(GREP_COUNT_PATTERN_RE.findall(section)) == sorted(REQUIRED_PATTERN_TEXT), (
        f"{_carrier_id(path)} vocabulary section must count only the "
        f"status-line total and the terminal statuses {REQUIRED_PATTERN_TEXT}"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
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
            tabled_terminal if match.group("terminal").strip().startswith("Yes") else tabled_pending
        )
        target.add(match.group("status"))

    assert tabled_terminal, f"{_carrier_id(path)} table parsed no terminal rows"
    assert tabled_terminal == _terminal_statuses_in_pattern(TERMINAL_PATTERN), (
        f"{_carrier_id(path)} table marks {sorted(tabled_terminal)} terminal "
        f"but the grep matches {sorted(_terminal_statuses_in_pattern(TERMINAL_PATTERN))}"
    )
    assert not tabled_pending & tabled_terminal
    assert tabled_pending == {"NEW", "ACKNOWLEDGED"}


# The Python-side detectors this suite uses to scan the carriers.


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


def test_terminal_statuses_in_pattern_reads_the_alternation() -> None:
    """The table-vs-grep comparison depends on parsing the alternation."""
    assert _terminal_statuses_in_pattern(TERMINAL_PATTERN) == {
        "COMPLETE",
        "WONTFIX",
        "DUPLICATE",
        "DEFERRED",
    }
    assert _terminal_statuses_in_pattern(STATUS_LINE_PATTERN) == set()
