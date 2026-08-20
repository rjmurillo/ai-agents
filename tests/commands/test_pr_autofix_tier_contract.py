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


@pytest.mark.parametrize("doc", [COMMAND_PATH, MIRROR_PATH])
def test_skip_is_recognized_but_never_dispatched(doc: Path) -> None:
    """Recognized is not actionable, and conflating them put SKIP on the acting path.

    The command's own tier table reads `| SKIP | Draft, merged, or closed | No
    action |`. Recognizing SKIP in the pass-through arm let it reach the
    auto-merge disarm gate, where `SKIP != T1` holds, so a PR that went draft,
    merged, or closed after the live-state gate ran would have had auto-merge
    stripped by a loop that had just decided it was non-actionable.
    """
    declared = declared_tiers()
    assert declared is not None

    dispatched = dispatched_tiers(doc.read_text(encoding="utf-8"))
    assert dispatched is not None, f"{doc.name} has no tier guard"

    assert "SKIP" not in dispatched, (
        f"{doc.name} dispatches SKIP, which the tier table defines as no action."
    )
    assert dispatched == frozenset(declared) - {"SKIP"}, (
        f"{doc.name} dispatches {sorted(dispatched)}; expected every declared tier but SKIP."
    )
