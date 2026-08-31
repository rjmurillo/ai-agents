"""Bot-author forwarding in `/pr-autofix`'s tier-dispatch block.

Refs #5208. `classify_tier` in `test_pr_merge_ready.py` returns T5 only through
`is_bot and (has_ci_failures or has_threads)`, and its `is_bot` parameter
defaults to `False`. The command performed no author lookup and never passed
`--is-bot`, so T5 was unreachable: every bot PR with a failing check or an
unresolved thread classified T2-T4 and entered the unattended
thread-fix/round-cap loop the tier table reserves for human handling.

Split from `test_pr_autofix_tier_dispatch_runtime.py` rather than appended to
it, following the precedent that file records for its own split from the
harness: adding these cases there took it from 415 lines to 576 and tripped the
500-line taste rule. Same harness, same docs, one concern per module.

The harness lives in `pr_autofix_dispatch_harness.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands.pr_autofix_dispatch_harness import DISPATCH_DOCS, run_dispatch


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_bot_authored_pr_forwards_is_bot_to_the_tier_producer(
    tmp_path: Path, doc: str
) -> None:
    """The producer cannot return T5 unless the command asks for it.

    `classify_tier` reaches T5 only through `is_bot and (has_ci_failures or
    has_threads)`, and its `is_bot` parameter defaults to `False`. The command
    performed no author lookup at all and never passed the flag, so T5 was
    unreachable and every bot PR with a failing check or an unresolved thread
    was classified T2-T4 and swept into the unattended thread-fix/round-cap
    loop the tier table reserves for human handling.

    T3 here rather than T5 on purpose: the fake producer echoes whatever tier
    the case names, so asserting on the returned tier would assert on the fake.
    What the block actually controls is the argument vector, so that is what
    this reads.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot="true")

    assert run.forwarded_is_bot, (
        "the tier producer was called without --is-bot on a bot-authored PR, so "
        f"T5 was unreachable; argv was {run.merge_ready_argv.strip()!r}"
    )
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_human_authored_pr_does_not_forward_is_bot(tmp_path: Path, doc: str) -> None:
    """The other half: forwarding unconditionally would be its own defect.

    Without this, a block that hardcoded `--is-bot` would pass the case above
    while pushing every human PR with a failing check into T5, which stops the
    loop from fixing the PRs it exists to fix.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot="false")

    assert not run.forwarded_is_bot, (
        "--is-bot was forwarded for a human-authored PR, so every human PR with "
        f"a failure would classify T5; argv was {run.merge_ready_argv.strip()!r}"
    )
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_t5_pr_is_handed_to_a_human_before_the_round_cap_breaker(
    tmp_path: Path, doc: str
) -> None:
    """Making T5 reachable must not switch the circuit breaker off.

    The breaker fires on `TIER = T3 or T4`. That was complete while `--is-bot`
    was never forwarded: a bot PR with threads or CI failures classified T3 or
    T4 and hit `check_pr_round_cap.py`, the cap added for issue #5056 after PR
    #1887 ran 11+ rounds over 46 hours. Once the same PR classifies T5 the
    condition no longer matches it, so an unterminated T5 would fall into the
    tier actions with no cap and no human handoff, which is worse than the
    defect issue #5208 reports.

    The tier table reads "| T5 | Bot PR with any failure or threads | Handle
    individually |", so the arm is a handoff. `round_cap_called` is the
    discriminating read: a fall-through reaches the end of the block, and a T5
    arm that terminated by falling into the breaker instead would call it.
    """
    run = run_dispatch(tmp_path, doc, tier="T5", author_is_bot="true")

    assert "Tier T5" in run.stdout
    assert not run.round_cap_called, "the breaker fired on a tier its condition excludes"
    assert not run.reached_end, "a T5 PR fell through into the tier actions uncapped"
    assert run.cleaned_up
    assert run.queue_completed, "the T5 arm aborted the queue instead of skipping one PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_t5_pr_is_disarmed_before_it_is_handed_over(tmp_path: Path, doc: str) -> None:
    """T5 exits one gate later than SKIP, and the difference is load bearing.

    SKIP names a state where disarming is meaningless or destroys a choice the
    author made deliberately. A T5 PR is "armed but not provably T1", which is
    the disarm gate's own trigger condition, so it has to pass through that gate
    before it stops. Handing a human a PR that GitHub can still land on its own
    is the CWE-284 shape the disarm ordering exists to prevent.
    """
    run = run_dispatch(tmp_path, doc, tier="T5", auto_merge="SQUASH", author_is_bot="true")

    assert run.disarmed, "a T5 PR was handed over with auto-merge still armed"
    assert "--disable" in run.disarm_argv, run.disarm_argv
    assert "Tier T5" in run.stdout
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_stale_context_helper_is_named_rather_than_silently_reclassifying(
    tmp_path: Path, doc: str
) -> None:
    """The version-skew case has its own cause and its own remedy.

    `resolve_pr_scripts_dir` tries `$COPILOT_PLUGIN_ROOT`, then
    `$CLAUDE_PLUGIN_ROOT`, then `$repo_root/.claude`, and only then its three
    installed-plugin caches, so a cache never outranks the checkout. Two paths
    still reach a stale helper: an explicit plugin root pointing at an install
    that predates the fix, or a session outside a checkout carrying
    `skills/github/scripts/pr`, which falls through to a cache. Either way
    `$SCRIPTS_DIR/get_pr_context.py` can be a copy predating issue #5208 that
    emits no `author_is_bot` key at all.
    That fails closed like any other unreadable author, which combined with the
    T5 arm above reclassifies every PR with a failure or a thread as T5 across
    the whole repository. One indistinguishable notice makes that invisible;
    naming the helper makes it fixable.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot="OMIT")

    assert "emits no author_is_bot field" in run.stdout, (
        "an absent field was reported the same way as an unreadable value, so "
        "an operator cannot tell a stale helper from a malformed author"
    )
    assert run.forwarded_is_bot
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize(
    "author_is_bot",
    [
        pytest.param("RAW:null", id="explicit-null"),
        pytest.param('RAW:"false"', id="string-spelling-of-false"),
    ],
)
def test_a_present_but_unreadable_field_is_not_blamed_on_a_stale_helper(
    tmp_path: Path, doc: str, author_is_bot: str
) -> None:
    """The other half: a current helper must not be reported as stale.

    Paired with the case above. A block that printed the stale-helper line for
    every closed-branch verdict would satisfy that one alone and send every
    operator to reinstall a plugin that is already current. `RAW:null` and the
    string spelling both carry the key, so the helper is emitting the field and
    the value is what cannot be read.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot=author_is_bot)

    assert "emits no author_is_bot field" not in run.stdout
    assert "Cannot read author bot state" in run.stdout
    assert run.forwarded_is_bot


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize(
    "author_is_bot",
    [
        pytest.param("OMIT", id="field-absent"),
        pytest.param("RAW:null", id="explicit-null"),
        pytest.param('RAW:"true"', id="string-spelling-of-true"),
        pytest.param('RAW:"false"', id="string-spelling-of-false"),
        pytest.param("RAW:1", id="number"),
    ],
)
def test_an_unreadable_author_fails_closed_to_bot(
    tmp_path: Path, doc: str, author_is_bot: str
) -> None:
    """An author nobody could classify must not enter the unattended loop.

    Same direction as the lease store's `lease-store-unavailable` verdict: the
    two errors are not symmetric. Guessing "human" hands a PR this session
    never classified to the automated thread-fix loop; guessing "bot" costs a
    human one look at a PR that may not have needed one.

    `RAW:"true"` and `RAW:"false"` are here because a bare `tostring` on this
    field would launder both string spellings into real booleans, which is the
    defect PR #5176 shipped on the sibling `fetched_pages_complete` read. Both
    must land on the closed branch, and `RAW:"false"` is the one that
    discriminates: a type-blind read would take it to the open branch, which is
    the fail-open direction this guard exists to refuse.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot=author_is_bot)

    assert run.forwarded_is_bot, (
        "an author this session could not classify was sent to the tier producer "
        f"as a human; argv was {run.merge_ready_argv.strip()!r}"
    )
    assert "Cannot read author bot state" in run.stdout, (
        "the fail-closed branch was taken silently, so an operator reading the "
        "log cannot tell a real human author from an unreadable one"
    )
    assert run.reached_end, "failing closed on the author must not skip the PR"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_malformed_suffix_forces_unknown_author(tmp_path: Path, doc: str) -> None:
    """jq can emit a valid first value then exit nonzero on a malformed suffix.

    The assignment captures jq output but must also check that jq succeeded.
    A valid JSON prefix with trailing garbage (MALFORMED_SUFFIX) produces a
    parseable author_is_bot=false from jq, but the jq exit status and the
    validation check should force IS_BOT to unknown, which the closed branch
    then treats as a bot (fail-closed).
    """
    run = run_dispatch(
        tmp_path, doc, tier="T3", author_is_bot="MALFORMED_SUFFIX"
    )

    assert run.forwarded_is_bot, (
        "a malformed jq response should fail closed to bot, not pass as human"
    )


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_real_human_author_is_not_reported_as_unreadable(tmp_path: Path, doc: str) -> None:
    """The diagnostic must discriminate, or it is noise on every PR.

    Paired with the case above: that one asserts the message appears when the
    field cannot be read, this one asserts it stays absent when it can. A block
    that printed the notice unconditionally would satisfy the first alone.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot="false")

    assert "Cannot read author bot state" not in run.stdout


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_author_lookup_runs_before_the_tier_producer(tmp_path: Path, doc: str) -> None:
    """Ordering, asserted rather than assumed.

    The context fetch used to sit after the tier read, at the auto-merge disarm
    gate. Reading `author_is_bot` from it is only useful if the fetch happens
    first, and nothing else in this suite would notice the two swapping back:
    under the harness `$CTX` would be unset, `set -u` would abort, and the
    generic non-zero-exit assertion in `run_dispatch` would report a shell
    error rather than the ordering defect. This names it.

    The disarm gate still reads `$AUTO_MERGE` from the same single fetch, which
    the surviving disarm cases in this file cover, so the move did not cost the
    PR a second API call.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", author_is_bot="true")

    assert run.forwarded_is_bot, "the tier call did not see an author state fetched before it"
    assert run.disarmed, "the disarm gate lost the context fetch when it moved"
    assert "--disable" in run.disarm_argv


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_context_is_fetched_exactly_once_per_pr(tmp_path: Path, doc: str) -> None:
    """One fetch per PR, counted rather than claimed.

    The case above proves the fetch moved ahead of the tier producer and that
    the disarm gate still reads `$AUTO_MERGE`. Neither assertion can count: a
    block that fetched once for the author read and a second time at the disarm
    gate satisfies both, and its docstring's closing claim, "the move did not
    cost the PR a second API call", would be the only thing saying otherwise.
    The block itself claims it twice, at the fetch ("the PR still costs one
    context fetch") and at the disarm gate ("One fetch still serves both
    reads"), so it is a stated contract with no test behind it.

    Cost is the whole point of the contract. `get_pr_context.py` runs `gh pr
    view` plus a paginated `reviewThreads` GraphQL walk, so a duplicate is a
    second round trip against the same rate limit for every PR in the queue,
    every pass through the loop.

    Exactly one, not at most one: a block that dropped the fetch entirely would
    leave `$CTX` unset, and while `set -u` catches that today, an edit that
    also gave `$CTX` a default would not be caught by an upper bound alone.

    The harness walks two PRs, so the assertion is on the per-PR count. A
    single-PR check could not tell one-per-PR from one-per-queue, and
    one-per-queue is the shape a fetch hoisted above the loop produces: PR
    5177 would then be classified off PR 5176's author and auto-merge state.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", author_is_bot="true")

    fetches = run.context_fetches
    assert len(fetches) == 2, (
        "the two-PR queue did not cost exactly one context fetch per PR; calls "
        f"were {fetches!r}"
    )
    for pr in ("5176", "5177"):
        matching = [line for line in fetches if f"--pull-request {pr}" in line]
        assert len(matching) == 1, (
            f"PR #{pr} was fetched {len(matching)} times, not once; calls were {fetches!r}"
        )


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_an_unreadable_context_terminates_on_auto_merge_guard(
    tmp_path: Path, doc: str
) -> None:
    """A context fetch that fails outright classifies the bot but terminates at the guard.

    `UNREADABLE` makes the fake `get_pr_context.py` exit 1 with no stdout, so
    both reads off `$CTX` come back empty. The author read falls to its closed
    branch and the PR is classified as a bot, but the auto-merge guard below it
    still terminates the PR on the same missing evidence, so nothing acts on a
    tier computed from a fetch that never returned.

    The author notice is asserted here rather than in the parametrized
    unreadable-author case above because this is the one shape that produces it
    without any `author_is_bot` value: empty stdin leaves `jq` printing nothing,
    so the variable holds the empty string, which is neither `false` nor any
    verdict the branch can name. The closed branch was taken silently, which is
    exactly what `test_a_real_human_author_is_not_reported_as_unreadable` calls
    load bearing, and the sibling `AUTO_MERGE` read six lines below already
    documented the same trap.
    """
    run = run_dispatch(
        tmp_path, doc, tier="T3", auto_merge="UNREADABLE", author_is_bot="true"
    )

    assert "Cannot read author bot state" in run.stdout, (
        "an empty context fetch failed closed on the author with no message, so "
        "an operator reading the log sees only the auto-merge skip"
    )
    assert "emits no author_is_bot field" not in run.stdout, (
        "an empty fetch was blamed on a stale helper; nothing was read at all"
    )
    assert "Cannot read auto-merge state" in run.stdout
    assert not run.reached_end, "the loop acted on a PR whose context fetch failed"
    assert run.cleaned_up
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"
