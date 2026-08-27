"""Contract test between `pr-autofix.md`'s tier guard and its producer's tier set.

Refs #5094. The guard has to agree with `test_pr_merge_ready.py` about two
separate properties, and collapsing them is what put `SKIP` on the acting path:

- **Recognition**: every value `classify_tier` can return must be named in some
  arm, or a healthy classification reads as a producer failure and the loop
  skips a PR it should have worked.
- **Dispatch**: only the actionable ones may fall through to the gates.

Split out of `test_pr_autofix_field_contract.py` so both files stay under the
500-line taste rule. The extractors live in `pr_autofix_tier_parser.py`; the
runtime behavior of the same guard is covered by
`test_pr_autofix_tier_dispatch_runtime.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands.pr_autofix_field_parser import COMMAND_PATH, MIRROR_PATH
from tests.commands.pr_autofix_tier_parser import (
    declared_tiers,
    dispatched_tiers,
    recognized_tiers,
)


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_the_guard_recognizes_exactly_what_the_producer_declares(doc: Path) -> None:
    """Recognition must equal `_TIER_ORDER`, not the T1-T5 prose ladder.

    The guard first shipped listing only T1 through T5, because it was written
    against the tier ladder in the command's own documentation instead of the
    producer's `_TIER_ORDER`. That rejected BEHIND, BLOCKED, DIRTY, and SKIP as
    producer failures and silently disabled the documented BEHIND and DIRTY
    handling: a fail-closed guard that closes on healthy input is worse than the
    fail-open it replaced, because it stops real work and says nothing.

    Recognition counts every arm, terminating or not, because a tier that
    terminates deliberately is still recognized. What each tier then *does* is
    the separate question the next test asks.
    """
    declared = declared_tiers()
    assert declared is not None, "could not read _TIER_ORDER from the producer"

    recognized = recognized_tiers(doc.read_text(encoding="utf-8"))
    assert recognized is not None, f"{doc.name} has no tier guard; the fail-open is back"

    assert recognized == frozenset(declared), (
        f"{doc.name} recognizes {sorted(recognized)}, but the producer declares "
        f"{sorted(declared)}. Quote the producer's tuple rather than restating the ladder."
    )


def test_a_second_no_op_arm_is_visible_to_the_dispatch_extractor() -> None:
    """The extractor must union every no-op arm, not stop at the first.

    This is the negative control for the case above, and the case above cannot
    supply it. `dispatched_tiers` used `search`, which returns the first match
    and no more, so a `case` carrying a second empty arm put that arm's tiers
    back on the acting path invisibly. Both assertions in
    `test_skip_is_recognized_but_never_dispatched` still passed against such a
    document: `SKIP` was absent from the returned set, and the set still equalled
    `declared - {"SKIP"}`. The guard reported green on precisely the defect it
    was written to catch.

    The input is synthetic rather than the shipped document, because the shipped
    document is correct and a control has to supply the shape the code gets
    wrong (testing rule SHOULD 10). Restoring `search` fails this and nothing
    else, which is what makes it the discriminating case.
    """
    two_arm_block = (
        "# tier-dispatch:start\n"
        'case "$TIER" in\n'
        "    T1|T2|T3|T4|T5|BEHIND|BLOCKED|DIRTY) ;;\n"
        "    SKIP) ;;\n"
        "    *)\n"
        '        echo "unknown"\n'
        "        ;;\n"
        "esac\n"
        "# tier-dispatch:end\n"
    )

    dispatched = dispatched_tiers(two_arm_block)

    assert dispatched is not None
    assert "SKIP" in dispatched, (
        "the extractor read only the first no-op arm, so a second one is invisible "
        f"and SKIP silently reaches the gates; got {sorted(dispatched)}"
    )


# Recognized but never dispatched: the tier table gives each of these an action
# that is not "keep working this PR", so neither may reach the gates.
#
# - SKIP ("Draft, merged, or closed", "No action"). Recognizing it in the
#   pass-through arm let it reach the auto-merge disarm gate, where `SKIP != T1`
#   holds, so a PR that went draft, merged, or closed after the live-state gate
#   ran would have had auto-merge stripped by a loop that had just decided it
#   was non-actionable.
# - UNSUPPORTED (`mergeStateStatus` with no verified merge path). Dispatching it
#   routes a PR with zero threads and zero CI failures into the T3/T4 round-cap
#   thread-fix loop, which has no action to take and terminates only by burning
#   the round cap and posting an escalation comment. Unlike SKIP it terminates
#   after the disarm gate, not before, because "armed but not provably T1" is
#   exactly true of it.
_TERMINAL_TIERS = frozenset({"SKIP", "UNSUPPORTED"})


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_terminal_tiers_are_recognized_but_never_dispatched(doc: Path) -> None:
    """Recognized is not actionable, and conflating them put SKIP on the acting path."""
    declared = declared_tiers()
    assert declared is not None
    assert _TERMINAL_TIERS <= frozenset(declared), (
        f"the producer no longer declares {sorted(_TERMINAL_TIERS - frozenset(declared))}; "
        "update this list rather than the assertion below."
    )

    dispatched = dispatched_tiers(doc.read_text(encoding="utf-8"))
    assert dispatched is not None, f"{doc.name} has no tier guard"

    assert not (dispatched & _TERMINAL_TIERS), (
        f"{doc.name} dispatches {sorted(dispatched & _TERMINAL_TIERS)}, which the tier "
        "table defines as terminal."
    )
    assert dispatched == frozenset(declared) - _TERMINAL_TIERS, (
        f"{doc.name} dispatches {sorted(dispatched)}; expected every declared tier "
        f"except {sorted(_TERMINAL_TIERS)}."
    )
