"""Each ratchet must reach the deduplicating enumeration, and announce once.

Companion to ``test_count_ratchet_unmerged_index.py``, which pins the
deduplication itself against real git. This module pins the two claims that
depend on the CONSUMERS rather than on git: that all six ratchets still count
through ``count_ratchet.tracked_files``, and that one run prints the mid-merge
note once rather than once per index read (issue #4746).

Split from that module at this seam because the two halves need opposite
fixtures. Those cases build real repositories and run the real linter; these
replace the enumeration with a spy and never touch git at all, which is what
lets them drive all six consumers in under a second.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.ci import (
    cli_exit_contract_ratchet,
    memory_index_count_ratchet,
    ruff_count_ratchet,
    subprocess_encoding_count_ratchet,
    taste_count_ratchet,
    type_ignore_count_ratchet,
)


class _EnumerationSpy:
    """Stands in for ``tracked_files`` and records that it was reached.

    Asserting that a module still holds the imported name proves only that the
    import survived: a consumer can stop calling it, keep the unused import,
    and pass. Driving the real counting entry point with this in place is what
    the repository's consumer-wiring rule asks for.
    """

    def __init__(self, result: list[str] | None) -> None:
        self.result = result
        self.calls = 0
        self.announced: list[bool] = []

    def __call__(
        self, repo_root: Path, globs: Sequence[str], *, announce_unmerged: bool = True
    ) -> list[str] | None:
        """Mirrors ``tracked_files``, keyword included, so a caller that passes
        ``announce_unmerged`` is exercised rather than rejected by the spy."""
        self.calls += 1
        self.announced.append(announce_unmerged)
        return self.result


def _stub_memory_tier_validator(monkeypatch) -> None:
    """Stub the external validator ``memory_index_count_ratchet`` shells out to.

    That module runs the memory-tier validator before it enumerates, and the
    validator is absent from a scratch root, so the module would bail before
    reaching the enumeration and the spy would prove nothing. This mocks at the
    process boundary only, leaving the enumeration on the path under test. The
    stub warning names a file that the empty enumeration will report untracked,
    which is what makes the control below land on zero.
    """
    monkeypatch.setattr(
        memory_index_count_ratchet,
        "_warning_lines",
        lambda _root: ["a.md: no index references this file"],
    )


_RATCHET_CONSUMERS = [
    (cli_exit_contract_ratchet, None),
    (memory_index_count_ratchet, _stub_memory_tier_validator),
    (ruff_count_ratchet, None),
    (subprocess_encoding_count_ratchet, None),
    (taste_count_ratchet, None),
    (type_ignore_count_ratchet, None),
]

_CONSUMER_IDS = [module.__name__.rsplit(".", 1)[-1] for module, _ in _RATCHET_CONSUMERS]


@pytest.mark.parametrize(("module", "prepare"), _RATCHET_CONSUMERS, ids=_CONSUMER_IDS)
def test_every_ratchet_counts_through_the_shared_enumeration(
    module, prepare, monkeypatch, tmp_path
):
    """A ratchet that rolls its own ``ls-files`` reopens #4746 for itself.

    The issue asked whether the siblings share the enumeration. They do, which
    is why one fix covers all six. This drives each consumer's real
    ``current_count`` and fails the moment one stops routing through the
    deduplicating helper.

    The unreadable-enumeration verdict is asserted alongside the call, because
    a consumer that reached the helper and then ignored its ``None`` would be
    wired and still wrong: each of these modules documents returning None
    rather than 0 as load-bearing, since a zero from a broken scan reads as a
    clean tree and ``--update`` would write it into the baseline.
    """
    if prepare is not None:
        prepare(monkeypatch)
    spy = _EnumerationSpy(None)
    monkeypatch.setattr(module, "tracked_files", spy)

    result = module.current_count(tmp_path)

    assert spy.calls >= 1, f"{module.__name__} did not reach the shared enumeration"
    assert result is None, f"{module.__name__} reported a count from an unreadable scan"


@pytest.mark.parametrize(("module", "prepare"), _RATCHET_CONSUMERS, ids=_CONSUMER_IDS)
def test_a_readable_enumeration_is_not_reported_as_a_failed_scan(
    module, prepare, monkeypatch, tmp_path
):
    """Control for the case above: the None must come from the enumeration.

    Same consumer, same input, differing only in the condition under test. A
    module that returned None for an unrelated reason fails here too, so the
    case above cannot pass for the wrong reason.
    """
    if prepare is not None:
        prepare(monkeypatch)
    spy = _EnumerationSpy([])
    monkeypatch.setattr(module, "tracked_files", spy)

    result = module.current_count(tmp_path)

    assert spy.calls >= 1, f"{module.__name__} did not reach the shared enumeration"
    assert result == 0, f"{module.__name__} did not count an empty tree as zero"


# ---------------------------------------------------------------------------
# The note belongs to the counting read, not to the diagnostic re-read (#4746)
# ---------------------------------------------------------------------------

_LISTER_CONSUMERS = [
    (memory_index_count_ratchet, _stub_memory_tier_validator),
    (taste_count_ratchet, None),
]

_LISTER_IDS = [module.__name__.rsplit(".", 1)[-1] for module, _ in _LISTER_CONSUMERS]


@pytest.mark.parametrize(("module", "prepare"), _LISTER_CONSUMERS, ids=_LISTER_IDS)
def test_the_diagnostic_re_read_does_not_repeat_the_note(
    module, prepare, monkeypatch, tmp_path
):
    """Both listers must enumerate silently, whatever their path to the helper.

    ``taste_count_ratchet`` calls the enumeration straight from its lister;
    ``memory_index_count_ratchet`` reaches it two frames down, through
    ``_collect`` and ``_tracked_relative_paths``. The end-to-end case covers
    the first shape only, because the second needs the external memory-tier
    validator. This pins both, so a future edit that drops the keyword
    somewhere along the second path is caught here.
    """
    if prepare is not None:
        prepare(monkeypatch)
    spy = _EnumerationSpy([])
    monkeypatch.setattr(module, "tracked_files", spy)

    module.list_violations(tmp_path)

    assert spy.calls >= 1, f"{module.__name__} lister did not reach the enumeration"
    assert not any(spy.announced), (
        f"{module.__name__} lister re-announced the mid-merge note on the "
        f"run's second index read"
    )


@pytest.mark.parametrize(("module", "prepare"), _LISTER_CONSUMERS, ids=_LISTER_IDS)
def test_the_counting_read_still_announces(module, prepare, monkeypatch, tmp_path):
    """Control for the case above: suppression must not have reached the count.

    Same consumer, same input, differing only in which entry point is driven.
    Silencing both reads would leave a contributor mid-merge with no caveat at
    all, which is the defect the note exists to prevent, one step further on.
    """
    if prepare is not None:
        prepare(monkeypatch)
    spy = _EnumerationSpy([])
    monkeypatch.setattr(module, "tracked_files", spy)

    module.current_count(tmp_path)

    assert spy.calls >= 1, f"{module.__name__} counter did not reach the enumeration"
    assert all(spy.announced), (
        f"{module.__name__} counting read went silent, so a mid-merge run "
        f"would print no caveat at all"
    )
