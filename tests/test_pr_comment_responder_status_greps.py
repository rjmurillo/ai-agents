# taste-lint: ignore file-size, one contract across nine carriers; splitting it
# would duplicate the carrier list, the canonical patterns, and the comment-map
# fixtures that every case here shares.
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

Subtraction alone still fails open on a corrupted map: strip every
``**Status**:`` field and both counts read zero, so the difference is zero
pending and the gate clears an artifact that describes nothing. Every gate now
also compares ``TOTAL`` against ``$TOTAL_COMMENTS``, the API count Phase 1
recorded, and blocks when the two disagree.

The counting tests read the quoted argument out of the carrier and hand it to a
real ``grep -Ec`` subprocess against a rendered comment map. A Python ``re``
mirror cannot catch a shell-side typo, because the engines disagree silently:
``\\d`` is a digit class in Python and a literal ``d`` in POSIX ERE. See
``test_python_regex_mirror_would_miss_an_ere_typo``.

The structural tests parse each fenced block separately and hold each one to the
whole derivation. Flattening every grep in a carrier and asking whether the
canonical pattern appears somewhere lets one gate drop a step while a sibling
gate's intact copy keeps the assertion green.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

GREP = shutil.which("grep")
BASH = shutil.which("bash")

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

# The skill entrypoint and its generated plugin copy. They publish completion
# criteria in prose, not the greps, so they carry no derivation fence. They are
# still what an agent reads first, so a stale copy hands out criteria narrower
# than the gates enforce.
SKILL_ENTRYPOINTS: tuple[Path, ...] = (
    REPO_ROOT / ".claude/skills/pr-comment-responder/SKILL.md",
    REPO_ROOT / "src/copilot-cli/skills/pr-comment-responder/SKILL.md",
)

# The four terminal status tokens the vocabulary table publishes. Spelled with
# brackets so a prose mention of the bare word cannot satisfy the assertion.
TERMINAL_STATUS_TOKENS: tuple[str, ...] = (
    "[COMPLETE]",
    "[WONTFIX]",
    "[DUPLICATE]",
    "[DEFERRED]",
)

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
TERMINAL_BODY = r"(\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)"
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

# The two counting assignments as the carriers publish them, shell text and all.
TOTAL_ASSIGNMENT_TEXT = f'TOTAL=$(grep -Ec "{STATUS_LINE_PATTERN}" "$COMMENT_MAP" || true)'
TERMINAL_ASSIGNMENT_TEXT = f'TERMINAL=$(grep -Ec "{TERMINAL_PATTERN}" "$COMMENT_MAP" || true)'

# The guard that proves the map is complete before the subtraction is trusted.
# A map whose status fields were stripped counts zero total and zero terminal,
# so the difference is zero pending and the gate clears an empty artifact.
API_COUNT_INVARIANT = (
    'if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then\n'
    '  echo "[BLOCKED] Comment map carries $TOTAL status fields, '
    'API reported $TOTAL_COMMENTS"\n'
    "  exit 1\n"
    "fi"
)

# Every step a fence that counts the comment map must publish, in this order.
REQUIRED_DERIVATION_STEPS: tuple[str, ...] = (
    MAP_EXISTS_GUARD,
    TOTAL_ASSIGNMENT_TEXT,
    TERMINAL_ASSIGNMENT_TEXT,
    FAIL_CLOSED_DERIVATION,
    API_COUNT_INVARIANT,
)

# The sections that own a counting fence. Hardcoded, never discovered from the
# file: a carrier that loses Gate 4's fence must fail, not drop out of the set.
VOCABULARY_SECTION_KEY = "Comment Map Status Vocabulary"
GATE_SECTION_KEYS: tuple[str, ...] = ("Gate 4", "Gate 5", "Phase 8.1")
SECTION_KEYS: tuple[str, ...] = (VOCABULARY_SECTION_KEY, *GATE_SECTION_KEYS)

EXPECTED_DERIVATION_SECTIONS: dict[Path, frozenset[str]] = {
    **{path: frozenset(SECTION_KEYS) for path in VOCABULARY_CARRIERS},
    **{path: frozenset(GATE_SECTION_KEYS) for path in GATE_REFERENCE_CARRIERS},
}

MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")

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

