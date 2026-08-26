"""The ADR debate-log gate must test for a review, not for a filename.

Issue #5205 proved two defects in ``check_adr_review_policy`` on ``main``:

1. The evidence test was a filename pattern plus an ADR-id substring, so a
   7-byte ``.agents/critique/x-debate.md`` containing ``ADR-042`` cleared it.
2. The coverage test was ``any()`` over the staged logs against the *union* of
   staged ADR ids, so one log naming one record authorized every ADR staged in
   the same commit.

Supersession is access-control-adjacent (a superseded record stops binding) and
a ``superseded-by`` edit is never frontmatter-exempt, so it always routes here.
Both defects therefore get a regression test that fails without the fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy
from tests.validation._adr_debate_repo import (
    ADR_05,
    ADR_42,
    GENUINE_LOG,
    _edit,
    _git,
    _stage_log,
)


def test_genuine_log_covering_the_single_staged_adr_passes(adr_debate_repo: Path) -> None:
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 0


def test_seven_byte_stub_does_not_clear_the_gate(adr_debate_repo: Path, capsys) -> None:
    """The exact reproduction from issue #5205."""
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "x-debate.md", "ADR-042")

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    assert "is not a debate log" in capsys.readouterr().err


def test_every_staged_adr_must_be_named_in_the_staged_logs(adr_debate_repo: Path, capsys) -> None:
    """Defect 2: one log naming one ADR used to authorize the whole staged set."""
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _edit(adr_debate_repo, ADR_05, "Retired by a supersession edit.")
    _git(adr_debate_repo, "add", ADR_42, ADR_05)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)

    assert policy.check_adr_review_policy([ADR_42, ADR_05], adr_debate_repo) == 1
    assert "ADR-005" in capsys.readouterr().err


def test_logs_covering_every_staged_adr_pass(adr_debate_repo: Path) -> None:
    """No false block: coverage may be spread across several staged logs."""
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _edit(adr_debate_repo, ADR_05, "Retired by a supersession edit.")
    _git(adr_debate_repo, "add", ADR_42, ADR_05)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)
    _stage_log(adr_debate_repo, "ADR-005-debate-log.md", GENUINE_LOG.replace("ADR-042", "ADR-005"))

    assert policy.check_adr_review_policy([ADR_42, ADR_05], adr_debate_repo) == 0


def test_one_log_naming_both_staged_adrs_passes(adr_debate_repo: Path) -> None:
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _edit(adr_debate_repo, ADR_05, "Retired by a supersession edit.")
    _git(adr_debate_repo, "add", ADR_42, ADR_05)
    _stage_log(
        adr_debate_repo,
        "ADR-042-005-debate-log.md",
        GENUINE_LOG.replace("ADR-042", "ADR-042 and ADR-005"),
    )

    assert policy.check_adr_review_policy([ADR_42, ADR_05], adr_debate_repo) == 0


def test_a_genuine_log_staged_beside_a_stub_still_blocks(adr_debate_repo: Path) -> None:
    """Edge: the stub is checked even when a real log covers every staged id."""
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG)
    _stage_log(adr_debate_repo, "x-debate.md", "ADR-042")

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1


@pytest.mark.parametrize(
    ("name", "content", "expected_gap"),
    [
        ("empty", "", "shorter than"),
        ("stub", "ADR-042", "shorter than"),
        ("padded_prose", "ADR-042 " * 80, "markdown sections"),
        (
            "headings_only",
            "# One\n\n## Two\n\n### Three\n\n" + "ADR-042 filler text. " * 30,
            "no reviewer attribution",
        ),
        (
            "reviewer_without_verdict",
            "# One\n\n## Participants\n\n### Three\n\n" + "ADR-042 filler text. " * 30,
            "no verdict",
        ),
    ],
)
def test_evidence_gaps_are_named(name: str, content: str, expected_gap: str) -> None:
    gap = policy.debate_log_evidence_gap(content)
    assert gap is not None, name
    assert expected_gap in gap, (name, gap)


def test_self_review_log_without_a_full_roster_passes() -> None:
    """No false block: single-reviewer logs exist in .agents/critique on main."""
    content = (
        "# ADR-068/071/085 Metrics Update Debate Log\n\n"
        "## Context\n\nIssue #4917 adds a new PreToolUse hook, so the metrics in\n"
        "ADR-068, ADR-071 and ADR-085 need updating.\n\n"
        "## Changes\n\n- Shim count: 3 to 4\n- Timeout budget: 110s to 120s\n\n"
        "## Verdict\n\n**Self-review: ACCEPT**\n\n"
        "Rationale: mechanical metrics updates that follow from adding a hook.\n"
        "No architectural decision changes. The host timeout still has headroom.\n"
    )
    assert policy.debate_log_evidence_gap(content) is None


