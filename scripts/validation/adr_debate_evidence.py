"""Check staged ADR debate logs for review evidence."""

from __future__ import annotations

import re
import unicodedata

# Issue #5205: thresholds calibrated against the 86 debate logs in
# .project-toolkit/critique on main. All 86 clear these; the smallest is 454 bytes.
DEBATE_LOG_MIN_BYTES = 300
# Canonical source: the fenced debate-log template in
# .claude/skills/adr-review/references/artifacts.md. These are its unfilled
# placeholder spans, quoted verbatim per .claude/rules/canonical-source-mirror.md.
# A log still carrying any of them was copied and not filled in, and an unfilled
# template is not a review: the shipped template clears the other four signals on
# its own, because "Agent Positions" satisfies reviewer attribution and
# "Outcome: [Consensus | Concluded Without Consensus]" satisfies a verdict label
# beside a decision token. Found by review of PR #5308.
#
# Matching these literals rather than bracketed spans in general is deliberate.
# A general placeholder regex was measured against the committed corpus and
# would false-block 25 of 86 logs (29%), on task checkboxes, [PASS] markers,
# confidence intervals such as [-0.20, +0.31], and bracketed ADR references.
# These exact literals false-block 0 of 86.
DEBATE_LOG_TEMPLATE_PLACEHOLDERS = (
    "[ADR Title]",
    "[N]",
    "[Consensus | Concluded Without Consensus]",
    "[proposed | accepted | needs-revision]",
    "[Issue 1]",
    "[Issue 2]",
    "[Change 1]",
    "[Change 2]",
    "[If applicable]",
    "| ... | ... |",
)
DEBATE_LOG_MIN_SECTIONS = 3
DEBATE_LOG_VERDICT_WINDOW_LINES = 6
# Canonical source: the "## Agent Roles" table in
# .claude/skills/adr-review/SKILL.md. Quoted verbatim per
# .claude/rules/canonical-source-mirror.md, which requires the contract itself
# rather than a pointer to it. The heading is cited rather than a line range:
# a range goes stale on any edit above it, and
# test_the_quoted_role_table_is_still_verbatim_in_the_skill checks the quote
# against the file, which a line number cannot do.
#
#     | Agent | Focus | Tie-Breaker Role |
#     |-------|-------|------------------|
#     | **architect** | Structure, governance, coherence, ADR compliance | Structural questions |
#     | **critic** | Gaps, risks, alignment, completeness | None |
#     | **independent-thinker** | Challenge assumptions, surface contrarian views | None |
#     | **security** | Threat models, security trade-offs | None |
#     | **analyst** | Root cause, evidence, feasibility | None |
#     | **high-level-advisor** | Priority, resolve conflicts, break ties | Decision paralysis |
#
# Stricter/looser/different than canonical: LOOSER, deliberately. The skill
# names these six as the agents that conduct a review. This gate does not
# require all six, or even any of them by name: DEBATE_LOG_REVIEWER_RE below
# also accepts "self-review", "participants", "reviewers", and "agents". That
# divergence is the resolution of issue #5205's proposed six-role roster, which
# was measured to false-block 18 of the 86 committed logs (21%), including
# genuine single-reviewer, self-review, and owner-direction records. Acceptance criterion 3 of
# that issue forbids false-blocking a genuine log, so the roster lost to the
# requirement. The looseness is therefore intentional and load-bearing; do not
# tighten these to the six roles without recalibrating against the corpus and
# rewriting the logs the tightening would reject.
DEBATE_LOG_ROLES = (
    "architect",
    "critic",
    "independent-thinker",
    "security",
    "analyst",
    "high-level-advisor",
)
# "agents?" is here because the canonical template in
# .claude/skills/adr-review/references/artifacts.md labels its roster "Agent
# Positions", so without it the gate rejects a log written to the document its
# own error message cites. It is a weak signal on its own; the byte floor,
# section count and verdict carry the weight.
DEBATE_LOG_REVIEWER_RE = re.compile(
    "|".join(
        [
            *(rf"\b{role}\b" for role in DEBATE_LOG_ROLES),
            r"\bself[- ]review\b",
            r"\bparticipants?\b",
            r"\breviewers?\b",
            r"\bagents?\b",
        ]
    ),
    re.IGNORECASE,
)
DEBATE_LOG_DECISION_RE = re.compile(
    r"\b(accept(?:ed)?|disagree[- ]and[- ]commit|d&c|block(?:ed|ing)?"
    r"|needs[- ]revision|concluded)\b",
    re.IGNORECASE,
)
# "decision", "direction", "governing evidence" and "ruling" are here because
# the corpus contains records that conclude without ever writing "verdict": an
# owner decides, and the record states the decision and its authority. Three of
# the 86 committed logs are that genre, headed "Owner Direction" or "No debate
# was held", and the narrower list false-blocked every one of them. Measured on
# the current corpus: 3 of 86 rejected before, 0 after, and issue #5205's
# 7-byte stub still fails. Found when the corpus grew from 79 to 86 while this
# change was open and the calibration test caught it in CI.
DEBATE_LOG_VERDICT_LABEL_RE = re.compile(
    r"\b(verdict|position|consensus|outcome|recommendation|decision|direction"
    r"|governing evidence|ruling|vote|stance)s?\b",
    re.IGNORECASE,
)
DEBATE_LOG_HEADING_RE = re.compile(r"(?m)^#{1,6} \S")


