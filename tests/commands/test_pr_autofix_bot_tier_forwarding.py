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
def test_an_unreadable_context_still_skips_before_classifying(tmp_path: Path, doc: str) -> None:
    """A context fetch that fails outright is a skip, not a bot guess.

    `UNREADABLE` makes the fake `get_pr_context.py` exit 1 with no stdout, so
    both reads off `$CTX` come back empty. The author read falls to its closed
    branch and the PR is classified as a bot, but the auto-merge guard below it
    still terminates the PR on the same missing evidence, so nothing acts on a
    tier computed from a fetch that never returned.
    """
    run = run_dispatch(
        tmp_path, doc, tier="T3", auto_merge="UNREADABLE", author_is_bot="true"
    )

    assert "Cannot read auto-merge state" in run.stdout
    assert not run.reached_end, "the loop acted on a PR whose context fetch failed"
    assert run.cleaned_up
    assert run.queue_completed, "the gate aborted the queue instead of skipping one PR"
