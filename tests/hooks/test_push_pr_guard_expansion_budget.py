"""Expansion-budget tests for the push-pr identity guard (issue #4764).

The guard enumerates brace expansions to decide whether a command can name
new_pr.py. Enumeration is attacker-reachable: the command text comes from the
model, and the hook accepts up to 128 KiB of it.

Measured on the merged tree at ``5cd72a7dad`` with ``tracemalloc``:

    input bytes: 10921   -> expansions: 256,  total expanded bytes: 2,562,194
    input bytes: 100060  -> expansions: 2048, total expanded bytes: 204,832,768
                            peak traced allocation: 195.6 MiB

The 10,920-byte figure in the report is the amplification this module pins:
roughly 235x on a single brace group, because ``_brace_expanded`` materialized
every expansion into a list and each expansion carried a full copy of the
surrounding literal text. The expansion COUNT budget (4096) did not bound it,
because count says nothing about the size of each element.

These tests assert on allocation counters, not on wall-clock time. A timing
assertion on a shared runner is flaky by construction and tells you nothing
about which machine it will fail on.
"""

from __future__ import annotations

import importlib.util
import sys
import tracemalloc
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = (
    REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py"
)
EXPANSION_PATH = GUARD_PATH.parent / "_push_pr_guard_expansion.py"

# Ceiling for peak allocation during one relevance decision. Set below the
# 2,562,194 bytes the merged tree materialized for the reported 10,920-byte
# input, so this file fails on the defect and passes only on a bounded
# implementation. A hostile 128 KiB command must not approach either the host's
# 10s PreToolUse timeout (where a Copilot timeout fails OPEN) or hundreds of
# MiB of RSS.
BYTE_BUDGET_CEILING = 512 * 1024