# One rendered comment map. Thirteen detail entries: five terminal, eight that
# must stay pending. The pending eight cover every way a status can fail to be
# terminal: not yet worked ([NEW], [ACKNOWLEDGED]), a [DEFERRED] with no
# tracking reference, an invented [BOGUS] that appears in no table, two
# malformed values whose valid prefix used to be enough to pass the gate, and
# two unresolvable issue numbers.
#
# ``Refs #0`` and ``Refs #007`` are the guaranteed-non-reference cases. GitHub
# numbers issues and pull requests from 1, so neither can ever resolve. The
# terminal pattern reads ``#[1-9][0-9]*``; the older ``#[0-9]+`` admitted both
# and let deferred work go terminal against a tracking issue nobody can open.
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
    "**Status**: [DEFERRED] Refs #0",
    "**Status**: [DEFERRED] Refs #007",
)
SAMPLE_TOTAL_STATUS_LINES = 13
SAMPLE_TERMINAL_LINES = 5
SAMPLE_PENDING_LINES = SAMPLE_TOTAL_STATUS_LINES - SAMPLE_TERMINAL_LINES

# The status lines that must never count as terminal, each paired with why. A
# dedicated case per line so a regression names the shape it readmitted rather
# than only moving an aggregate count.
NON_TERMINAL_STATUS_LINES: tuple[tuple[str, str], ...] = (
    ("**Status**: [NEW]", "fetched, not yet acknowledged"),
    ("**Status**: [ACKNOWLEDGED]", "reaction posted, fix not committed"),
    ("**Status**: [DEFERRED]", "no tracking reference"),
    ("**Status**: [BOGUS]", "appears in no vocabulary table"),
    ("**Status**: [COMPLETE]oops", "trailing garbage after a valid prefix"),
    ("**Status**: [DEFERRED] Refs #4054garbage", "trailing garbage after the reference"),
    ("**Status**: [DEFERRED] Refs #0", "GitHub numbers issues from 1, so #0 never resolves"),
    ("**Status**: [DEFERRED] Refs #007", "leading zero is not a GitHub issue number"),
)

# Three comments the API reported, all of them worked to a terminal status.
API_COMMENT_COUNT = 3
COMPLETE_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "**Status**: [COMPLETE]",
    "### Comment 124 (@reviewer)",
    "**Status**: [WONTFIX]",
    "### Comment 125 (@reviewer)",
    "**Status**: [DEFERRED] Refs #4054",
)

# The same map after a bad edit stripped every status field. Both counts read
# zero, so the subtraction reports zero pending on an artifact that records
# nothing about the three comments the API said exist.
STRIPPED_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "[COMPLETE]",
    "### Comment 124 (@reviewer)",
    "[WONTFIX]",
    "### Comment 125 (@reviewer)",
    "[DEFERRED] Refs #4054",
)

# One field survived the edit. Two comments lost theirs, so the map is short.
PARTIAL_COMMENT_MAP_LINES: tuple[str, ...] = (
    "### Comment 123 (@reviewer)",
    "**Status**: [COMPLETE]",
    "### Comment 124 (@reviewer)",
    "[WONTFIX]",
    "### Comment 125 (@reviewer)",
    "[DEFERRED] Refs #4054",
)

VOCABULARY_ROW_RE = re.compile(
    r"^\| `\[(?P<status>[A-Z]+)\][^`]*` \| [^|]+ \| (?P<terminal>[^|]+)\|"
)
TABLE_HEADER = "| Status | Meaning |"

requires_grep = pytest.mark.skipif(GREP is None, reason="grep is not on PATH")
requires_bash = pytest.mark.skipif(BASH is None, reason="bash is not on PATH")


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


def _bash_fences(text: str) -> list[tuple[str, str]]:
    """Return ``(owning heading, fence body)`` for every ``bash`` fence.

    Every fenced block is consumed, not only the bash ones, so a ``#`` comment
    inside a ``text`` or ``python`` fence cannot be mistaken for a heading and
    mislabel the next bash fence.
    """
    fences: list[tuple[str, str]] = []
    heading = ""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            opener = line.strip()
            index += 1
            body: list[str] = []
            while index < len(lines) and lines[index].strip() != "```":
                body.append(lines[index])
                index += 1
            if opener == "```bash":
                fences.append((heading, "\n".join(body) + "\n"))
            index += 1
            continue
        match = MARKDOWN_HEADING_RE.match(line)
        if match is not None:
            heading = match.group("title")
        index += 1
    return fences


