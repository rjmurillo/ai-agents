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
def test_round_cap_escalation_stops_before_the_disarm_gate(tmp_path: Path, doc: str) -> None:
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
    assert not run.disarmed, "the loop kept acting after the round cap escalated"
    assert not run.reached_end
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_non_t1_with_auto_merge_armed_is_disarmed(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", round_action="ACT")

    assert run.disarmed
    assert "Auto-merge armed on non-T1 PR" in run.stdout
    assert run.reached_end
    # The flags, not just the fact of a call. The fake used to ignore argv, so
    # `--disable` could be mutated to `--enable` with all 429 tests green: the
    # gate that strips auto-merge before an unguarded push would instead arm it.
    # Verified surviving before this assertion existed.
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
@pytest.mark.parametrize("failure", ["CRASH", "MALFORMED", "ERROR_OBJECT"])
def test_a_producer_that_names_no_tier_skips_the_pr(tmp_path: Path, doc: str, failure: str) -> None:
    """Fail closed when the tier is unknown, in all three failure shapes.

    An earlier version of this test asserted the opposite and called it the
    sentinel asymmetry: no round cap, auto-merge disarmed. That codified a
    fail-open as correct. Copilot caught it. Without `pipefail` `jq` masks the
    producer's failure, and the shapes do not even agree: a crash or malformed
    output leaves `TIER` empty, a JSON error object leaves it `UNKNOWN`. Both
    skip the T3/T4 breaker *and* satisfy `TIER != T1`, so the loop would strip
    auto-merge from a PR whose tier it never learned and then keep acting on it.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier=failure,
        auto_merge="SQUASH",
        round_action="ACT",
        expected_stderr="jq: parse error" if failure == "MALFORMED" else None,
    )

    assert "Cannot determine tier" in run.stdout
    assert run.cleaned_up
    assert not run.disarmed, "auto-merge was stripped on an unknown tier"
    assert not run.round_cap_called
    assert not run.reached_end, "the loop kept acting without a valid tier"
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("tier", ["T2", "T5", "BEHIND", "BLOCKED", "DIRTY"])
def test_a_valid_tier_exiting_nonzero_is_still_dispatched(
    tmp_path: Path, doc: str, tier: str
) -> None:
    """Every declared tier is dispatched, and exit status is not the discriminator.

    Two things this pins. `test_pr_merge_ready.py` exits 1 for any PR that is
    not merge-ready, so these tiers legitimately arrive with a non-zero status,
    and a guard rejecting exit 1 would skip every PR the loop exists to fix.

    And the set is the producer's `_TIER_ORDER`, not the T1-T5 ladder the
    command's prose describes. BEHIND, BLOCKED, and DIRTY are declared return
    values; the guard first shipped rejecting them, which turned a healthy
    classification into "producer failed" and stopped the documented BEHIND and
    DIRTY handling. SKIP is declared too but is not dispatched, so it has its
    own test below rather than a row here.
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
    env["FAKE_TIER"] = "T1"  # exits 0; the fake mirrors the real not-ready status
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
    assert "Data" not in payload, "the fake grew an envelope the real producer does not emit"

    real = (REPO_ROOT / ".claude/skills/github/scripts/pr/test_pr_merge_ready.py").read_text(
        encoding="utf-8"
    )
    assert 'result["Tier"]' in real
    assert "print(json.dumps(result, indent=2))" in real
    assert "write_skill_output" not in real, "the real producer started using the Data emitter"


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
    demonstrated rather than assumed: retargeting `block_edit` at the disarm
    gate's `[ "$AUTO_MERGE" != "null" ]` and flipping it to `=` fails both
    parameterizations on the first assertion, while the shipped comment edit
    passes. The first attempt at that demonstration proved nothing, because it
    flipped `[ "$TIER" != "T1" ]` to `!= "T9"`, and T3 sits on the same side of
    both, so the edit was behavior-preserving for this case. A control that
    cannot move the thing it probes is not a passing control; it is an
    unfinished one, which is the same narrower-than-the-claim mistake the rest
    of this suite exists to catch.
    """
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
        block_edit=("# gate ran.", "# gate ran (reworded by the inverted control)."),
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
