"""Runtime behavior of the auto-merge exemption in `/pr-autofix`.

Refs #5094. Split from `test_pr_autofix_tier_dispatch_runtime.py` when it
crossed the 500-line taste rule, on the seam already there: that file asks what
the parsed tier makes the shell do, this one asks what it takes for a T1 to keep
auto-merge. Both run the same block through the same harness.

The whole file exists because this PR's own tier fix opened the case. While TIER
was pinned at UNKNOWN, `TIER != T1` held for every PR, so the disarm gate
stripped auto-merge from a truncated-fetch PR by accident. Making T1 reachable
removed that accident.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands.pr_autofix_dispatch_harness import DISPATCH_DOCS, run_dispatch

# The T1 exemption must be earned, not assumed (issue #5094 mirror obligation).
#
# `classify_tier` returns T1 on `CanMerge`, and `CanMerge` is `len(reasons) == 0`
# with `fetched_pages_complete` computed after it and never appended to
# `reasons`, so a fetch truncated at the pagination cap that happens to surface
# no unresolved thread and no failing required check classifies T1.
#
# This only became reachable when the tier read was fixed. While TIER was pinned
# at UNKNOWN, `TIER != T1` held for every PR, so the disarm gate stripped
# auto-merge from the truncated-fetch case by accident. Making T1 reachable
# removed that accident, which makes closing it part of this change rather than
# a follow-up: the fix opened the case.


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_t1_from_a_complete_fetch_keeps_its_auto_merge(tmp_path: Path, doc: str) -> None:
    """The positive half. Without this, denying every T1 would also pass."""
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="SQUASH", pages_complete="true")

    assert not run.disarmed, "a T1 backed by a complete fetch lost the auto-merge it earned"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("pages", ["false", "OMIT"])
def test_a_t1_from_an_incomplete_fetch_is_disarmed(tmp_path: Path, doc: str, pages: str) -> None:
    """Both unproven shapes: the producer said false, and it said nothing.

    `OMIT` is what a producer predating the field emits. Defaulting a missing
    field to complete would fail open on exactly the state that must not buy a
    merge, so the command accepts only the literal `true`.
    """
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="SQUASH", pages_complete=pages)

    assert run.disarmed, (
        "a T1 whose merge-readiness fetch was incomplete kept auto-merge armed; "
        "GitHub can then land it without the readiness ever being proven"
    )
    assert "--disable" in run.disarm_argv
    assert "incomplete" in run.stdout, "the operator was not told why it disarmed"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_completeness_does_not_rescue_a_non_t1(tmp_path: Path, doc: str) -> None:
    """A complete fetch is necessary for the exemption, never sufficient."""
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", pages_complete="true")

    assert run.disarmed, "a complete fetch granted the T1 exemption to a T3"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_an_incomplete_fetch_is_reported_as_false_not_unknown(tmp_path: Path, doc: str) -> None:
    """The producer said `false`; the operator must not be told `unknown`.

    Both values deny the T1 exemption, so every assertion above holds either
    way. That is precisely why this one is needed: the first version of the
    read used jq's `//`, which fires on `false` as well as `null`, and the
    whole suite stayed green while an incomplete fetch was relabelled as an
    unreadable one. A reviewer caught it, not a test.

    The two states are genuinely different and a later reader will act on the
    difference: `false` means the producer measured the fetch and found it
    truncated, `unknown` means no measurement reached us at all. Anyone adding
    a `= "false"` branch on top of the collapsing read would find it dead.
    """
    reported = run_dispatch(
        tmp_path / "false", doc, tier="T1", auto_merge="SQUASH", pages_complete="false"
    )
    assert "fetched_pages_complete=false" in reported.stdout, (
        "an incomplete fetch the producer measured was reported as something else"
    )


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_missing_field_is_reported_as_unknown(tmp_path: Path, doc: str) -> None:
    """The other half, so the test above cannot pass by reporting one label."""
    omitted = run_dispatch(
        tmp_path / "omit", doc, tier="T1", auto_merge="SQUASH", pages_complete="OMIT"
    )
    assert "fetched_pages_complete=unknown" in omitted.stdout


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize(
    "raw",
    ['RAW:"true"', 'RAW:"false"', "RAW:1", 'RAW:"yes"', "RAW:[]"],
    ids=["string-true", "string-false", "number", "string-yes", "array"],
)
def test_a_wrong_typed_completeness_value_never_buys_the_exemption(
    tmp_path: Path, doc: str, raw: str
) -> None:
    """Malformed evidence must deny, and the string `"true"` is the trap.

    The repair for the `//` bug used a bare `tostring`, which converts without
    checking the JSON type, so a producer emitting the *string* `"true"` came
    out as `true` and kept auto-merge armed. That is the worse direction of the
    two: the earlier bug mislabelled a denial, this one granted a merge on
    evidence the command could not actually read.

    `"false"` is here as well, even though it denies either way. Without it the
    case set would only cover values that differ in outcome, and the next reader
    could not tell whether the type check or the value check did the work.
    """
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="SQUASH", pages_complete=raw)

    assert run.disarmed, (
        f"a completeness value of {raw[4:]} is not a boolean the command can trust, "
        "yet it kept auto-merge armed on a T1"
    )
    assert "fetched_pages_complete=unknown" in run.stdout, (
        "a wrong-typed value was reported as if it had been read"
    )
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_inverted_control_can_fail(tmp_path: Path, doc: str) -> None:
    """The inverted control's own control, executable rather than recorded.

    `test_a_comment_reword_changes_nothing` asserts two runs agree. On its own
    that is satisfiable by a harness which cannot observe anything, so the claim
    it rests on is that a *non-inert* edit would make the two runs differ. That
    claim was demonstrated by hand and written into a docstring and a QA report,
    which is prose: nothing re-runs it when the harness changes underneath.

    This asserts it. The edit inverts the disarm gate's auto-merge test, which
    changes the outcome for the case both controls run, and the two runs must
    then disagree. If the harness ever stops seeing behavior, this fails and the
    inverted control above is exposed as vacuous instead of quietly passing.

    Verified to be discriminating rather than assumed: the first hand-run
    attempt flipped `[ "$TIER" != "T1" ]` to `!= "T9"`, and T3 sits on the same
    side of both, so the edit changed nothing and the probe reported nothing.
    """
    shipped = run_dispatch(tmp_path / "shipped", doc, tier="T3", auto_merge="SQUASH")
    non_inert = run_dispatch(
        tmp_path / "mutated",
        doc,
        tier="T3",
        auto_merge="SQUASH",
        block_edit=('[ "$AUTO_MERGE" != "null" ]', '[ "$AUTO_MERGE" = "null" ]'),
    )

    assert shipped.disarmed, "the shipped block should disarm an armed non-T1 PR"
    assert not non_inert.disarmed, "the inverted gate should not disarm"
    assert non_inert.stdout != shipped.stdout, (
        "a behavior-changing edit produced byte-identical output, so the "
        "inverted control that asserts agreement cannot be distinguishing "
        "anything and its passing means nothing"
    )