def _load_guard() -> ModuleType:
    """Load the expansion member of the guard's runtime unit.

    The budget lives in ``_push_pr_guard_expansion``, which the dispatched
    entrypoint imports. Loading that member directly keeps the assertions on
    the function that owns the budget instead of on a re-export.
    """
    if str(GUARD_PATH.parent) not in sys.path:
        sys.path.insert(0, str(GUARD_PATH.parent))
    spec = importlib.util.spec_from_file_location("push_pr_guard_under_test", EXPANSION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    return _load_guard()


def _peak_bytes(call) -> tuple[object, int]:
    """Run ``call`` and report its result with the peak traced allocation."""
    tracemalloc.start()
    try:
        result = call()
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


def _amplifying_command(literal_bytes: int, alternatives: int) -> str:
    """Build the shape that amplified: long literal text plus one brace group.

    Every alternative carries a copy of the literal prefix, so materializing
    the expansions costs ``literal_bytes * alternatives`` regardless of how
    small the alternatives themselves are.
    """
    prefix = "echo " + ("x" * literal_bytes) + " "
    body = ",".join(str(index) for index in range(alternatives))
    return prefix + "{" + body + "}"


def test_brace_expansion_bounds_total_expanded_bytes(guard: ModuleType) -> None:
    """The reported amplification must no longer be reachable.

    Reproduces the measured input almost exactly: a 10,921-byte command with
    256 brace alternatives, which materialized 2,562,194 bytes on the merged
    tree. The guard must decide relevance without allocating anywhere near that.
    """
    command = _amplifying_command(literal_bytes=10_000, alternatives=256)
    assert len(command) > 10_000

    (_verdict, peak) = _peak_bytes(lambda: guard._names_new_pr(command))

    assert peak < BYTE_BUDGET_CEILING, (
        f"relevance decision allocated {peak} bytes for a {len(command)}-byte command; "
        f"the merged tree allocated 2,598,415 for this shape"
    )


def test_brace_expansion_bounds_nested_groups(guard: ModuleType) -> None:
    """Nested groups multiply the count; the byte budget must still hold.

    Measured on the merged tree: a 100,060-byte command with eleven nested
    two-way groups produced 2,048 expansions totalling 204,832,768 bytes and a
    195.6 MiB peak, all while staying inside the 4096-expansion budget. Count
    budgets cannot bound bytes.
    """
    prefix = "echo " + ("x" * 100_000)
    command = prefix + "{a,b}" * 11

    (_verdict, peak) = _peak_bytes(lambda: guard._names_new_pr(command))

    assert peak < BYTE_BUDGET_CEILING, (
        f"nested brace enumeration allocated {peak} bytes; the merged tree peaked at "
        f"205,141,000 for this shape"
    )


def test_expansion_budget_fails_closed_when_exceeded(guard: ModuleType) -> None:
    """A command too large to enumerate must be treated as relevant, not skipped.

    Fail-closed is the whole point of the budget. If enumeration gives up and
    the caller reads that as "does not name new_pr.py", an attacker buys an
    allow by making the command expensive. The guard must place such a command
    IN scope so the strict policy runs and denies it.
    """
    command = _amplifying_command(literal_bytes=60_000, alternatives=5000)

    assert guard._names_new_pr(command) is True


def test_ordinary_brace_ranges_stay_allowed(guard: ModuleType) -> None:
    """Edge correctness: ranges, nesting, and large ordinary commands still pass.

    These are the commands the byte budget must not break. A range collapses to
    representative values rather than being materialized, so the count stays
    small no matter how wide the range is.
    """
    ordinary = (
        "touch log{0..99}.txt",
        "cp file{1..1000}.txt dir/",
        "mkdir -p build/{debug,release}/{bin,lib,obj}",
        "echo {a..z}",
        "mv report{2020..2030}.csv archive/",
        "rm -f build/{a,b,c}/{x,y,z}.o",
    )

    for command in ordinary:
        assert guard._names_new_pr(command) is False, f"{command} was treated as relevant"


def test_brace_range_edge_cases_still_resolve(guard: ModuleType) -> None:
    """A range that can spell the target keeps naming it.

    ``n{e..e..1}w_pr.py`` is the issue #4825 regression: Bash's optional step
    made the group read as literal text and skipped the guard. The byte budget
    must not reintroduce it by giving up on small inputs.
    """
    assert guard._names_new_pr("python3 n{e..e..1}w_pr.py") is True
    assert guard._names_new_pr("python3 n{e,x}w_pr.py") is True
    assert guard._names_new_pr("python3 {new_pr,other}.py") is True


def _many_token_command(token: str, repetitions: int) -> str:
    """Build a command whose cost is spread over many separately-budgeted calls."""
    return "\n".join([token] * repetitions)


def test_budget_is_shared_across_every_enumeration_for_one_command(guard: ModuleType) -> None:
    """A per-call budget bounds one enumeration; the command is what needs bounding.

    The guard enumerates once per spelling variant, per token, per segment.
    Measured on this branch before the fix, with a 121 KiB command built from
    4,600 copies of the 25-byte token ``p{a..z}{a..z}{a..z}{a..z}``: the
    relevance decision took 100.5 seconds, against 0.06 seconds on the merged
    tree, while every individual call stayed inside its own 256 KiB budget.

    The Copilot host allows a PreToolUse hook 10 seconds and a Copilot timeout
    fails OPEN, so a per-call budget alone is not an allowance.

    One shared budget makes the total the bounded thing: enumeration stops
    early and every caller reads the stop as "in scope", so the command is
    denied rather than run out the clock.
    """
    token = "p{a..z}{a..z}{a..z}{a..z}"
    command = _many_token_command(token, 4_600)
    assert len(command) > 100_000

    budget = guard._ExpansionBudget()
    (_verdict, peak) = _peak_bytes(
        lambda: [guard._path_names_new_pr(line, budget) for line in command.splitlines()]
    )

    assert peak < BYTE_BUDGET_CEILING, (
        f"a shared budget still allocated {peak} bytes across {len(command)} bytes of command"
    )
    assert budget.expanded_bytes <= guard._MAX_BRACE_EXPANDED_BYTES


def test_shared_budget_exhaustion_reports_relevance(guard: ModuleType) -> None:
    """Once the shared allowance is gone, every later answer must be fail-closed.

    An exhausted budget means the guard stopped looking, not that it looked
    and found nothing. Reading it as "not relevant" would sell an allow to
    anyone willing to make the command expensive.
    """
    budget = guard._ExpansionBudget()
    for _ in range(4_600):
        guard._path_names_new_pr("p{a..z}{a..z}{a..z}{a..z}", budget)

    assert guard._path_names_new_pr("harmless.txt", budget) is True
    assert guard._names_new_pr("harmless.txt", budget) is True


def test_private_budget_still_answers_small_inputs(guard: ModuleType) -> None:
    """Inverse control: the shared budget must not make ordinary calls fail closed.

    A caller with its own allowance, which is every single-string caller,
    still gets a real answer for an ordinary command.
    """
    assert guard._path_names_new_pr("tests/test_new_pr.py") is False
    assert guard._path_names_new_pr("./attacker/pr/new_pr.py") is True
    assert guard._names_new_pr("touch log{0..99}.txt") is False