def _has_verdict(content: str) -> bool:
    """Return True when a decision sits within the window of a verdict label.

    One bounded path, deliberately. There used to be a second, unbounded one:
    any pipe-prefixed row anywhere in the document containing a role and a
    decision word counted as a positions table. Review showed that accepted
    prose notes that decide nothing, for instance::

        | architect | Open issue | dependency remains blocked |

    which names a role and contains "blocked" while recording an open issue.

    The fallback is deleted rather than narrowed, because it turned out to be
    redundant once ``DEBATE_LOG_VERDICT_LABEL_RE`` covered the words real
    positions tables head their columns with (position, stance, vote). A table
    header is itself a label line, and its rows fall inside the window, so the
    bounded branch already accepts every genuine positions table. Measured with
    the fallback removed: 0 of the 86 committed logs rejected. Issue #5205.
    """
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if not DEBATE_LOG_VERDICT_LABEL_RE.search(line):
            continue
        window = lines[index : index + DEBATE_LOG_VERDICT_WINDOW_LINES]
        if any(DEBATE_LOG_DECISION_RE.search(entry) for entry in window):
            return True
    return False


def _evidence_byte_count(content: str) -> int:
    """Return the byte count of ``content``, ignoring replacement characters.

    A lossy decode turns every byte that is not valid UTF-8 into U+FFFD, which
    re-encodes to three bytes. Measuring the decoded text directly therefore
    inflates the count threefold over the invalid span: 100 on-disk bytes of
    ``0xFF`` measure 300 and clear a stated 300-byte floor. Replacement
    characters carry no review text, so they count for nothing here and the
    floor stays a floor on real bytes.

    The staged path no longer decodes lossily. ``_staged_debate_log_contents``
    decodes strictly and routes a blob that is not valid UTF-8 to the undecodable
    report, so the inflation above cannot arrive through the gate any more. This
    stays because it is a property of the function rather than of one caller:
    ``debate_log_evidence_gap`` is public, takes text from wherever its caller
    got it, and a future caller that decodes leniently would otherwise inherit
    the bypass. Two independent things have to be wrong before the floor is.

    Fail-closed against the measurement it replaces, which is the claim that
    matters: for any input this returns at most what
    ``len(content.encode("utf-8"))`` returned, since it encodes the same text
    minus the replacement characters, so it admits nothing the old measurement
    rejected. It is NOT bounded by the decoded character count, and saying so
    would be wrong: 200 characters of U+00E9 measure 400 bytes here, which a
    test pins.

    The residual: an authored U+FFFD, one a committer typed on purpose rather
    than one the decoder produced, loses three bytes here. The two are
    indistinguishable after decoding, so the choice is which way to be wrong,
    and undercounting can only block a log the committer can then lengthen,
    while overcounting admits the invalid-byte bypass this exists to close.
    None of the 86 committed logs contains a replacement character. Issue #5205.
    """
    return len(content.replace("\ufffd", "").encode("utf-8"))


# Three normalizations, each closing a class of edit rather than one variant.
#
# Cf is the Unicode "format" category: zero-width space, ZWNJ, ZWJ, soft hyphen,
# the bidi controls. Every one of them renders as nothing and none of them are
# review content, so a placeholder wearing them is still a placeholder.
#
# A markdown backslash escape renders as the character it escapes, so `\]` and
# `]` are the same document to every reader and different strings to a matcher.
#
# `[^\S\r\n]` is whitespace minus the line breaks, so U+00A0, U+2007 and U+202F
# collapse while a placeholder still cannot match across a line it does not span.
#
# The class framing is the point, and it was learned the expensive way: this
# check was defeated four times on this PR, by invalid bytes, ASCII spaces,
# U+00A0, and markdown escapes. Each fix targeted the variant in front of it and
# the next variant was cheaper than the last. Zero-width and soft hyphen cleared
# the gate too and nobody had reported them; they were found by asking what else
# is invisible rather than by waiting for the fifth review round.
DEBATE_LOG_PLACEHOLDER_FORMAT_CATEGORY = "Cf"
DEBATE_LOG_PLACEHOLDER_ESCAPE_RE = re.compile(r"\\([!-/:-@\[-`{-~])")
DEBATE_LOG_PLACEHOLDER_SPACING_RE = re.compile(r"[^\S\r\n]+")
DEBATE_LOG_PLACEHOLDER_PUNCTUATION_RE = re.compile(r" ?([\[\]|]) ?")


