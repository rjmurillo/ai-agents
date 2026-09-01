"""Runtime behavior of `/pr-autofix`'s tier-dispatch block.

Refs #5094. The static contract gate proves each `jq` read names a field its
producer emits. It cannot say what the parsed tier makes the shell do, which is
the half that matters: the defect was a stuck sentinel reaching two gates that
compare it in opposite directions. These cases execute the block.

The harness lives in `pr_autofix_dispatch_harness.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.commands.pr_autofix_dispatch_harness import (
    CI_ONLY_ENV,
    DISPATCH_DOCS,
    PREFIX_TIER_READ,
    REPO_ROOT,
    extract_dispatch,
    run_dispatch,
    write_fake_scripts,
)


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_t1_with_auto_merge_armed_keeps_it(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="SQUASH")

    assert not run.disarmed, "a T1 PR lost the auto-merge it earned"
    assert not run.round_cap_called, "the round cap fired outside T3/T4"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("tier", ["T3", "T4"])
def test_round_cap_runs_for_t3_and_t4(tmp_path: Path, doc: str, tier: str) -> None:
    run = run_dispatch(tmp_path, doc, tier=tier, round_action="ACT")

    assert run.round_cap_called, f"the round-cap breaker stayed inert on {tier}"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_round_cap_escalation_disarms_before_handing_the_pr_to_a_human(
    tmp_path: Path, doc: str
) -> None:
    """The escalated PR must not be left able to merge itself.

    This test asserted the opposite until Copilot filed it as CWE-284, and the
    old assertion read `assert not run.disarmed, "the loop kept acting after the
    round cap escalated"`. The reasoning was wrong in a way worth keeping on the
    record: disarming is not acting on a PR, it is taking a capability away from
    one, so it was never the thing the escalation needed to stop.

    Leaving it armed is the harm. The breaker escalates precisely when a PR has
    burned its rounds and needs a human, and native auto-merge does not wait for
    this session's completion gate, so the PR could land on its own with
    readiness never proven. The gates are now ordered so the disarm runs first.

    Opened by this PR rather than found beside it: a pinned UNKNOWN never
    matched T3 or T4, so the breaker never fired and the disarm gate reached
    every armed PR anyway.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        round_action="ESCALATE",
    )

    assert run.round_cap_called
    assert "Stopping thread-fix loop" in run.stdout
    assert run.cleaned_up
    assert run.disarmed, (
        "an escalated PR was handed to a human with auto-merge still armed, so "
        "it can land without this session ever proving it ready"
    )
    assert "--disable" in run.disarm_argv
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_non_t1_with_auto_merge_armed_is_disarmed(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", round_action="ACT")

    assert run.disarmed
    assert "Auto-merge armed on non-T1 PR" in run.stdout
    assert run.reached_end
    # The flags, not just the fact of a call. The fake used to ignore argv, so
    # `--disable` could be mutated to `--enable` and the whole suite stayed
    # green: the gate that strips auto-merge before an unguarded push would
    # instead arm it. Verified surviving before this assertion existed. Stated
    # as that property rather than as the pass count it first carried, which was
    # written as 429 and was wrong by the next commit that added a case.
    assert "--disable" in run.disarm_argv, (
        f"the disarm call did not pass --disable; argv was {run.disarm_argv.strip()!r}"
    )
    assert "--enable" not in run.disarm_argv, (
        f"the disarm call passed --enable; argv was {run.disarm_argv.strip()!r}"
    )


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_unarmed_pr_is_left_alone(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="null", round_action="ACT")

    assert not run.disarmed
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_unreadable_auto_merge_state_skips_instead_of_guessing(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="UNREADABLE")

    assert "Cannot read auto-merge state" in run.stdout
    assert run.cleaned_up
    assert not run.disarmed, "the disarm path fired on no evidence"
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_schema_invalid_auto_merge_state_skips_instead_of_laundering_false(
    tmp_path: Path, doc: str
) -> None:
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="RAW:false")

    assert "Cannot read auto-merge state" in run.stdout
    assert run.cleaned_up
    assert not run.disarmed, "a schema-invalid auto-merge value was treated as unarmed"
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_skipped_mutation_is_not_reported_as_a_failure(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        round_action="ACT",
        mutation_rc="75",
    )

    assert "Failed to disable auto-merge" not in run.stdout
    assert run.cleaned_up
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_failed_mutation_is_reported(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        round_action="ACT",
        mutation_rc="1",
    )

    assert "Failed to disable auto-merge" in run.stdout
    assert run.cleaned_up
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize(
    "failure", ["CRASH", "MALFORMED", "PREFIX_MALFORMED", "ERROR_OBJECT"]
)
def test_a_producer_that_names_no_tier_disarms_then_skips(
    tmp_path: Path, doc: str, failure: str
) -> None:
    """An unknown tier takes the capability away, then stops. All three shapes.

    This assertion has now been written three ways, and the two rewrites are
    the finding. The first version asserted no round cap and auto-merge
    disarmed, but let the block run on to the tier actions, which is a
    fail-open on the acting path. The repair moved the arm's exit ahead of the
    disarm gate, which stopped the acting and, as Copilot then reported, made a
    producer crash the single path where this loop leaves auto-merge armed on a
    PR it never assessed. Both rewrites came from reading "skip the PR" as one
    decision when it is two: whether to act, and whether to leave a capability
    in place. Disarming is not acting on a PR, it is taking a capability away
    from one, so the answers are independent and here they differ.

    So: `TIER` unknown in all three shapes (a crash or malformed output leaves
    it empty, a JSON error object leaves it `UNKNOWN`), auto-merge armed. The
    block must disarm, must not call the round-cap breaker, and must not reach
    a tier action.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier=failure,
        auto_merge="SQUASH",
        round_action="ACT",
        expected_stderr=(
            "jq: parse error" if failure in {"MALFORMED", "PREFIX_MALFORMED"} else None
        ),
    )

    assert "Cannot determine tier" in run.stdout
    assert run.cleaned_up
    assert run.disarmed, "auto-merge was left armed on a PR whose tier is unknown"
    assert "--disable" in run.disarm_argv, run.disarm_argv
    assert not run.round_cap_called
    assert not run.reached_end, "the loop kept acting without a valid tier"
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_t1_payload_with_nonzero_status_is_not_trusted(tmp_path: Path, doc: str) -> None:
    """A success payload and failure exit cannot jointly authorize merge."""
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T1",
        auto_merge="SQUASH",
        merge_ready_rc="1",
    )

    assert "Cannot determine tier" in run.stdout
    assert run.disarmed
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_an_unknown_tier_with_no_auto_merge_armed_calls_nothing(tmp_path: Path, doc: str) -> None:
    """Falling through to the disarm gate is not the same as always disarming.

    The case above proves the gate is reached on an unknown tier. On its own
    that is compatible with an arm that calls `set_pr_auto_merge.py`
    unconditionally, which would fire the mutation on a PR with nothing armed.
    This pins the other half: same unknown tier, nothing armed, no mutation.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier="CRASH",
        auto_merge="null",
        round_action="ACT",
    )

    assert "Cannot determine tier" in run.stdout
    assert not run.disarmed, "the disarm ran with no auto-merge armed"
    assert not run.round_cap_called
    assert not run.reached_end
    assert run.cleaned_up
    assert run.queue_completed


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("tier", ["T2", "BEHIND", "BLOCKED", "DIRTY"])
def test_a_valid_tier_exiting_nonzero_is_still_dispatched(
    tmp_path: Path, doc: str, tier: str
) -> None:
    """Every dispatched tier is dispatched, and exit status is not the discriminator.

    Two things this pins. `test_pr_merge_ready.py` exits 1 for any PR that is
    not merge-ready, so these tiers legitimately arrive with a non-zero status,
    and a guard rejecting exit 1 would skip every PR the loop exists to fix.

    And the set is the producer's `_TIER_ORDER`, not the T1-T5 ladder the
    command's prose describes. BEHIND, BLOCKED, and DIRTY are declared return
    values; the guard first shipped rejecting them, which turned a healthy
    classification into "producer failed" and stopped the documented BEHIND and
    DIRTY handling.

    Two declared tiers are recognized without being dispatched, and each has its
    own case rather than a row here. SKIP is a draft, merged, or closed PR. T5 is
    a bot-authored PR with a failure or unresolved threads, which the tier table
    hands to a human; it sat in this row while `--is-bot` was never forwarded and
    the tier was therefore unreachable, and it moved out in the same change that
    made it reachable (issue #5208, `test_pr_autofix_bot_tier_forwarding.py`).
    """
    run = run_dispatch(tmp_path, doc, tier=tier, auto_merge="null")

    assert "Cannot determine tier" not in run.stdout
    assert not run.round_cap_called, "the breaker fired outside T3/T4"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_prefix_read_stops_a_t1_pr_from_being_dispatched(tmp_path: Path, doc: str) -> None:
    """Negative control: the defect, restored, on its discriminating input.

    `test_t1_with_auto_merge_armed_keeps_it` above asserts the opposite of this
    against the shipped read. Both run the same block on the same inputs, so
    together they show the fix is what moves the behavior.

    What the pre-fix read does changed once the tier guard landed, and this test
    changed with it rather than being left asserting the old outcome. Before the
    guard, `UNKNOWN` reached the disarm gate and stripped auto-merge from a T1
    PR. Now the guard catches it first and the PR is skipped. Both are wrong for
    a T1 PR, so the control still discriminates; the observable outcome is the
    skip, not the disarm.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T1",
        auto_merge="SQUASH",
        tier_read=PREFIX_TIER_READ,
    )

    assert "Cannot determine tier" in run.stdout, "the pre-fix read no longer reproduces the defect"
    assert not run.reached_end, "a T1 PR was dispatched on a tier the read never resolved"
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"
    assert not run.round_cap_called


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_fake_tier_producer_matches_the_real_output_shape(tmp_path: Path, doc: str) -> None:
    """Guard the fake against drifting from the producer it stands in for.

    A fake that grew a `Data` envelope would make every case above pass under
    the pre-fix read too, and the negative control would stop discriminating.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    write_fake_scripts(scripts_dir)

    env = {k: v for k, v in os.environ.items() if k not in CI_ONLY_ENV}
    # T1 is the one tier the fake exits 0 for, mirroring the real producer,
    # which exits 1 for any PR that is not merge-ready. `check=True` below then
    # fails on a fake that has stopped matching that contract.
    env["FAKE_TIER"] = "T1"
    env["FAKE_PAGES_COMPLETE"] = "true"
    env["MERGE_READY_LOG"] = str(tmp_path / "merge-ready")
    process = subprocess.run(
        ["python3", str(scripts_dir / "test_pr_merge_ready.py")],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=60,
    )
    payload = json.loads(process.stdout)

    assert payload["Tier"] == "T1"
    assert payload["fetched_pages_complete"] is True
    assert "Data" not in payload, "the fake grew an envelope the real producer does not emit"

    real = (REPO_ROOT / ".claude/skills/github/scripts/pr/test_pr_merge_ready.py").read_text(
        encoding="utf-8"
    )
    assert 'result["Tier"]' in real
    # The command reads this field to decide whether a T1 earned its exemption,
    # so its disappearance from the producer must fail here rather than silently
    # turn every T1 into "not provably complete".
    assert '"fetched_pages_complete": fetched_pages_complete,' in real
    assert "print(json.dumps(result, indent=2))" in real
    assert "write_skill_output" not in real, "the real producer started using the Data emitter"
    # The flag the block forwards. If the producer drops it, the block starts
    # passing an argument argparse rejects, and the whole loop breaks on every
    # bot PR. That must fail here rather than in production (issue #5208).
    assert '"--is-bot", action="store_true",' in real, (
        "the real producer no longer declares --is-bot, which the tier-dispatch "
        "block forwards for bot-authored PRs"
    )

    # The other end of the same contract: get_pr_context.py must still emit the
    # field the block reads the author state from. Without this the block's
    # type-checked read would silently fall to its fail-closed branch and every
    # PR, human or not, would classify as a bot.
    context = (REPO_ROOT / ".claude/skills/github/scripts/pr/get_pr_context.py").read_text(
        encoding="utf-8"
    )
    assert '"author_is_bot": author_is_bot(author),' in context


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_skip_terminates_instead_of_reaching_the_disarm_gate(tmp_path: Path, doc: str) -> None:
    """SKIP is recognized and non-actionable, so the loop must stop on it.

    The command's tier table reads `| SKIP | Draft, merged, or closed | No
    action |`. Sending it down the pass-through arm let it reach the auto-merge
    disarm gate, where `SKIP != T1` holds, so a PR that went draft, merged, or
    closed after the live-state gate ran would have had auto-merge stripped by
    a loop that had just classified it as nothing to do. Copilot caught that
    while reviewing the widened whitelist.
    """
    run = run_dispatch(tmp_path, doc, tier="SKIP", auto_merge="SQUASH", round_action="ACT")

    assert "no action" in run.stdout.lower()
    assert "Cannot determine tier" not in run.stdout, "SKIP is declared, not a producer failure"
    assert run.cleaned_up
    assert not run.disarmed, "auto-merge was stripped from a non-actionable PR"
    assert not run.round_cap_called
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_unsupported_disarms_first_then_terminates(tmp_path: Path, doc: str) -> None:
    """UNSUPPORTED terminates, but one gate later than SKIP, and that is the point.

    Both are recognized and non-actionable, and they differ on exactly one
    thing: whether auto-merge survives. SKIP names a state the author chose
    (draft, merged, closed), so stripping it would destroy that choice. This
    one names a `mergeStateStatus` with no verified merge path, so "armed but
    not provably T1" is exactly true of it and the arm must fall through to the
    disarm gate before stopping. Read against
    `test_skip_terminates_instead_of_reaching_the_disarm_gate` above, which
    asserts the opposite `disarmed` value on the same harness.

    `round_cap_called` is the other half. Before this tier existed the same PR
    classified T4, which dispatches into the round-cap thread-fix loop with no
    threads to fix and no CI to repair, so it terminated only by burning the
    cap and posting an escalation comment (issue #4899 reopen).
    """
    run = run_dispatch(
        tmp_path, doc, tier="UNSUPPORTED", auto_merge="SQUASH", round_action="ACT"
    )

    assert "Cannot determine tier" not in run.stdout, (
        "UNSUPPORTED is declared in _TIER_ORDER, not a producer failure"
    )
    assert "no verified merge path" in run.stdout
    assert run.disarmed, "auto-merge survived on a PR with no verified merge path"
    assert not run.round_cap_called, "the round-cap breaker fired on a PR with no work"
    assert not run.reached_end
    assert run.cleaned_up
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_comment_reword_changes_nothing(tmp_path: Path, doc: str) -> None:
    """The inverted control, in the suite rather than in a report.

    A set of same-polarity mutants cannot distinguish "every mutant died" from
    "this fails no matter what". Every other control here asserts a mutation
    breaks something; this one asserts a mutation that should be inert really
    is, so a harness that failed unconditionally would be caught.

    It lived only in the QA report as a manual run until spec validation
    pointed out the obvious: a control nothing re-runs stops being evidence the
    moment the suite changes under it. The same "turn prose into a guard" move
    already applied to the nested-path limit.

    The reason the negative controls cannot live here is that they would have
    to keep the defect present to assert on it. This one has no such problem:
    rewording a comment is inert by construction, so the assertion is that
    behavior is identical, not that a defect survives.

    An inverted control is only evidence if it can also fail, so that was
    demonstrated rather than assumed: retargeting the edit at the disarm
    gate's `[ "$AUTO_MERGE" != "null" ]` and flipping it to `=` fails both
    parameterizations on the first assertion, while the shipped comment edit
    passes. The first attempt at that demonstration proved nothing, because it
    flipped `[ "$TIER" != "T1" ]` to `!= "T9"`, and T3 sits on the same side of
    both, so the edit was behavior-preserving for this case. A control that
    cannot move the thing it probes is not a passing control; it is an
    unfinished one, which is the same narrower-than-the-claim mistake the rest
    of this suite exists to catch.
    """
    block = extract_dispatch((REPO_ROOT / doc).read_text(encoding="utf-8"))
    # Derived, not pinned. An earlier version named a literal comment fragment,
    # which coupled the control to one sentence's line wrapping: rewrapping the
    # paragraph would fail the exactly-one assertion and read as a defect when
    # nothing had changed. The property is that editing a comment is inert, not
    # that editing this comment is.
    target = next(
        line for line in block.splitlines() if line.startswith("#") and block.count(line) == 1
    )

    shipped_dir = tmp_path / "shipped"
    reworded_dir = tmp_path / "reworded"
    shipped_dir.mkdir()
    reworded_dir.mkdir()

    shipped = run_dispatch(shipped_dir, doc, tier="T3", auto_merge="SQUASH")
    reworded = run_dispatch(
        reworded_dir,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        block_edit=(target, target + " Reworded by the inverted control."),
    )

    assert reworded.disarmed == shipped.disarmed
    assert reworded.round_cap_called == shipped.round_cap_called
    assert reworded.cleaned_up == shipped.cleaned_up
    assert reworded.reached_end == shipped.reached_end
    assert reworded.queue_completed == shipped.queue_completed
    assert reworded.stdout == shipped.stdout, (
        "rewording a comment changed the block's behavior, so either the "
        "extraction is including something it should not, or the suite is "
        "sensitive to text it has no business reading"
    )
