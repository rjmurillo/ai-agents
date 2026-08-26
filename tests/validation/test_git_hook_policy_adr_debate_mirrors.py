"""Canonical-source drift guards for the ADR debate-log gate.

Split out of ``test_git_hook_policy_adr_debate_boundaries.py`` when that module
reached 506 lines and tripped the repository's 500-line file-size rule. The seam
is the same kind as the earlier one: the sibling asserts thresholds against text
the test itself writes, while every case here reads a document the gate claims
to mirror and fails when the two disagree.

Three quotes are guarded. The debate-log template in the adr-review skill's
``references/artifacts.md``, which the gate's own error message points
committers at. The ``## Agent Roles`` roster quoted above ``DEBATE_LOG_ROLES``,
which ``.claude/rules/canonical-source-mirror.md`` requires character for
character. And the placeholder literals the gate rejects, compared against the
template in both directions so neither side can drift alone.

Issue #5205.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy

_DEBATE_LOG_TEMPLATE_DOC = (
    _ROOT / ".claude" / "skills" / "adr-review" / "references" / "artifacts.md"
)


_DEBATE_LOG_TEMPLATE_RE = re.compile(
    r"Save to: `\.agents/critique/ADR-NNN-debate-log\.md`\s*\n+```markdown\n(.*?)\n```",
    re.DOTALL,
)


def _canonical_debate_log_template() -> str:
    """Return the debate-log template as the cited document actually holds it."""
    source = _DEBATE_LOG_TEMPLATE_DOC.read_text(encoding="utf-8")
    match = _DEBATE_LOG_TEMPLATE_RE.search(source)
    assert match is not None, (
        f"no debate-log template fence found in {_DEBATE_LOG_TEMPLATE_DOC}. "
        "The gate's error message points committers at that document, so if "
        "the template moved, the message is now wrong too."
    )
    return match.group(1)


def _filled_template() -> str:
    """Return the canonical template with every placeholder answered.

    Substituted the way an author filling it in would, so the assertions below
    are about the template's *shape* rather than about any wording of mine.
    """
    filled = _canonical_debate_log_template()
    for placeholder, answer in (
        ("[ADR Title]", "Python Migration Strategy"),
        ("[N]", "2"),
        ("[Consensus | Concluded Without Consensus]", "Consensus"),
        ("[proposed | accepted | needs-revision]", "accepted"),
        ("[Issue 1]", "The trust boundary was not written down anywhere."),
        ("[Issue 2]", "The rollback path assumed a backup that is not taken."),
        ("[Change 1]", "Added the boundary to the Context section."),
        ("[Change 2]", "Replaced the rollback step with one that is tested."),
        ("[If applicable]", "Ship ADR-042 and revisit the metrics in Q3."),
        ("| ... | ... |", "| architect | Accept |\n| security | Disagree-and-Commit |"),
    ):
        filled = filled.replace(placeholder, answer)
    return filled


def test_the_canonical_template_shape_passes() -> None:
    """A log written to the cited template must pass once it is filled in.

    ``debate_log_evidence_gap``'s failure message cites
    ``.claude/skills/adr-review/references/artifacts.md``. That template labels
    its roster "Agent Positions" and its table column "Agent", so a reviewer
    check that knew only the six role slugs blocked the committer and then sent
    them to the document they had followed.

    The template is read from that file rather than restated. A hardcoded copy
    makes the cross-file contract unobservable: an edit to the document could
    start failing real template-based logs while a detached copy kept this test
    green, which is the drift the test exists to prevent.
    """
    filled = _filled_template()

    # Guard the extraction. A regex that silently matched an empty or wrong
    # fence would make the assertion below vacuous.
    assert "Agent Positions" in filled, (
        "extracted the wrong fence from "
        f"{_DEBATE_LOG_TEMPLATE_DOC}: no 'Agent Positions' roster in it"
    )

    gap = policy.debate_log_evidence_gap(filled)
    assert gap is None, (
        f"the canonical template at {_DEBATE_LOG_TEMPLATE_DOC} no longer clears "
        f"the gate that cites it once filled in: {gap}. Either the template or "
        "the gate moved; they have to move together."
    )


def test_the_unfilled_canonical_template_does_not_pass() -> None:
    """Negative pair: copying the template is not conducting a review.

    Review of PR #5308 found the gate cleared the shipped template with only
    its title changed. The four content signals cannot catch that on their own:
    "Agent Positions" satisfies reviewer attribution and "Outcome: [Consensus |
    Concluded Without Consensus]" satisfies a verdict label beside a decision
    token, so an untouched template reads as a complete review to every one of
    them. That is the stub defect this PR exists to close, wearing more bytes.
    """
    untouched = _canonical_debate_log_template().replace("[ADR Title]", "ADR-042")

    # It really does clear the other four signals; the placeholder check is
    # what stops it. Asserting this first keeps the test honest about which
    # signal is doing the work.
    for signal_name, satisfied in (
        ("byte floor", policy._evidence_byte_count(untouched) >= policy.DEBATE_LOG_MIN_BYTES),
        (
            "section floor",
            len(policy.DEBATE_LOG_HEADING_RE.findall(untouched)) >= policy.DEBATE_LOG_MIN_SECTIONS,
        ),
        ("reviewer attribution", bool(policy.DEBATE_LOG_REVIEWER_RE.search(untouched))),
        ("verdict", policy._has_verdict(untouched)),
    ):
        assert satisfied, f"fixture no longer reaches the placeholder check: {signal_name} fails"

    gap = policy.debate_log_evidence_gap(untouched)
    assert gap is not None and gap.startswith("unfilled template placeholders"), gap


_ADR_REVIEW_SKILL = _ROOT / ".claude" / "skills" / "adr-review" / "SKILL.md"


_GATE_MODULE = _ROOT / "scripts" / "validation" / "git_hook_policy.py"


# The literal indent the roster table is quoted under above DEBATE_LOG_ROLES.
# Removed rather than stripped so trailing whitespace survives the comparison.
_QUOTED_TABLE_INDENT = "#     "


def _canonical_roster_table() -> list[str]:
    """Return the "## Agent Roles" table rows from the skill, verbatim."""
    skill = _ADR_REVIEW_SKILL.read_text(encoding="utf-8")
    section = re.search(r"^## Agent Roles$(.*?)^## ", skill, re.MULTILINE | re.DOTALL)
    assert section is not None, (
        f"the cited '## Agent Roles' heading is gone from {_ADR_REVIEW_SKILL}; "
        "the quote above DEBATE_LOG_ROLES now points at nothing"
    )
    return [line for line in section.group(1).splitlines() if line.startswith("|")]


def _quoted_roster_table() -> list[str]:
    """Return the table quoted in the comment above ``DEBATE_LOG_ROLES``.

    The quote is indented inside a ``#`` comment block, so the rows are
    recovered by removing that exact prefix rather than by restating them
    here, which would just move the drift problem into this file.

    The prefix removed is the literal comment indent, not a strip. Stripping
    would discard trailing whitespace on both the quote and, by comparison,
    the canonical row, which would make a trailing-space edit to either side
    invisible to a test whose name claims a character-for-character mirror.
    """
    module = _GATE_MODULE.read_text(encoding="utf-8")
    anchor = module.index("DEBATE_LOG_ROLES = (")
    rows = [
        line.removeprefix(_QUOTED_TABLE_INDENT)
        for line in module[:anchor].splitlines()
        if line.startswith(f"{_QUOTED_TABLE_INDENT}|")
    ]
    assert rows, f"no quoted table found above DEBATE_LOG_ROLES in {_GATE_MODULE}"
    return rows


def test_the_quoted_role_table_is_still_verbatim_in_the_skill() -> None:
    """Drift guard for the role table quoted above DEBATE_LOG_ROLES.

    `.claude/rules/canonical-source-mirror.md` requires the contract quoted
    character for character, which makes the quote a claim that can rot. The
    comment cites the "## Agent Roles" heading rather than a line range,
    because a range goes stale on any edit above it while saying nothing about
    whether the quoted text still matches. This checks the text.

    The whole table, not the role column. Two earlier versions of this test
    were weaker than their own name: the first found six bold names anywhere
    in the document, so a rename, a reorder, a seventh role, or the table
    moving out of the section all stayed green; the second compared the role
    sequence, which still left the Focus and Tie-Breaker cells free to drift
    while the comment claimed to quote them. The comment quotes the table, so
    the test compares the table.
    """
    canonical = _canonical_roster_table()
    quoted = _quoted_roster_table()

    assert quoted == canonical, (
        f"the table quoted in {_GATE_MODULE} no longer matches the roster in "
        f"{_ADR_REVIEW_SKILL}.\ncanonical: {canonical}\nquoted:    {quoted}"
    )

    # The quote is the contract the constant claims to mirror, so the constant
    # has to agree with it too, in order.
    roles = [re.match(r"\|\s*\*\*([^*]+)\*\*", row) for row in canonical]
    assert [m.group(1) for m in roles if m] == list(policy.DEBATE_LOG_ROLES)


def test_the_placeholder_set_matches_the_canonical_template_both_ways() -> None:
    """Drift guard, in both directions.

    ``DEBATE_LOG_TEMPLATE_PLACEHOLDERS`` is a verbatim copy per
    `.claude/rules/canonical-source-mirror.md`. Checking only that each quoted
    literal is still in the template catches a placeholder removed or reworded,
    but not one *added*: the gate would then accept an unfilled copy of the new
    template, and ``_filled_template`` would leave the new token in place while
    the positive test still passed. Both halves have to be checked. Found by
    review.
    """
    template = _canonical_debate_log_template()
    quoted = set(policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS)

    stale = sorted(p for p in quoted if p not in template)
    assert not stale, (
        f"quoted placeholders no longer in {_DEBATE_LOG_TEMPLATE_DOC}, so the "
        f"copy has drifted from the template it mirrors: {stale}"
    )

    # The other direction. Bracketed spans are the template's placeholder form;
    # the ellipsis row is the one that is not bracketed, so it is named here
    # rather than discovered.
    in_template = set(re.findall(r"\[[^\]\n]*\]", template))
    if "| ... | ... |" in template:
        in_template.add("| ... | ... |")
    unquoted = sorted(in_template - quoted)
    assert not unquoted, (
        f"{_DEBATE_LOG_TEMPLATE_DOC} grew placeholders the gate does not "
        f"reject, so an unfilled copy of the new template would clear it, and "
        f"_filled_template would leave them unanswered: {unquoted}"
    )


def test_a_byte_corrupted_template_is_stopped_at_the_decode_not_by_the_signals() -> None:
    """The placeholder check is defeated by corrupting the placeholders.

    Corrupt one byte inside each of the template's placeholder literals and the
    fifth signal stops seeing them, while everything the other four read stays
    intact: the headings, the `Agent Positions` roster column, the `Outcome`
    line with `Concluded` beside it, and the ADR id. A lossy decode turned that
    into a document the committer never wrote, and the unfilled template cleared
    the gate at 402 on-disk bytes.

    The fix is not in the signal set, and this test says so rather than leaving
    it to be inferred: the corrupted copy still passes `debate_log_evidence_gap`
    when it is decoded lossily. What changed is that the staged path no longer
    decodes lossily, so those bytes never become that string. Any future caller
    that reintroduces `errors="replace"` reopens this, which is why the assertion
    below is written against the decode rather than against the gap.
    """
    template = _canonical_debate_log_template().replace("[ADR Title]", "ADR-042")
    blob = template.encode("utf-8")
    corrupted = 0
    for literal in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS:
        needle = literal.encode("utf-8")
        index = blob.find(needle)
        while index != -1:
            blob = blob[: index + 1] + b"\xff" + blob[index + 2 :]
            corrupted += 1
            index = blob.find(needle)

    assert corrupted >= len(policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS)

    lossy = blob.decode("utf-8", errors="replace")
    assert not [p for p in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS if p in lossy], (
        "the corruption must actually defeat the placeholder check, or this "
        "test proves nothing about the decode"
    )
    assert policy.debate_log_evidence_gap(lossy) is None

    with pytest.raises(UnicodeDecodeError):
        blob.decode("utf-8")


@pytest.mark.parametrize(
    ("label", "spacer"),
    [
        ("ascii space", " "),
        ("no-break space", "\u00a0"),
        ("figure space", "\u2007"),
        ("narrow no-break space", "\u202f"),
        ("zero-width space", "\u200b"),
        ("soft hyphen", "\u00ad"),
        ("zero-width non-joiner", "\u200c"),
    ],
)
def test_any_horizontal_whitespace_in_a_placeholder_is_still_rejected(
    label: str, spacer: str
) -> None:
    """The normalization collapses whitespace, not just the ASCII kind.

    Parametrized rather than written once, because the first version of this
    normalization collapsed only space and tab, and one U+00A0 before each
    closing bracket walked the unfilled template straight through: the reviewer
    and verdict regexes still matched and none of the nine literals did. That
    was the third variant of one attack, after invalid bytes and after ASCII
    spaces, so the case is a table now and a fourth variant costs a row.
    """
    template = _canonical_debate_log_template().replace("[ADR Title]", "ADR-042")

    altered = template
    for placeholder in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS:
        if placeholder in altered:
            altered = altered.replace(placeholder, f"{placeholder[:-1]}{spacer}{placeholder[-1]}")

    assert not [p for p in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS if p in altered], (
        f"{label} must actually defeat exact matching, or this row proves nothing"
    )
    assert policy.DEBATE_LOG_REVIEWER_RE.search(altered), (
        f"{label}: the other signals must still pass, or the block below could "
        "come from the wrong one"
    )
    assert policy._has_verdict(altered)

    gap = policy.debate_log_evidence_gap(altered)
    assert gap is not None and gap.startswith("unfilled template placeholders"), f"{label}: {gap}"


def test_a_newline_inside_a_placeholder_is_not_collapsed_away() -> None:
    """Line breaks survive the normalization, so no match spans a line.

    The guard on the widened whitespace class. Collapsing every whitespace
    character would let a literal match across two lines that merely end and
    begin with its halves, which is a false block waiting to happen in a corpus
    full of tables.
    """
    split = "| ...\n| ... |"
    normalized = policy._normalized_for_placeholders(split)
    assert "\n" in normalized
    assert policy._normalized_for_placeholders("| ... | ... |") not in normalized


def test_a_whitespace_altered_template_is_still_rejected() -> None:
    """Editing a placeholder is not filling it in.

    Exact-literal matching was defeated by one space before each closing
    bracket: measured on the shipped template, nine one-character edits stopped
    all nine literals matching while the byte floor, the section floor, the
    roster column and the outcome line stayed satisfied, so the visibly
    unedited template cleared the gate. Case does the same thing for free.

    The four preceding signals are asserted to still hold, so this cannot
    quietly stop testing the placeholder check if a fixture drifts and starts
    failing earlier for an unrelated reason.
    """
    template = _canonical_debate_log_template().replace("[ADR Title]", "ADR-042")

    spaced = template
    for placeholder in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS:
        if placeholder in spaced:
            spaced = spaced.replace(placeholder, f"{placeholder[:-1]} {placeholder[-1]}")

    assert not [p for p in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS if p in spaced], (
        "the alteration must actually defeat exact matching, or this test "
        "proves nothing about the normalization"
    )
    assert policy._evidence_byte_count(spaced) >= policy.DEBATE_LOG_MIN_BYTES
    assert policy.DEBATE_LOG_REVIEWER_RE.search(spaced)
    assert policy._has_verdict(spaced)

    gap = policy.debate_log_evidence_gap(spaced)
    assert gap is not None and gap.startswith("unfilled template placeholders"), gap

    upper = template.replace(
        "[Consensus | Concluded Without Consensus]",
        "[CONSENSUS | CONCLUDED WITHOUT CONSENSUS]",
    )
    upper_gap = policy.debate_log_evidence_gap(upper)
    assert upper_gap is not None and upper_gap.startswith("unfilled template"), upper_gap


def test_the_normalization_does_not_reject_any_committed_log() -> None:
    """The normalization is calibrated, not assumed.

    A looser comparison is a false-block risk, which is the mistake the roster
    proposal made. Measured the same way the literals were: 0 of the committed
    corpus is rejected by the normalized comparison. Without this, a future
    widening of the normalization could start rejecting real reviews and only
    the whole-corpus pin in the boundaries module would notice, one signal
    later and with a less specific message.
    """
    critique = _ROOT / ".agents" / "critique"
    logs = sorted(path for path in critique.glob("*.md") if "debate" in path.name)
    assert len(logs) >= 70, "expected the calibration corpus to be present"

    hits = {}
    for path in logs:
        normalized = policy._normalized_for_placeholders(path.read_text(encoding="utf-8"))
        matched = [
            placeholder
            for placeholder in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS
            if policy._normalized_for_placeholders(placeholder) in normalized
        ]
        if matched:
            hits[path.name] = matched

    assert hits == {}


def test_a_markdown_escaped_placeholder_is_still_rejected() -> None:
    """`\\]` and `]` are the same document and different strings.

    A backslash escape renders as the character it escapes, so an author can
    escape every closing bracket and the internal pipe and the template still
    reads exactly as shipped, while no literal matches. Reported by review as
    the fourth defeat of this check; the fix resolves escapes rather than
    adding a fifth special case.
    """
    template = _canonical_debate_log_template().replace("[ADR Title]", "ADR-042")

    escaped = template
    for placeholder in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS:
        if placeholder in escaped:
            escaped = escaped.replace(
                placeholder, placeholder.replace("]", "\\]").replace("|", "\\|")
            )

    assert not [p for p in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS if p in escaped], (
        "the escaping must actually defeat exact matching"
    )
    assert policy.DEBATE_LOG_REVIEWER_RE.search(escaped)
    assert policy._has_verdict(escaped)

    gap = policy.debate_log_evidence_gap(escaped)
    assert gap is not None and gap.startswith("unfilled template placeholders"), gap


def test_an_escape_before_a_letter_is_not_stripped() -> None:
    """Only punctuation escapes resolve, which is what markdown defines.

    The guard on the escape normalization. Stripping a backslash before any
    character would rewrite prose that legitimately contains one, and markdown
    only assigns meaning to a backslash before ASCII punctuation.
    """
    assert "\\n" in policy._normalized_for_placeholders("a\\nb")
    assert "\\" not in policy._normalized_for_placeholders("a\\]b")