def _section_key(heading: str) -> str | None:
    for key in SECTION_KEYS:
        if heading.startswith(key):
            return key
    return None


def _counting_fences(text: str) -> list[tuple[str, str]]:
    """Every bash fence that counts status fields out of the comment map."""
    return [
        (heading, body)
        for heading, body in _bash_fences(text)
        if GREP_COUNT_PATTERN_RE.search(body) and '"$COMMENT_MAP"' in body
    ]


def _derivation_script(
    fence: str,
    comment_map: Path,
    total_comments: int,
    *,
    with_invariant: bool = True,
) -> str:
    """Lift a fence's counting steps out verbatim and make them runnable.

    The slice runs from the ``TOTAL=`` assignment to the end of the API-count
    invariant, which is exactly the derivation and excludes the ``gh api``
    calls the surrounding gate makes. ``COMMENT_MAP`` and ``TOTAL_COMMENTS``
    are injected because the carrier leaves both to the caller.
    """
    assert TOTAL_ASSIGNMENT_TEXT in fence, "fence publishes no canonical TOTAL assignment"
    assert API_COUNT_INVARIANT in fence, (
        "fence publishes no API-count invariant, so a stripped comment map "
        "computes zero pending and clears the gate"
    )
    start = fence.index(TOTAL_ASSIGNMENT_TEXT)
    end = fence.index(API_COUNT_INVARIANT) + len(API_COUNT_INVARIANT)
    body = fence[start:end]
    if not with_invariant:
        body = body.replace(API_COUNT_INVARIANT, ":")
    return (
        f"COMMENT_MAP={shlex.quote(str(comment_map))}\n"
        f"TOTAL_COMMENTS={total_comments}\n"
        f"{body}\n"
        'echo "PENDING=$PENDING"\n'
    )


