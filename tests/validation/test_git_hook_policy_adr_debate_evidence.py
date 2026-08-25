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

import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy

ADR_42 = ".agents/architecture/ADR-042-python-migration-strategy.md"
ADR_05 = ".agents/architecture/ADR-005-powershell-only-scripting.md"

GENUINE_LOG = """# ADR Debate Log: Example

## Participants

- architect agent (primary reviewer)
- security agent

## Verdict: Accept

The architect reviewed ADR-042 and found no P0 or P1 issues. The decision
text matches the implementation and the alternatives considered are
reasonable. Template compliance confirmed against the canonical structure.

## Notes

P2 observation: evaluation order clarification added to the ADR text so a
later reader does not have to reconstruct it from the implementation.
"""


_DEBATE_LOG_TEMPLATE_DOC = (
    _ROOT / ".claude" / "skills" / "adr-review" / "references" / "artifacts.md"
)
# The fence is keyed to the "Save to:" line above it so a later fence added to
# the same document cannot be picked up by accident.
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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # encoding and errors are explicit to match the convention at
    # tests/test_lefthook_integration.py:107 and
    # tests/validation/test_session_log_optional.py:142. Without them, text
    # mode decodes with the locale codec, which on Windows can fail on git's
    # UTF-8 output and leave stdout unset.
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    for relative in (ADR_42, ADR_05):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Title\n\n## Status\n\nAccepted\n\n## Decision\n\nBaseline.\n")
    (repo / ".agents" / "critique").mkdir(parents=True, exist_ok=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")


def _edit(repo: Path, relative: str, body: str) -> None:
    (repo / relative).write_text(f"# Title\n\n## Status\n\nAccepted\n\n## Decision\n\n{body}\n")


def _stage_log(repo: Path, name: str, content: str) -> str:
    relative = f".agents/critique/{name}"
    (repo / relative).write_text(content)
    _git(repo, "add", relative)
    return relative


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_repo(tmp_path)
    return tmp_path


def test_genuine_log_covering_the_single_staged_adr_passes(repo: Path) -> None:
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)

    assert policy.check_adr_review_policy([ADR_42], repo) == 0


def test_seven_byte_stub_does_not_clear_the_gate(repo: Path, capsys) -> None:
    """The exact reproduction from issue #5205."""
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "x-debate.md", "ADR-042")

    assert policy.check_adr_review_policy([ADR_42], repo) == 1
    assert "is not a debate log" in capsys.readouterr().err


def test_every_staged_adr_must_be_named_in_the_staged_logs(repo: Path, capsys) -> None:
    """Defect 2: one log naming one ADR used to authorize the whole staged set."""
    _edit(repo, ADR_42, "Rewritten decision text.")
    _edit(repo, ADR_05, "Retired by a supersession edit.")
    _git(repo, "add", ADR_42, ADR_05)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)

    assert policy.check_adr_review_policy([ADR_42, ADR_05], repo) == 1
    assert "ADR-005" in capsys.readouterr().err


def test_logs_covering_every_staged_adr_pass(repo: Path) -> None:
    """No false block: coverage may be spread across several staged logs."""
    _edit(repo, ADR_42, "Rewritten decision text.")
    _edit(repo, ADR_05, "Retired by a supersession edit.")
    _git(repo, "add", ADR_42, ADR_05)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)
    _stage_log(repo, "ADR-005-debate-log.md", GENUINE_LOG.replace("ADR-042", "ADR-005"))

    assert policy.check_adr_review_policy([ADR_42, ADR_05], repo) == 0


def test_one_log_naming_both_staged_adrs_passes(repo: Path) -> None:
    _edit(repo, ADR_42, "Rewritten decision text.")
    _edit(repo, ADR_05, "Retired by a supersession edit.")
    _git(repo, "add", ADR_42, ADR_05)
    _stage_log(
        repo,
        "ADR-042-005-debate-log.md",
        GENUINE_LOG.replace("ADR-042", "ADR-042 and ADR-005"),
    )

    assert policy.check_adr_review_policy([ADR_42, ADR_05], repo) == 0


def test_a_genuine_log_staged_beside_a_stub_still_blocks(repo: Path) -> None:
    """Edge: the stub is checked even when a real log covers every staged id."""
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)
    _stage_log(repo, "x-debate.md", "ADR-042")

    assert policy.check_adr_review_policy([ADR_42], repo) == 1


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
    """ADR-084's log records the verdict one role per table row, not as a label."""
    # No verdict-label word appears anywhere, so the label branch cannot fire
    # and only the table can supply the verdict. Without this the label branch
    # short-circuits and the test passes even with the table branch removed.
    content = (
        "# ADR-084 Debate Log\n\n## Round 1\n\n### Agent stances\n\n"
        "| Agent | Stance | Note |\n|---|---|---|\n"
        "| architect | BLOCK | P0-1: placement inverts rule 1. |\n"
        "| security | BLOCK | P0-2: orphaned line-number citations. |\n"
    ) + "\nFurther discussion of ADR-084 and its consequences follows here.\n" * 4
    assert not policy.DEBATE_LOG_VERDICT_LABEL_RE.search(content), (
        "the fixture must not offer the label branch a way to short-circuit"
    )
    assert policy.debate_log_evidence_gap(content) is None


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


