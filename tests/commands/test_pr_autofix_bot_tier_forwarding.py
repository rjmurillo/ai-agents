"""Bot-author forwarding in `/pr-autofix`'s tier-dispatch block.

Refs #5208. `classify_tier` in `test_pr_merge_ready.py` returns T5 only through
`is_bot and (has_ci_failures or has_threads)`, and its `is_bot` parameter
defaults to `False`. The command performed no author lookup and never passed
`--is-bot`, so T5 was unreachable: every affected bot PR that reached
work-tier classification entered the T2-T4 unattended thread-fix/round-cap
loop the tier table reserves for human handling.

Split from `test_pr_autofix_tier_dispatch_runtime.py` rather than appended to
it, following the precedent that file records for its own split from the
harness: adding these cases there took it from 415 lines to 576 and tripped the
500-line taste rule. Same harness, same docs, one concern per module.

The harness lives in `pr_autofix_dispatch_harness.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands.pr_autofix_dispatch_harness import (
    DISPATCH_DOCS,
    run_dispatch,
    run_scripts_readiness,
)


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_bot_authored_pr_forwards_is_bot_to_the_tier_producer(
    tmp_path: Path, doc: str
) -> None:
    """The producer cannot return T5 unless the command asks for it.

    `classify_tier` reaches T5 only through `is_bot and (has_ci_failures or
    has_threads)`, and its `is_bot` parameter defaults to `False`. The command
    performed no author lookup at all and never passed the flag, so T5 was
    unreachable and every affected bot PR that reached work-tier classification
    was swept into the T2-T4 unattended thread-fix/round-cap loop the tier table
    reserves for human handling.

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

    assert run.did_not_forward_is_bot, (
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
    was never forwarded: an affected bot PR that reached work-tier
    classification became T3 or T4 and hit `check_pr_round_cap.py`, the cap
    added for issue #5056 after PR #1887 ran 11+ rounds over 46 hours. Once the
    same PR classifies T5 the condition no longer matches it, so an unterminated
    T5 would fall into the tier actions with no cap and no human handoff, which
    is worse than the defect issue #5208 reports.

    The tier table assigns individual handling to bot PRs that pass merge-state
    gates but still have failures or threads, so the arm is a handoff.
    `round_cap_called` is the discriminating read: a fall-through reaches the
    end of the block, and a T5 arm that terminated by falling into the breaker
    instead would call it.
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
def test_a_failed_context_producer_discards_its_human_output(
    tmp_path: Path, doc: str
) -> None:
    """A producer failure cannot buy either the human or auto-merge path."""
    run = run_dispatch(
        tmp_path, doc, tier="T3", author_is_bot="FAILED_WITH_HUMAN"
    )

    assert run.forwarded_is_bot
    assert "Cannot read auto-merge state" in run.stdout
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize(
    "author_is_bot",
    [
        pytest.param("MALFORMED_SUFFIX", id="malformed-json"),
        pytest.param("SECOND_DATA_ARRAY", id="later-value-breaks-filter"),
    ],
)
def test_a_failed_jq_filter_forces_unknown_author(
    tmp_path: Path, doc: str, author_is_bot: str
) -> None:
    """jq can emit a valid first value then exit nonzero on a malformed suffix.

    The assignment captures jq output but must also check that jq succeeded.
    Both inputs first emit a parseable author_is_bot=false. One then emits
    malformed JSON; the other emits a valid value that breaks this jq filter.
    Either nonzero exit must force unknown, which fails closed to bot.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", author_is_bot=author_is_bot)

    assert run.forwarded_is_bot, (
        "a malformed jq response should fail closed to bot, not pass as human"
    )


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_flag_lookalike_is_not_the_is_bot_token(tmp_path: Path, doc: str) -> None:
    """The argv check must reject strings argparse rejects."""
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        author_is_bot="true",
        block_edit=('IS_BOT_FLAG="--is-bot"', 'IS_BOT_FLAG="--is-bot=false"'),
    )

    assert not run.forwarded_is_bot


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_every_dispatch_call_targets_its_current_pr(tmp_path: Path, doc: str) -> None:
    """The two-PR queue must not reuse one PR number."""
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        author_is_bot="true",
    )

    assert run.merge_ready_calls == [
        ["--pull-request", "5176", "--is-bot"],
        ["--pull-request", "5177", "--is-bot"],
    ]
    assert run.context_calls == [
        ["--pull-request", "5176", "--output-format", "json"],
        ["--pull-request", "5176", "--output-format", "json"],
        ["--pull-request", "5177", "--output-format", "json"],
        ["--pull-request", "5177", "--output-format", "json"],
    ]
    assert run.disarm_calls == [
        ["--pull-request", "5176", "--disable", "--output-format", "json"],
        ["--pull-request", "5177", "--disable", "--output-format", "json"],
    ]


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

    The disarm gate performs a fresh context read after tier production. The
    surviving disarm cases cover that second consumer.
    """
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", author_is_bot="true")

    assert run.forwarded_is_bot, "the tier call did not see an author state fetched before it"
    assert run.disarmed, "the disarm gate lost the context fetch when it moved"
    assert "--disable" in run.disarm_argv


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_auto_merge_is_refetched_after_tier_production(tmp_path: Path, doc: str) -> None:
    """A stale author lookup must not decide whether auto-merge is armed."""
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="ARMED_AFTER_AUTHOR",
        author_is_bot="true",
    )

    fetches = run.context_fetches
    assert len(fetches) == 4, (
        "the two-PR queue did not fetch author state and fresh auto-merge state; calls "
        f"were {fetches!r}"
    )
    for pr in ("5176", "5177"):
        matching = [line for line in fetches if f"--pull-request {pr}" in line]
        assert len(matching) == 2, (
            f"PR #{pr} was fetched {len(matching)} times, not twice; calls were {fetches!r}"
        )
    assert run.disarmed, "auto-merge armed after author lookup bypassed the disarm gate"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize(
    ("author_is_bot", "expected_flag"),
    [
        pytest.param("true", True, id="bot"),
        pytest.param("false", False, id="human"),
        pytest.param("OMIT", True, id="field-absent"),
        pytest.param("RAW:null", True, id="unreadable"),
        pytest.param("MALFORMED_SUFFIX", True, id="malformed-json"),
        pytest.param("SECOND_DATA_ARRAY", True, id="later-value-breaks-filter"),
        pytest.param("FAILED_WITH_HUMAN", True, id="failed-producer"),
    ],
)
def test_the_scripts_readiness_recipe_fails_closed(
    tmp_path: Path, doc: str, author_is_bot: str, expected_flag: bool
) -> None:
    """The runnable reference must enforce the same author boundary."""
    argv = run_scripts_readiness(tmp_path, doc, author_is_bot=author_is_bot)

    assert ("--is-bot" in argv) is expected_flag


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