def _run_derivation(script: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def _gate_four_fence(path: Path) -> str:
    for heading, body in _counting_fences(path.read_text(encoding="utf-8")):
        if _section_key(heading) == "Gate 4":
            return body
    raise AssertionError(f"{_carrier_id(path)} publishes no Gate 4 counting fence")


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
@pytest.mark.parametrize(
    ("status_line", "reason"),
    NON_TERMINAL_STATUS_LINES,
    ids=[line.removeprefix("**Status**: ") for line, _ in NON_TERMINAL_STATUS_LINES],
)
def test_a_non_terminal_status_line_stays_pending(
    status_line: str, reason: str, tmp_path: Path
) -> None:
    """Each way a status can fail to be terminal, named one shape per case."""
    comment_map = _render_comment_map(tmp_path, (status_line,))
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0, (
        f"{status_line!r} counted as terminal; it must stay pending because {reason}"
    )


@requires_grep
@pytest.mark.parametrize("issue_number", ("1", "9", "10", "4054"))
def test_a_real_issue_number_still_marks_deferred_terminal(
    issue_number: str, tmp_path: Path
) -> None:
    """The tightened number class must not cost a legitimate reference.

    Guards the inverse of ``test_a_non_terminal_status_line_stays_pending``:
    narrowing ``#[0-9]+`` to ``#[1-9][0-9]*`` must reject only the numbers
    GitHub cannot issue, never a tracked deferral.
    """
    comment_map = _render_comment_map(tmp_path, (f"**Status**: [DEFERRED] Refs #{issue_number}",))
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 1


@requires_grep
def test_the_old_number_class_is_the_bug_the_new_one_fixes(tmp_path: Path) -> None:
    """Negative control: ``#[0-9]+`` admits the numbers GitHub never issues.

    Issues and pull requests are numbered from 1, so ``Refs #0`` names nothing
    that can be opened. Under the old class it counted terminal, so the gates
    cleared deferred work whose tracking issue does not and cannot exist.
    """
    old_pattern = (
        STATUS_LINE_PATTERN
        + r"(\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[0-9]+)"
        + END_ANCHOR
    )
    unresolvable = (
        "**Status**: [DEFERRED] Refs #0",
        "**Status**: [DEFERRED] Refs #007",
    )
    comment_map = _render_comment_map(tmp_path, unresolvable)

    assert _grep_count(old_pattern, comment_map) == len(unresolvable)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0


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
def test_every_counting_fence_publishes_the_whole_derivation(path: Path) -> None:
    """Each fence, on its own, must carry every step in order.

    Flattening the file and asking whether each step appears somewhere lets one
    gate drop its subtraction, or its API-count invariant, while a sibling
    gate's intact copy keeps the assertion green. The fence is the unit.
    """
    fences = _counting_fences(path.read_text(encoding="utf-8"))
    assert fences, f"{_carrier_id(path)} publishes no fence that counts the comment map"

    for heading, body in fences:
        offsets: list[int] = []
        for step in REQUIRED_DERIVATION_STEPS:
            assert step in body, (
                f"{_carrier_id(path)} section {heading!r} counts the comment map "
                f"without publishing {step!r}"
            )
            offsets.append(body.index(step))
        assert offsets == sorted(offsets), (
            f"{_carrier_id(path)} section {heading!r} publishes the derivation "
            f"steps out of order; the map-exists guard, the two counts, the "
            f"subtraction, and the API-count invariant must run in that order"
        )


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_expected_section_owns_a_counting_fence(path: Path) -> None:
    """Deleting a gate's fence must fail, not shrink the set under test.

    The expected sections are hardcoded per carrier. A gate that loses its
    fence stops being checked otherwise, which is how a per-fence assertion
    silently becomes a no-op.
    """
    found = {
        key
        for heading, _ in _counting_fences(path.read_text(encoding="utf-8"))
        if (key := _section_key(heading)) is not None
    }
    unkeyed = [
        heading
        for heading, _ in _counting_fences(path.read_text(encoding="utf-8"))
        if _section_key(heading) is None
    ]

    assert not unkeyed, (
        f"{_carrier_id(path)} counts the comment map under unrecognized "
        f"section(s) {unkeyed}; add the section to SECTION_KEYS so the "
        f"derivation there is checked"
    )
    assert found == EXPECTED_DERIVATION_SECTIONS[path], (
        f"{_carrier_id(path)} counts the comment map in {sorted(found)}, "
        f"expected {sorted(EXPECTED_DERIVATION_SECTIONS[path])}"
    )


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
    unguarded = []
    for heading, block in _counting_fences(path.read_text(encoding="utf-8")):
        first_count = min(m.start() for m in GREP_COUNT_PATTERN_RE.finditer(block))
        guard = block.find(MAP_EXISTS_GUARD)
        if guard == -1 or guard > first_count:
            unguarded.append(heading)

    assert not unguarded, (
        f"{_carrier_id(path)} counts the comment map without proving it exists "
        f"first, so an absent map computes zero pending and clears the gate "
        f"(issue #4054): {unguarded}"
    )


# The API-count invariant, executed by the shell the carriers publish it for.


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_stripped_comment_map_blocks_the_gate(path: Path, tmp_path: Path) -> None:
    """A map whose status fields were stripped must block, not read as done.

    Both counts read zero, so the subtraction reports zero pending. Only the
    comparison against the API count can tell that apart from a finished map.
    """
    comment_map = _render_comment_map(tmp_path, STRIPPED_COMMENT_MAP_LINES)
    script = _derivation_script(_gate_four_fence(path), comment_map, API_COMMENT_COUNT)

    result = _run_derivation(script)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 4 cleared a comment map with every status "
        f"field stripped: exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 0 status fields, API reported 3" in result.stdout
    assert "PENDING=" not in result.stdout, (
        f"{_carrier_id(path)} Gate 4 reached the pending report after the "
        f"invariant should have exited"
    )


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_partially_stripped_comment_map_blocks_the_gate(path: Path, tmp_path: Path) -> None:
    """Losing some status fields must block too, not shrink the denominator."""
    comment_map = _render_comment_map(tmp_path, PARTIAL_COMMENT_MAP_LINES)
    script = _derivation_script(_gate_four_fence(path), comment_map, API_COMMENT_COUNT)

    result = _run_derivation(script)

    assert result.returncode == 1, (
        f"{_carrier_id(path)} Gate 4 cleared a comment map holding 1 of 3 "
        f"status fields: exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "[BLOCKED] Comment map carries 1 status fields, API reported 3" in result.stdout


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_a_complete_comment_map_clears_the_invariant(path: Path, tmp_path: Path) -> None:
    """Control: the invariant must not block a map that matches the API count."""
    comment_map = _render_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    script = _derivation_script(_gate_four_fence(path), comment_map, API_COMMENT_COUNT)

    result = _run_derivation(script)

    assert result.returncode == 0, (
        f"{_carrier_id(path)} Gate 4 blocked a complete comment map: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "PENDING=0" in result.stdout


@requires_bash
@pytest.mark.parametrize("bad_value", ["", "null", "-1", "3abc"])
def test_a_non_numeric_total_comments_blocks_before_the_invariant(
    bad_value: str, tmp_path: Path
) -> None:
    """A non-numeric API count must fail closed, not skip the invariant.

    Phase 1 sets ``TOTAL_COMMENTS`` via ``jq`` without ``-e``; an API or
    script failure can leave it empty or ``null``. ``[ "$TOTAL" -ne
    "$TOTAL_COMMENTS" ]`` on a non-numeric right side raises ``integer
    expression expected``, which is a nonzero exit from ``[`` and therefore
    reads as *false* to ``if``, so the BLOCKED body is skipped and a
    terminal-looking map clears this fail-closed gate anyway (PR #5342
    review). Reproduced here against the real shell for
    ``.claude/agents/pr-comment-responder.md``, which now guards
    ``TOTAL_COMMENTS`` with a numeric ``case`` before the comparison runs.
    """
    path = REPO_ROOT / ".claude/agents/pr-comment-responder.md"
    fence = _gate_four_fence(path)
    start = fence.index(TOTAL_ASSIGNMENT_TEXT)
    end = fence.index(API_COUNT_INVARIANT) + len(API_COUNT_INVARIANT)
    body = fence[start:end]
    comment_map = _render_comment_map(tmp_path, COMPLETE_COMMENT_MAP_LINES)
    script = (
        f"COMMENT_MAP={shlex.quote(str(comment_map))}\n"
        f"TOTAL_COMMENTS={shlex.quote(bad_value)}\n"
        f"{body}\n"
        'echo "PENDING=$PENDING"\n'
    )

    result = _run_derivation(script)

    assert result.returncode == 1, (
        f"non-numeric TOTAL_COMMENTS={bad_value!r} cleared the gate: "
        f"exit {result.returncode}, stdout {result.stdout!r}"
    )
    assert "PENDING=" not in result.stdout, (
        f"TOTAL_COMMENTS={bad_value!r} reached the pending report; "
        f"the invariant should have exited first"
    )
    assert "not a non-negative integer" in result.stdout


@requires_bash
def test_without_the_invariant_a_stripped_map_clears_the_gate(tmp_path: Path) -> None:
    """Negative control: the invariant is what catches the stripped map.

    Take the shipped Gate 4 derivation, remove only the API-count invariant,
    and the same stripped map exits 0 with zero pending. That is the fail-open
    Copilot reported on PR #5342, reproduced against the real shell.
    """
    fence = _gate_four_fence(REPO_ROOT / "templates/agents/pr-comment-responder.shared.md")
    comment_map = _render_comment_map(tmp_path, STRIPPED_COMMENT_MAP_LINES)

    without = _run_derivation(
        _derivation_script(fence, comment_map, API_COMMENT_COUNT, with_invariant=False)
    )
    with_invariant = _run_derivation(_derivation_script(fence, comment_map, API_COMMENT_COUNT))

    assert without.returncode == 0
    assert "PENDING=0" in without.stdout
    assert with_invariant.returncode == 1


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


@pytest.mark.parametrize("path", SKILL_ENTRYPOINTS, ids=_carrier_id)
def test_skill_entrypoint_completion_criteria_name_every_terminal_status(
    path: Path,
) -> None:
    """The entrypoint states completion; a stale copy narrows the vocabulary.

    ``SKILL.md`` is what an agent reads before it reaches the gates. While it
    defined completion as ``COMPLETE or WONTFIX`` it contradicted the gates,
    which also accept ``[DUPLICATE]`` and a tracked ``[DEFERRED]``. An agent
    following the entrypoint would keep working comments the gates already
    counted terminal, or file the outcome under the wrong status.
    """
    text = path.read_text(encoding="utf-8")

    assert "COMPLETE or WONTFIX" not in text, (
        f"{_carrier_id(path)} still defines completion as the two-status "
        f"vocabulary that predates [DUPLICATE] and [DEFERRED] (issue #4054)"
    )
    for status in TERMINAL_STATUS_TOKENS:
        assert status in text, (
            f"{_carrier_id(path)} completion criteria omit {status}, so an "
            f"agent reading the entrypoint gets criteria the gates disagree with"
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