def test_positions_table_counts_as_a_verdict() -> None:
    """A per-role table records the verdict through its own column header.

    The header line is itself the verdict label and the rows fall inside the
    window, so this reaches the one bounded branch rather than a separate
    unbounded one. The second branch that used to serve this shape accepted
    any pipe row with a role and a decision word anywhere in the document, and
    was deleted as both loose and redundant; the negative case is pinned by
    ``test_a_notes_table_row_is_not_a_positions_table_verdict``.
    """
    content = (
        "# ADR-084 Debate Log\n\n## Round 1\n\n### Table\n\n"
        "| Agent | Stance | Note |\n|---|---|---|\n"
        "| architect | BLOCK | P0-1: placement inverts rule 1. |\n"
        "| security | BLOCK | P0-2: orphaned line-number citations. |\n"
    ) + "\nFurther discussion of ADR-084 and its consequences follows here.\n" * 4

    # The heading is deliberately neutral text that does not itself match
    # DEBATE_LOG_VERDICT_LABEL_RE (unlike a heading such as "Agent stances"
    # would). The only label in the fixture is the table's own column
    # header, so a header that stopped being read as a label would fail
    # this test rather than let the heading supply the verdict instead.
    # Found by review: the prior heading matched the same regex, so its
    # six-line window already reached the BLOCK rows and this test passed
    # even with the table-header path broken.
    labels = [
        line for line in content.splitlines() if policy.DEBATE_LOG_VERDICT_LABEL_RE.search(line)
    ]
    assert labels == ["| Agent | Stance | Note |"], labels

    assert policy.debate_log_evidence_gap(content) is None


def test_a_log_writing_the_unpadded_id_still_covers_a_padded_record(adr_debate_repo: Path) -> None:
    """Prose says ADR-42; the filename says ADR-042. Both name one record.

    ``ADR_ID_RE`` matches digits literally, so these are different strings.
    Filenames here are zero-padded to three digits and prose is not. Under the
    old ``any()`` test a sibling log usually rescued the mismatch; requiring
    full coverage would make it a false block on a genuine review, so the
    comparison folds the padding away.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-042-debate-log.md", GENUINE_LOG.replace("ADR-042", "ADR-42"))

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 0


def test_padding_folding_does_not_make_unrelated_ids_match(adr_debate_repo: Path, capsys) -> None:
    """Negative control: folding zeros must not collapse distinct records."""
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _git(adr_debate_repo, "add", ADR_42)
    _stage_log(adr_debate_repo, "ADR-005-debate-log.md", GENUINE_LOG.replace("ADR-042", "ADR-5"))

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
    assert "ADR-042" in capsys.readouterr().err, "the error names the staged filename form"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ADR-042", "ADR-42"),
        ("ADR-42", "ADR-42"),
        ("adr-0042", "ADR-42"),
        ("ADR-000", "ADR-0"),
        ("ADR-0", "ADR-0"),
    ],
)
def test_adr_id_normalization(raw: str, expected: str) -> None:
    """Edge: an all-zero id must fold to a key, not to the empty string."""
    assert policy._normalized_record_number(raw) == expected


def test_an_incidental_mention_covers_a_staged_id(adr_debate_repo: Path) -> None:
    """Document the coverage rule's edge: any mention counts, reviewed or not.

    ``_referenced_adr_ids`` scans the whole log, so a log that genuinely
    reviews ADR-042 and cites ADR-005 only in a footer covers both. This is the
    one-line semantics issue #5205 proposed, so it ships as specified, but
    nothing previously said either way and a reader could reasonably assume the
    gate distinguishes a review from a citation. It does not.
    """
    _edit(adr_debate_repo, ADR_42, "Rewritten decision text.")
    _edit(adr_debate_repo, ADR_05, "Retired by a supersession edit.")
    _git(adr_debate_repo, "add", ADR_42, ADR_05)
    _stage_log(
        adr_debate_repo,
        "ADR-042-debate-log.md",
        GENUINE_LOG + "\n## References\n\n- Refs ADR-005 for background.\n",
    )

    assert policy.check_adr_review_policy([ADR_42, ADR_05], adr_debate_repo) == 0


def test_frontmatter_only_implemented_flip_stays_exempt(adr_debate_repo: Path) -> None:
    """Pin the one correctly scoped control: widening it would reopen the hole."""
    target = adr_debate_repo / ADR_42
    target.write_text("---\nstatus: proposed\nimplemented: false\n---\n\n# Title\n\nBody.\n")
    _git(adr_debate_repo, "add", ADR_42)
    _git(adr_debate_repo, "commit", "-m", "add frontmatter")

    target.write_text("---\nstatus: proposed\nimplemented: true\n---\n\n# Title\n\nBody.\n")
    _git(adr_debate_repo, "add", ADR_42)

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 0


def test_frontmatter_status_flip_is_not_exempt(adr_debate_repo: Path) -> None:
    """A status change is a lifecycle change and must route through the gate."""
    target = adr_debate_repo / ADR_42
    target.write_text("---\nstatus: proposed\nimplemented: false\n---\n\n# Title\n\nBody.\n")
    _git(adr_debate_repo, "add", ADR_42)
    _git(adr_debate_repo, "commit", "-m", "add frontmatter")

    target.write_text("---\nstatus: accepted\nimplemented: false\n---\n\n# Title\n\nBody.\n")
    _git(adr_debate_repo, "add", ADR_42)

    assert policy.check_adr_review_policy([ADR_42], adr_debate_repo) == 1