def _normalized_for_placeholders(text: str) -> str:
    """Return ``text`` with the spacing and case a placeholder edit can change.

    Matching the template's literals exactly was defeated by editing them
    rather than filling them in. Measured on the shipped template: adding one
    space before each closing bracket stops all nine literals matching while
    every other signal stays satisfied, so the visibly unedited template
    cleared the gate for nine keystrokes. Upper-casing one word does the same.

    Invisible formatting characters go, markdown backslash escapes resolve to
    the character they escape, horizontal whitespace of any kind collapses,
    spacing around ``[``, ``]`` and ``|`` goes, and the result case-folds.
    Newlines survive so a placeholder cannot be matched across a line it does
    not span. Calibrated like the literals themselves: 0 of the 86 committed
    logs are rejected by the normalized comparison, the same as by the exact
    one, with every variant above measured individually. Issue #5205.
    """
    visible = "".join(
        character
        for character in text
        if unicodedata.category(character) != DEBATE_LOG_PLACEHOLDER_FORMAT_CATEGORY
    )
    unescaped = DEBATE_LOG_PLACEHOLDER_ESCAPE_RE.sub(r"\1", visible)
    collapsed = DEBATE_LOG_PLACEHOLDER_SPACING_RE.sub(" ", unescaped)
    return DEBATE_LOG_PLACEHOLDER_PUNCTUATION_RE.sub(r"\1", collapsed).casefold()


def debate_log_evidence_gap(content: str) -> str | None:
    """Return why ``content`` fails as review evidence, or None when it passes.

    Issue #5205: the gate accepted any staged ``.project-toolkit/critique/*debate*.md``
    whose bytes contained an ADR id, so a 7-byte file cleared it. These four
    signals are calibrated against the 86 debate logs in ``.project-toolkit/critique`` on
    main: all 86 pass, and a stub carrying only an ADR id fails on the first.

    A fifth check rejects a log still carrying the canonical template's own
    placeholders. The shipped template clears the four signals above unchanged,
    so without it a contributor could copy the template, change the title, and
    self-authorize an ADR lifecycle change with a document nobody filled in.

    What this is worth, stated at the floor rather than at the ceiling. It
    stops the accidental and the lazy: a 7-byte stub, an unfilled template, a
    name-shaped file. It does not raise forgery to anything like "deliberately
    constructed", and an earlier version of this docstring said otherwise.
    ``test_the_weakest_currently_passing_log_is_pinned`` holds the real floor,
    and it is about thirty seconds of typing::

        # D

        ## Outcome

        Accepted.

        ### Notes

        agent

        <filler to clear the byte floor>

    Every signal is a property of text the committer controls, so a committer
    who wants past this gate gets past it. Binding the gate to attestation of
    the review itself is tracked on #5245 and #5247; until then this is a
    tripwire, not a control.

    One more limit worth naming here rather than leaving in a test docstring:
    coverage is by citation, not by review. ``_referenced_adr_ids`` scans the
    whole log, so a log that genuinely reviews ADR-042 and mentions ADR-005
    once in a footer covers both. That is the semantics issue #5205 asked for
    and it narrows defect 2 rather than closing it: one log can still authorize
    a second record it never discusses, it just has to name it.
    ``test_an_incidental_mention_covers_a_staged_id`` pins that behavior.
    """
    if _evidence_byte_count(content) < DEBATE_LOG_MIN_BYTES:
        return f"shorter than {DEBATE_LOG_MIN_BYTES} bytes"
    if len(DEBATE_LOG_HEADING_RE.findall(content)) < DEBATE_LOG_MIN_SECTIONS:
        return f"fewer than {DEBATE_LOG_MIN_SECTIONS} markdown sections"
    if not DEBATE_LOG_REVIEWER_RE.search(content):
        return (
            "no reviewer attribution (an adr-review role, 'participants', "
            "'reviewers', 'agents' as in the template's 'Agent Positions', "
            "or 'self-review')"
        )
    if not _has_verdict(content):
        return (
            "no verdict (a decision within "
            f"{DEBATE_LOG_VERDICT_WINDOW_LINES} lines of a verdict, decision, "
            "position, stance, vote or outcome label; a positions-table "
            "header counts as that label)"
        )
    normalized = _normalized_for_placeholders(content)
    unresolved = [
        placeholder
        for placeholder in DEBATE_LOG_TEMPLATE_PLACEHOLDERS
        if _normalized_for_placeholders(placeholder) in normalized
    ]
    if unresolved:
        shown = ", ".join(repr(placeholder) for placeholder in unresolved[:3])
        return f"unfilled template placeholders ({shown})"
    return None
