"""The workflow half of the shallow-graft guard (issue #4572).

A `git fetch --depth=1` writes `.git/shallow`, which git shares across the
whole repository and every worktree, and severs ancestry traversal for every
later step in the same job. A plain `git fetch` afterwards does not repair it.

That makes the trap invisible at the step that pays for it: the step writing
the graft succeeds, and a different step further down measures the wrong
thing. This module is the prevention half, so no workflow writes the graft.

The runtime half, proving the graft's effect against real git and pinning the
CI entrypoints that must refuse to answer under it, is in
test_shallow_fetch_graft_guards.py. The parsing lives in
shallow_fetch_workflow_parsing.py, exercised by test_shallow_fetch_parser.py.
"""

from __future__ import annotations

from tests.ci.shallow_fetch_workflow_parsing import (
    _jobs,
    _root_checkout_depths,
    _shallowing_fetches,
    _workflow_documents,
)


def test_workflow_directory_is_not_empty() -> None:
    """Scope control for the invariant below (testing rule 10).

    A zero-finding sweep proves nothing when the examined count is unknown, and
    a glob that stops matching would make the next test vacuous while still
    reporting green.
    """
    documents = _workflow_documents()
    assert len(documents) >= 10, (
        f"expected the workflow sweep to examine files, saw {len(documents)}"
    )
    assert sum(len(_jobs(doc)) for _, doc in documents) >= 10


def test_no_job_mixes_a_full_checkout_with_a_depth_limited_fetch() -> None:
    """Issue #4572: the graft is written by a step that does not pay for it.

    Scoped to jobs whose ROOT checkout is already `fetch-depth: 0`, because
    there a shallowing fetch is pure downside: the history is present already,
    so the flag saves no bandwidth and its only observable effect is the graft.
    A job that deliberately checks out shallow is left alone; it has made a
    different trade knowingly.

    Known limit of a static scan, deliberately not papered over: a shallowing
    fetch reached through a composite action, a reusable workflow, or a script
    the step invokes is not resolved here. A sweep for the script case was
    written and then removed, because every candidate it found was prose in a
    docstring or an unrelated argparse `--depth` for graph traversal, and a
    guard that cannot tell those from a real fetch would fail the next
    contributor who adds a depth option to a CLI. The expression case, which
    IS decidable, is pinned by the sibling test below.
    """
    offenders: list[str] = []
    examined = 0
    for path, document in _workflow_documents():
        for job_name, job in _jobs(document).items():
            examined += 1
            if 0 not in _root_checkout_depths(job):
                continue
            for step_name, line in _shallowing_fetches(job):
                offenders.append(f"{path.name}::{job_name} step {step_name!r}: {line}")

    assert examined >= 10, f"sweep examined only {examined} jobs"
    assert not offenders, (
        "a job checks out at fetch-depth 0 and then fetches shallowly, which "
        "writes .git/shallow for the rest of the job and severs ancestry for "
        "every later step (issue #4572). Drop the depth flag:\n  "
        + "\n  ".join(offenders)
    )


def test_no_workflow_computes_its_checkout_depth_from_an_expression() -> None:
    """Pins the one blind spot the depth parser cannot resolve.

    `_normalized_depth` turns `0` and `"0"` into the same integer, but a
    `${{ }}` expression is decided at run time and cannot be classified here.
    Rather than guess, this asserts none exists, so the day one appears this
    fails and names it instead of the invariant above going quietly blind.
    """
    computed: list[str] = []
    for path, document in _workflow_documents():
        for job_name, job in _jobs(document).items():
            for depth in _root_checkout_depths(job):
                if isinstance(depth, str) and "${{" in depth:
                    computed.append(f"{path.name}::{job_name} fetch-depth: {depth}")

    assert not computed, (
        "a root checkout computes fetch-depth from an expression, which the "
        "shallow-graft invariant cannot classify statically. Either pin the "
        "depth to a literal or teach the invariant this case:\n  "
        + "\n  ".join(computed)
    )



