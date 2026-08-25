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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


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


def test_the_canonical_template_shape_passes() -> None:
    """The gate must not reject a log written to the document it points at.

    ``debate_log_evidence_gap``'s failure message cites
    ``.claude/skills/adr-review/references/artifacts.md``. That template labels
    its roster "Agent Positions" and its table column "Agent", so a reviewer
    check that knew only the six role slugs blocked the committer and then sent
    them to the document they had followed.
    """
    template = (
        "# ADR Debate Log: Example Title\n\n"
        "## Summary\n\n"
        "- **Rounds**: 2\n"
        "- **Outcome**: Consensus\n"
        "- **Final Status**: accepted\n\n"
        "## Round 2 Summary\n\n"
        "### Key Issues Addressed\n\n"
        "- The trust boundary was not written down anywhere.\n"
        "- The rollback path assumed a backup that is not taken.\n\n"
        "### Agent Positions\n\n"
        "| Agent | Position |\n|-------|----------|\n"
        "| gpt-5 | Accept |\n| reviewer-two | Disagree-and-Commit |\n"
    )
    assert policy.debate_log_evidence_gap(template) is None


def test_an_unreadable_staged_log_cannot_satisfy_coverage(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log whose index blob will not read contributes nothing, and blocks.

    ``_staged_debate_log_contents`` drops such a log from the map rather than
    raising. That drop must not become a way past the gate: a dropped log
    supplies no coverage either, so the staged id stays uncovered and the gate
    returns 1.

    This pins the fail-closed outcome, not the branch. Mutating the drop to
    ``contents[path] = content or ""`` still returns 1, because an empty string
    fails the byte floor instead. Killing that mutation needs a probe that can
    tell the two rejection reasons apart, which the exit code alone cannot.
    """
    _edit(repo, ADR_42, "Rewritten decision text.")
    _git(repo, "add", ADR_42)
    _stage_log(repo, "ADR-042-debate-log.md", GENUINE_LOG)

    monkeypatch.setattr(policy, "_read_index_blob", lambda *_args, **_kwargs: None)

    assert policy.check_adr_review_policy([ADR_42], repo) == 1


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


def test_every_debate_log_on_main_still_passes() -> None:
    """Calibration pin: the thresholds must not false-block committed evidence."""
    critique = _ROOT / ".agents" / "critique"
    logs = sorted(path for path in critique.glob("*.md") if "debate" in path.name)
    assert len(logs) >= 70, "expected the calibration corpus to be present"

    rejected = {
        path.name: gap
        for path in logs
        if (gap := policy.debate_log_evidence_gap(path.read_text(errors="replace"))) is not None
    }
    assert rejected == {}


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
