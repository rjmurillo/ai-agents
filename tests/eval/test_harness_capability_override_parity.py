"""classify_override equal-value negative control (issue #5423 reopen).

PR #5547 shipped `classify_override` without a guard for the case where a
child requests the same value the parent already has. Run against
pre-fix code, `classify_override("sol-medium", "sol-medium",
EvidenceKind.BACKEND, parent_value="sol-medium")` returned `VERIFIED`: a
backend value equal to both the request and the parent is indistinguishable
from the override mechanism never running and the value simply passing
through unchanged. `test_equal_parent_and_child_value_is_never_verified`
is the negative control that closes this gap; it failed on pre-fix code
(returned VERIFIED, not UNVERIFIED) and passes after the fix. The other two
tests are regression guards proving the fix does not overreach: a genuinely
differing, honored override must still verify, and a request made with no
parent context at all (issue #5423 Arm E, single-agent) must be unaffected.
Both already passed before this change and continue to pass after it.
"""

from __future__ import annotations

from tests.eval._harness_capability_test_support import capability

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind


# --- Negative control: the equal-value trap ------------------------------------


def test_equal_parent_and_child_value_is_never_verified() -> None:
    status = capability.classify_override(
        "sol-medium", "sol-medium", EvidenceKind.BACKEND, parent_value="sol-medium"
    )
    assert status is CapabilityStatus.UNVERIFIED


def test_equal_value_trap_applies_to_effort_too() -> None:
    # The same undecidable case can arise on effort_override, not only
    # model_override; classify_override backs both.
    status = capability.classify_override(
        "high", "high", EvidenceKind.BACKEND, parent_value="high"
    )
    assert status is CapabilityStatus.UNVERIFIED


# --- Regression guards: the fix must not overreach -----------------------------


def test_genuinely_differing_honored_override_still_verifies() -> None:
    status = capability.classify_override(
        "luna-high", "luna-high", EvidenceKind.BACKEND, parent_value="sol-medium"
    )
    assert status is CapabilityStatus.VERIFIED


def test_no_parent_context_still_verifies_on_matching_backend_value() -> None:
    # Arm E (single-agent, issue #5423) has no parent to compare against.
    # The equal-value guard only fires when parent_value is given; without
    # one, a matching backend observation is still the best available
    # evidence and must keep verifying.
    status = capability.classify_override("sol-medium", "sol-medium", EvidenceKind.BACKEND)
    assert status is CapabilityStatus.VERIFIED