def test_an_unreadable_staged_log_cannot_satisfy_coverage(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A log whose index blob will not read is named and blocks."""
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)

    monkeypatch.setattr(policy, "_read_index_blob", lambda *_args, **_kwargs: None)

    assert policy.check_adr_review_policy([ADR_42], repo) == 1
    # Assert the reason, not just the exit code. Before unreadable logs were
    # reported, this blocked only as a side effect of supplying no coverage,
    # so the same 1 came back for a different reason and the case below passed
    # through the gate entirely.
    assert "could not be read" in capsys.readouterr().err


def test_an_unreadable_log_blocks_even_when_a_sibling_covers_every_id(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-open regression: a covering sibling must not excuse an unreadable log.

    ``_staged_debate_log_contents`` used to drop an unreadable log silently.
    With one valid log covering every staged id, the drop left nothing to
    fail on: both checks passed on the sibling and the gate returned 0.
    Reproduced against this exact shape before the fix.

    Distinct from the single-log case above, which blocked for the unrelated
    reason that the dropped log supplied no coverage.
    """
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    good = _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)
    bad = _stage_log(repo, "ADR-042-second-debate.md", GENUINE_LOG)

    real_read = policy._read_index_blob

    def only_the_second_log_fails(root: Path, relative: str) -> bytes | None:
        return None if relative == bad else real_read(root, relative)

    monkeypatch.setattr(policy, "_read_index_blob", only_the_second_log_fails)

    # The sibling is genuinely sufficient on its own, so this fails open unless
    # the unreadable log is reported rather than skipped.
    assert policy.debate_log_evidence_gap(GENUINE_LOG) is None
    assert good != bad

    assert policy.check_adr_review_policy([ADR_42], repo) == 1
    error = capsys.readouterr().err
    assert "could not be read" in error
    assert bad in error, "the error must name the log that would not read"


def test_a_log_writing_the_unpadded_id_still_covers_a_padded_record(repo: Path) -> None:
    """Prose says ADR-42; the filename says ADR-042. Both name one record.

    ``ADR_ID_RE`` matches digits literally, so these are different strings.
    Filenames here are zero-padded to three digits and prose is not. Under the
    old ``any()`` test a sibling log usually rescued the mismatch; requiring
    full coverage would make it a false block on a genuine review, so the
    comparison folds the padding away.
    """
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG.replace("ADR-042", "ADR-42"))

    assert policy.check_adr_review_policy([ADR_42], repo) == 0


def test_padding_folding_does_not_make_unrelated_ids_match(repo: Path, capsys) -> None:
    """Negative control: folding zeros must not collapse distinct records."""
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "ADR-005-debate-log.md", GENUINE_LOG.replace("ADR-042", "ADR-5"))

    assert policy.check_adr_review_policy([ADR_42], repo) == 1
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
    assert policy._normalize_adr_id(raw) == expected


def test_an_incidental_mention_covers_a_staged_id(repo: Path) -> None:
    """Document the coverage rule's edge: any mention counts, reviewed or not.

    ``_referenced_adr_ids`` scans the whole log, so a log that genuinely
    reviews ADR-042 and cites ADR-005 only in a footer covers both. This is the
    one-line semantics issue #5205 proposed, so it ships as specified, but
    nothing previously said either way and a reader could reasonably assume the
    gate distinguishes a review from a citation. It does not.
    """
    _edit(repo, ADR_42, "Rewritten decision text.")
    _edit(repo, ADR_05, "Retired by a supersession edit.")
    _git(repo, "add", ADR_42, ADR_05)
    _stage_log(
        repo,
        "ADR-042-debate-log.md",
        GENUINE_LOG + "\n## References\n\n- Refs ADR-005 for background.\n",
    )

    assert policy.check_adr_review_policy([ADR_42, ADR_05], repo) == 0


def test_frontmatter_only_implemented_flip_stays_exempt(repo: Path) -> None:
    """Pin the one correctly scoped control: widening it would reopen the hole."""
    target = repo / ADR_42
    target.write_text("---\nstatus: proposed\nimplemented: false\n---\n\n# Title\n\nBody.\n")
    _git(repo, "add", ADR_42)
    _git(repo, "commit", "-m", "add frontmatter")

    target.write_text("---\nstatus: proposed\nimplemented: true\n---\n\n# Title\n\nBody.\n")
    _git(repo, "add", ADR_42)

    assert policy.check_adr_review_policy([ADR_42], repo) == 0


def test_frontmatter_status_flip_is_not_exempt(repo: Path) -> None:
    """A status change is a lifecycle change and must route through the gate."""
    target = repo / ADR_42
    target.write_text("---\nstatus: proposed\nimplemented: false\n---\n\n# Title\n\nBody.\n")
    _git(repo, "add", ADR_42)
    _git(repo, "commit", "-m", "add frontmatter")

    target.write_text("---\nstatus: accepted\nimplemented: false\n---\n\n# Title\n\nBody.\n")
    _git(repo, "add", ADR_42)

    assert policy.check_adr_review_policy([ADR_42], repo) == 1
