"""Threshold, boundary, and calibration cases for the ADR debate-log gate.

Split out of ``test_git_hook_policy_adr_debate_evidence.py``, which reached 532
lines and tripped the repository's 500-line file-size rule. The split is along a
real seam rather than at an arbitrary line: every case here exercises
``debate_log_evidence_gap`` and its helpers as pure functions of text, with no
git repository and no staged index. The sibling module keeps the cases that
stage files and call ``check_adr_review_policy`` end to end.

Each boundary test asserts the measured quantity before the behavior, so a
future threshold change cannot silently reinterpret what the test proves.

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


def test_the_weakest_currently_passing_log_is_pinned() -> None:
    """Document the floor these four signals actually enforce.

    This log is deliberately the thinnest thing that clears every signal: a
    verdict label with a decision word inside the window, the token "agent" as
    attribution, three headings, and filler to clear the byte floor. It says
    nothing about any review that happened.

    It passes, and that is the disclosed trade in ``debate_log_evidence_gap``:
    every signal is a property of text the committer controls. The test exists
    so the floor is visible and so a future tightening has a reference point to
    move, rather than leaving the weakest passing shape undocumented.

    The paired negative below pins the one thing that does constrain the shape:
    the decision word has to sit within DEBATE_LOG_VERDICT_WINDOW_LINES of the
    label, so a stray "Accepted" elsewhere in the file does not manufacture a
    verdict.
    """
    weakest = (
        "# D\n\n## Outcome\n\nAccepted.\n\n### Notes\n\nagent\n\n"
        + "Filler prose about ADR-042 that carries no review content. " * 6
    )
    assert policy.debate_log_evidence_gap(weakest) is None

def test_a_decision_word_outside_the_verdict_window_is_not_a_verdict() -> None:
    """Negative control for the window that bounds the loosest passing shape."""
    spread = (
        "# D\n\n## Outcome\n\n### Notes\n\nagent\n\n"
        + "\n" * 8
        + "Accepted.\n"
        + "Filler prose about ADR-042 that carries no review content. " * 6
    )
    gap = policy.debate_log_evidence_gap(spread)
    assert gap is not None
    assert "no verdict" in gap

def _log_of_exactly(byte_count: int) -> str:
    """Build a passing-shaped log padded to exactly ``byte_count`` bytes."""
    head = "# A\n\n## Participants\n\narchitect\n\n### Verdict\n\nAccepted.\n"
    pad = byte_count - len(head.encode("utf-8"))
    assert pad >= 0, "head already exceeds the requested size"
    return head + ("x" * pad)

def test_the_byte_floor_is_exact() -> None:
    """One byte under is rejected; exactly the floor is not."""
    under = _log_of_exactly(policy.DEBATE_LOG_MIN_BYTES - 1)
    at = _log_of_exactly(policy.DEBATE_LOG_MIN_BYTES)

    assert len(under.encode("utf-8")) == policy.DEBATE_LOG_MIN_BYTES - 1
    assert len(at.encode("utf-8")) == policy.DEBATE_LOG_MIN_BYTES

    gap = policy.debate_log_evidence_gap(under)
    assert gap is not None
    assert "shorter than" in gap
    assert policy.debate_log_evidence_gap(at) is None

def test_the_section_floor_is_exact() -> None:
    """Two headings are rejected; three are not, all else held equal."""
    body = "\n\narchitect\n\nVerdict: Accepted.\n" + ("filler prose. " * 30)
    two = "# A\n\n## Participants" + body
    three = "# A\n\n## Participants\n\n### Round 1" + body

    assert len(policy.DEBATE_LOG_HEADING_RE.findall(two)) == 2
    assert len(policy.DEBATE_LOG_HEADING_RE.findall(three)) == 3

    gap = policy.debate_log_evidence_gap(two)
    assert gap is not None
    assert "markdown sections" in gap
    assert policy.debate_log_evidence_gap(three) is None

@pytest.mark.parametrize(
    ("offset", "expected_verdict"),
    [
        (policy.DEBATE_LOG_VERDICT_WINDOW_LINES - 1, True),
        (policy.DEBATE_LOG_VERDICT_WINDOW_LINES, False),
    ],
)
def test_the_verdict_window_is_exact(offset: int, expected_verdict: bool) -> None:
    """The window is ``lines[i : i + N]``, so the last accepted offset is N-1.

    Placing the decision one line further must not count, or the window is not
    bounding anything.
    """
    lines = ["## Outcome"] + ["filler"] * (offset - 1) + ["Accepted."]
    content = "\n".join(lines)
    assert content.splitlines().index("Accepted.") == offset

    assert policy._has_verdict(content) is expected_verdict

@pytest.mark.parametrize(
    "prose",
    [
        "The architecture is sound and the boundaries are well documented.",
        "This securityless path needs no further hardening at all.",
        "The analysis section explains the tradeoff in full detail here.",
    ],
)
def test_prose_about_the_subject_is_not_reviewer_attribution(prose: str) -> None:
    """A word that merely contains a role name must not stand in for a reviewer.

    Without word boundaries, "architecture" satisfies "architect" and
    "securityless" satisfies "security", so a log discussing the subject
    matter would clear attribution while naming nobody.
    """
    assert not policy.DEBATE_LOG_REVIEWER_RE.search(prose)

@pytest.mark.parametrize(
    "attributed",
    ["The architect reviewed it.", "Participants: two.", "Self-review: ACCEPT", "agent notes"],
)
def test_real_attribution_still_matches(attributed: str) -> None:
    """Positive control: the boundaries must not break genuine attribution."""
    assert policy.DEBATE_LOG_REVIEWER_RE.search(attributed)

def test_every_debate_log_in_the_working_tree_still_passes() -> None:
    """Calibration pin: the thresholds must not false-block committed evidence.

    Scope, stated precisely because the obvious reading is wrong: this reads
    the corpus in the current working tree, not at any named ref. Local edits,
    untracked logs, or a change that touches both the logs and this gate move
    what it measures without main having moved. It is a guard against a
    threshold change silently starting to reject real reviews, not a claim
    about main's contents at any point in time.
    """
    critique = _ROOT / ".agents" / "critique"
    logs = sorted(path for path in critique.glob("*.md") if "debate" in path.name)
    assert len(logs) >= 70, "expected the calibration corpus to be present"

    rejected = {
        path.name: gap
        for path in logs
        if (gap := policy.debate_log_evidence_gap(path.read_text(errors="replace"))) is not None
    }
    assert rejected == {}

def test_invalid_utf8_bytes_do_not_inflate_toward_the_byte_floor() -> None:
    """A short blob of invalid bytes must not clear a floor it does not reach.

    The staged blob is decoded with ``errors="replace"``, so each invalid byte
    becomes U+FFFD and re-encodes to three. 100 on-disk bytes measured 300 and
    cleared the stated 300-byte floor before ``_evidence_byte_count`` existed.
    """
    decoded = (b"\xff" * 100).decode("utf-8", errors="replace")
    assert len(decoded.encode("utf-8")) == 3 * 100, "the inflation is what is being pinned"

    gap = policy.debate_log_evidence_gap(decoded)
    assert gap == f"shorter than {policy.DEBATE_LOG_MIN_BYTES} bytes"

def test_replacement_characters_do_not_pad_a_real_log_over_the_floor() -> None:
    """Negative pair: real text just under the floor stays under it when padded."""
    body = "x" * (policy.DEBATE_LOG_MIN_BYTES - 1)
    assert policy.debate_log_evidence_gap(body) is not None

    padded = body + (b"\xff" * 50).decode("utf-8", errors="replace")
    assert policy.debate_log_evidence_gap(padded) == (
        f"shorter than {policy.DEBATE_LOG_MIN_BYTES} bytes"
    )

def test_valid_multibyte_text_still_counts_its_real_bytes() -> None:
    """Positive control: the fix must not penalize genuine non-ASCII prose."""
    # Well-formed U+FFFD written by an author counts as one character of real
    # text, so stripping it is the one case where this measurement is stricter
    # than the on-disk length. Everything else measures exactly.
    text = "\u00e9" * 200
    assert len(text.encode("utf-8")) == 400
    assert policy._evidence_byte_count(text) == 400


_DEBATE_LOG_TEMPLATE_DOC = (
    _ROOT / ".claude" / "skills" / "adr-review" / "references" / "artifacts.md"
)


_DEBATE_LOG_TEMPLATE_RE = re.compile(
    r"Save to: `\.agents/critique/ADR-NNN-debate-log\.md`\s*\n+```markdown\n(.*?)\n```",
    re.DOTALL,
)


def test_an_owner_direction_record_without_a_verdict_label_passes() -> None:
    """A decision recorded by an owner is a verdict, however it is headed.

    Three of the 86 committed logs conclude without ever writing "verdict":
    an owner decides and the record states the decision and its authority.
    ``DEBATE_LOG_VERDICT_LABEL_RE`` originally covered only debate vocabulary
    and false-blocked every one of them. CI caught it, not local calibration,
    because the corpus grew from 79 to 86 while this change was open.
    """
    record = (
        "# Owner Direction: ADR-005 Prose Status Duplication\n\n"
        "## Governing evidence\n\n"
        "The architect and the repository owner accepted the change. "
        + "The reasoning is recorded here rather than in a debate. " * 6
        + "\n\n## What still holds\n\n"
        + "The rule the record states survives unchanged. " * 4
    )

    # Isolate the verdict signal: the other four must already be satisfied, or
    # this passes or fails for a reason it does not name.
    assert policy._evidence_byte_count(record) >= policy.DEBATE_LOG_MIN_BYTES
    assert policy.DEBATE_LOG_REVIEWER_RE.search(record)
    assert policy.DEBATE_LOG_VERDICT_LABEL_RE.search(record)

    assert policy.debate_log_evidence_gap(record) is None


def test_a_decision_word_with_no_label_of_any_kind_is_still_not_a_verdict() -> None:
    """Negative pair: widening the label list did not remove the label."""
    unlabelled = (
        "# Notes\n\n## Background\n\n"
        + "The change was accepted at some point by somebody. " * 8
        + "\n\n## More\n\nThe architect wrote this down later.\n"
    )

    gap = policy.debate_log_evidence_gap(unlabelled)
    assert gap is not None and gap.startswith("no verdict"), gap


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
        ("reviewer attribution", bool(policy.DEBATE_LOG_REVIEWER_RE.search(untouched))),
        ("verdict", policy._has_verdict(untouched)),
    ):
        assert satisfied, f"fixture no longer reaches the placeholder check: {signal_name} fails"

    gap = policy.debate_log_evidence_gap(untouched)
    assert gap is not None and gap.startswith("unfilled template placeholders"), gap


_ADR_REVIEW_SKILL = _ROOT / ".claude" / "skills" / "adr-review" / "SKILL.md"


def test_the_quoted_role_table_is_still_verbatim_in_the_skill() -> None:
    """Drift guard for the role table quoted above DEBATE_LOG_ROLES.

    `.claude/rules/canonical-source-mirror.md` requires the contract quoted
    character for character, which makes the quote a claim that can rot. The
    comment cites the "## Agent Roles" heading rather than a line range,
    because a range goes stale on any edit above it while saying nothing about
    whether the quoted text still matches. This checks the text.
    """
    skill = _ADR_REVIEW_SKILL.read_text(encoding="utf-8")
    assert "## Agent Roles" in skill, (
        f"the cited heading is gone from {_ADR_REVIEW_SKILL}; the quote above "
        "DEBATE_LOG_ROLES now points at nothing"
    )

    missing = [role for role in policy.DEBATE_LOG_ROLES if f"**{role}**" in skill]
    absent = [role for role in policy.DEBATE_LOG_ROLES if f"**{role}**" not in skill]
    assert not absent, (
        f"these roles are no longer in the {_ADR_REVIEW_SKILL} roster, so the "
        f"quoted copy has drifted from the table it mirrors: {absent}"
    )
    assert len(missing) == len(policy.DEBATE_LOG_ROLES) == 6


def test_every_template_placeholder_is_still_in_the_canonical_template() -> None:
    """Drift guard: the hardcoded literals must match the document they quote.

    ``DEBATE_LOG_TEMPLATE_PLACEHOLDERS`` is a verbatim copy per
    `.claude/rules/canonical-source-mirror.md`. If the template is reworded and
    this list is not, the gate silently stops rejecting unfilled copies of the
    new template while still claiming to.
    """
    template = _canonical_debate_log_template()
    missing = [
        placeholder
        for placeholder in policy.DEBATE_LOG_TEMPLATE_PLACEHOLDERS
        if placeholder not in template
    ]
    assert not missing, (
        f"these placeholders are no longer in {_DEBATE_LOG_TEMPLATE_DOC}, so the "
        f"quoted copy has drifted from the template it mirrors: {missing}"
    )
