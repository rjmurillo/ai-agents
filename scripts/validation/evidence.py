# taste-lint: ignore file-size. This module is one type contract and must stay
# one module: scripts/validation/ is imported both flat (pre_pr.py inserts the
# directory on sys.path) and as a package (tests use scripts.validation.X), so
# splitting the policy half out would give the two import paths two distinct
# EvidenceState enums and every `is` comparison across the seam would silently
# return False. That is the dual-module-identity trap issue #3073 records for
# pre_pr. Roughly a third of the lines are docstrings and rationale comments.
"""Typed evidence states for repository validators.

A validator that returns ``bool`` can say only "clean" or "dirty". Every other
outcome has to borrow one of those two words, and in this tree it has always
borrowed ``True``: a base ref that would not resolve, a ``git diff`` that
exited non-zero, a linter that is not installed, and a script an install does
not ship all returned the same value as a check that ran and proved its
contract. The caller cannot tell them apart, so the gate reports success for a
check that never looked (issue #5635).

Five states replace the two:

``PASS``
    Ran against the intended revision and scope, and proved the contract. The
    only state a blocking gate accepts by default.
``FAIL``
    Ran, and found a violation.
``SKIP``
    Intentionally did not apply, and says why in a reason code.
``BLOCKED``
    Could not run: a required dependency or external service was unavailable.
``UNKNOWN``
    Ran, or tried to, but the evidence was incomplete, malformed, stale, or
    truncated.

``BLOCKED`` and ``UNKNOWN`` differ by who is at fault for the missing evidence.
``BLOCKED`` means a precondition was absent, so nothing was observed and the
reader should go install or authenticate something. ``UNKNOWN`` means an
observation was attempted and what came back could not be trusted, so the
reader should go look at the output. Collapsing them costs the reader the first
diagnostic step, the same defect ``.claude/rules/ci-scripts.md`` MUST 14
records for the count ratchets.

Prior art this mirrors rather than reinvents:

- ``scripts/eval/_harness_capability.py`` (issue #5630) proved the shape on the
  capability probes: a typed status, a separate evidence kind, a restrictive
  default, and worst-wins aggregation over an explicit precedence tuple.
- ``scripts/ai_review_common/verdict.py`` established that an empty set of
  child verdicts aggregates to ``UNKNOWN``, not to ``PASS``.
- ``scripts/ci/merge_tree_ratchet_check.py`` established that the ways a
  measurement fails to happen are separate states, because they share no
  remedy.

This is one module on purpose. Splitting the policy half out would give a flat
``from evidence import ...`` and a package ``from scripts.validation.evidence
import ...`` two distinct ``EvidenceState`` enums, and every ``is`` comparison
across the seam would silently return False. That is the dual-module-identity
trap issue #3073 records for ``pre_pr``.

Import discipline: standard library only, so a step invoking a script with bare
``python3`` can use it (``ci-scripts.md`` MUST 18), and nothing from this
package, so ``pre_pr_sequence`` can use it without a back-reference to
``pre_pr``.

Related: issue #5635. Callers: ``scripts/validation/pre_pr.py``,
``scripts/validation/pre_pr_sequence.py``, ``scripts/validation/checks_*.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Final

__all__ = [
    "AggregateOutcome",
    "CheckOutcome",
    "EvidenceState",
    "GatePolicy",
    "GateResult",
    "PolicyException",
    "REASON_ALREADY_RUN",
    "REASON_AUTH_UNAVAILABLE",
    "REASON_BASE_REF_UNRESOLVED",
    "REASON_DIFF_FAILED",
    "REASON_INCOMPLETE_EVIDENCE",
    "REASON_LEGACY_BOOLEAN",
    "REASON_MALFORMED_OUTPUT",
    "REASON_NO_OUTCOMES",
    "REASON_QUICK_MODE",
    "REASON_SCRIPT_ABSENT",
    "REASON_TIMEOUT",
    "REASON_TOOL_ABSENT",
    "REASON_TREE_ABSENT",
    "REASON_VALIDATOR_RAISED",
    "WORKING_TREE",
    "aggregate",
    "coerce_outcome",
    "default_pre_pr_policy",
    "exit_code_for",
    "worst_state",
]


class EvidenceState(str, Enum):
    """What a validator actually observed.

    Inherits ``str`` so a state serializes to its own name in JSON and compares
    equal to the bare string this tree already writes in many places.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


#: Aggregation precedence, worst first. ``FAIL`` outranks the no-evidence states
#: because a proven violation is more actionable than an absent observation, and
#: both no-evidence states outrank ``SKIP`` because a check that could not run is
#: not a check that did not apply.
_PRECEDENCE: Final[tuple[EvidenceState, ...]] = (
    EvidenceState.FAIL,
    EvidenceState.UNKNOWN,
    EvidenceState.BLOCKED,
    EvidenceState.SKIP,
    EvidenceState.PASS,
)

#: Revision sentinel for a check whose subject is the working tree or the index
#: rather than a named ref. ``ci-scripts.md`` MUST 9 requires a claim about what
#: the repository *contains* to name a ref, and permits a working-tree read
#: where that state is itself the subject; this value says which one a ``PASS``
#: is claiming.
WORKING_TREE: Final = "WORKING_TREE"

# Machine-readable reason codes. Any string matching _REASON_PATTERN is legal;
# these are the ones this tree needs, named so a consumer greps a constant
# rather than a spelling.
REASON_BASE_REF_UNRESOLVED: Final = "base_ref.unresolved"
REASON_DIFF_FAILED: Final = "diff.failed"
REASON_SCRIPT_ABSENT: Final = "script.absent"
REASON_TOOL_ABSENT: Final = "tool.absent"
REASON_TREE_ABSENT: Final = "tree.absent"
REASON_TIMEOUT: Final = "timeout"
REASON_MALFORMED_OUTPUT: Final = "output.malformed"
REASON_INCOMPLETE_EVIDENCE: Final = "evidence.incomplete"
REASON_AUTH_UNAVAILABLE: Final = "auth.unavailable"
REASON_QUICK_MODE: Final = "policy.quick_mode"
REASON_ALREADY_RUN: Final = "policy.already_run"
REASON_VALIDATOR_RAISED: Final = "validator.raised"
REASON_LEGACY_BOOLEAN: Final = "legacy.boolean_contract"
REASON_NO_OUTCOMES: Final = "aggregate.no_outcomes"

#: Dotted lowercase slug. Machine-readable means a consumer can branch on it,
#: which a free-text sentence does not support.
_REASON_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """One validator's evidence about one scope.

    Construct through :meth:`passed`, :meth:`failed`, :meth:`skipped`,
    :meth:`blocked`, or :meth:`unknown`: each fills the fields its state
    requires, so a caller cannot reach a state it has no evidence for by
    forgetting an argument.

    ``examined`` is how many items the check looked at. ``ci-scripts.md``
    MUST 12 requires it, because "0 violations in 381 files" is verifiable and
    "OK" is not.
    """

    validator: str
    state: EvidenceState
    revision: str = ""
    scope: str = ""
    reason: str = ""
    detail: str = ""
    examined: int | None = None
    findings: int | None = None
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Reject a result whose fields contradict its state."""
        self._check_field_shapes()
        if self.state is EvidenceState.PASS:
            self._check_pass_evidence()
        elif not self.reason:
            raise ValueError(
                f"{self.validator}: {self.state.value} requires a machine-readable reason code"
            )

    def _check_field_shapes(self) -> None:
        """Reject values no state could carry."""
        if not self.validator.strip():
            raise ValueError("CheckOutcome.validator must be a non-empty name")
        if not isinstance(self.state, EvidenceState):
            raise TypeError(
                f"CheckOutcome.state must be an EvidenceState, got {type(self.state).__name__}"
            )
        if self.reason and not _REASON_PATTERN.match(self.reason):
            raise ValueError(
                f"CheckOutcome.reason {self.reason!r} is not a machine-readable "
                "code; expected a dotted lowercase slug such as 'diff.failed'"
            )
        for name, value in (("examined", self.examined), ("findings", self.findings)):
            if value is not None and value < 0:
                raise ValueError(f"CheckOutcome.{name} must not be negative, got {value}")
        if self.duration_seconds < 0:
            raise ValueError(
                f"CheckOutcome.duration_seconds must not be negative, got {self.duration_seconds}"
            )

    def _check_pass_evidence(self) -> None:
        """Reject a PASS that cannot be falsified or that contradicts itself.

        Without a revision and a scope, a ``PASS`` states only that some code
        ran, which is the claim issue #5635 exists to stop accepting.
        """
        if not self.revision.strip():
            raise ValueError(
                f"{self.validator}: PASS requires a revision (a ref, a SHA, "
                f"or the {WORKING_TREE} sentinel)"
            )
        if not self.scope.strip():
            raise ValueError(f"{self.validator}: PASS requires a scope naming what was checked")
        if self.reason:
            raise ValueError(
                f"{self.validator}: PASS must not carry a reason code (got {self.reason!r}); "
                "a reason explains why a check did not prove its contract"
            )
        if self.findings:
            raise ValueError(f"{self.validator}: PASS must not report {self.findings} finding(s)")

    @classmethod
    def passed(
        cls,
        validator: str,
        *,
        revision: str,
        scope: str,
        examined: int | None = None,
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> CheckOutcome:
        """Record that the check ran against ``revision``/``scope`` and proved it."""
        return cls(
            validator=validator,
            state=EvidenceState.PASS,
            revision=revision,
            scope=scope,
            examined=examined,
            findings=0,
            detail=detail,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def failed(
        cls,
        validator: str,
        *,
        reason: str,
        revision: str = "",
        scope: str = "",
        examined: int | None = None,
        findings: int | None = None,
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> CheckOutcome:
        """Record that the check ran and found a violation."""
        return cls(
            validator=validator,
            state=EvidenceState.FAIL,
            revision=revision,
            scope=scope,
            reason=reason,
            examined=examined,
            findings=findings,
            detail=detail,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def unknown(
        cls,
        validator: str,
        *,
        reason: str,
        revision: str = "",
        scope: str = "",
        examined: int | None = None,
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> CheckOutcome:
        """Record that the evidence was incomplete, malformed, stale, or truncated."""
        return cls(
            validator=validator,
            state=EvidenceState.UNKNOWN,
            revision=revision,
            scope=scope,
            reason=reason,
            examined=examined,
            detail=detail,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def skipped(
        cls,
        validator: str,
        *,
        reason: str,
        scope: str = "",
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> CheckOutcome:
        """Record that the check intentionally did not apply."""
        return cls._no_observation(
            validator, EvidenceState.SKIP, reason, scope, detail, duration_seconds
        )

    @classmethod
    def blocked(
        cls,
        validator: str,
        *,
        reason: str,
        scope: str = "",
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> CheckOutcome:
        """Record that a required dependency or service was unavailable."""
        return cls._no_observation(
            validator, EvidenceState.BLOCKED, reason, scope, detail, duration_seconds
        )

    @classmethod
    def _no_observation(
        cls,
        validator: str,
        state: EvidenceState,
        reason: str,
        scope: str,
        detail: str,
        duration_seconds: float,
    ) -> CheckOutcome:
        """Build the two states that observed nothing, so carry no counts."""
        return cls(
            validator=validator,
            state=state,
            scope=scope,
            reason=reason,
            detail=detail,
            duration_seconds=duration_seconds,
        )

    def with_duration(self, duration_seconds: float) -> CheckOutcome:
        """Return a copy timed at ``duration_seconds``.

        The runner owns the clock, so a validator that does not time itself
        returns 0.0 and the runner stamps the measured value here.
        """
        return replace(self, duration_seconds=duration_seconds)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form consumers parse."""
        return {
            "validator": self.validator,
            "state": self.state.value,
            "revision": self.revision,
            "scope": self.scope,
            "reason": self.reason,
            "detail": self.detail,
            "examined": self.examined,
            "findings": self.findings,
            "duration_seconds": round(self.duration_seconds, 4),
        }

    def summary_line(self) -> str:
        """Return one human line naming the state, reason, scope, and counts.

        A reader who sees only ``[SKIP] Session End Validation`` cannot tell a
        gate that did not apply from one whose base ref would not resolve.
        """
        parts = [f"[{self.state.value}] {self.validator}"]
        if self.reason:
            parts.append(f"reason={self.reason}")
        if self.scope:
            parts.append(f"scope={self.scope}")
        if self.revision:
            parts.append(f"rev={self.revision}")
        if self.examined is not None:
            parts.append(f"examined={self.examined}")
        if self.findings:
            parts.append(f"findings={self.findings}")
        return " ".join(parts)


#: What a gate row may return. ``bool`` stays legal so the migration can move
#: one validator at a time; :func:`coerce_outcome` tags every bool it wraps so
#: the unmigrated rows stay countable rather than invisible.
GateResult = bool | CheckOutcome


def coerce_outcome(validator: str, result: object) -> CheckOutcome:
    """Adapt a validator's return value to a :class:`CheckOutcome`.

    A ``CheckOutcome`` passes through unchanged. A ``bool`` becomes ``PASS`` or
    ``FAIL``, tagged ``legacy.boolean_contract`` on the failing side. Anything
    else is ``UNKNOWN``: a validator that returned ``None`` or a string told the
    runner nothing, and guessing ``PASS`` for it is the defect this module
    exists to remove.
    """
    if isinstance(result, CheckOutcome):
        return result
    if isinstance(result, bool):
        if result:
            return CheckOutcome.passed(
                validator,
                revision=WORKING_TREE,
                scope="whole validator (unmigrated boolean contract)",
                detail="Validation passed",
            )
        return CheckOutcome.failed(
            validator, reason=REASON_LEGACY_BOOLEAN, detail="Validation failed"
        )
    return CheckOutcome.unknown(
        validator,
        reason=REASON_MALFORMED_OUTPUT,
        detail=(
            f"validator returned {type(result).__name__}, "
            "which is neither a bool nor a CheckOutcome"
        ),
    )


def worst_state(states: Iterable[EvidenceState]) -> EvidenceState:
    """Return the worst state in ``states`` by :data:`_PRECEDENCE`.

    An empty input is ``UNKNOWN``, never ``PASS``: nothing was observed, so
    there is no evidence to report. ``merge_verdicts`` and
    ``_worst_eligibility`` already default the same way in this tree.
    """
    seen = set(states)
    if not seen:
        return EvidenceState.UNKNOWN
    for candidate in _PRECEDENCE:
        if candidate in seen:
            return candidate
    raise ValueError(
        f"worst_state received unrecognized states: {sorted(str(state) for state in seen)}"
    )


@dataclass(frozen=True, slots=True)
class PolicyException:
    """A bounded, auditable licence for one non-``PASS`` state to not block.

    The justification is required, not optional: an exception nobody can review
    is not policy. ``validator`` accepts ``"*"`` to cover every row; ``reasons``
    empty means any reason code, and naming reasons narrows the licence to the
    ones a reviewer actually considered.
    """

    validator: str
    states: frozenset[EvidenceState]
    justification: str
    reasons: frozenset[str] = field(default_factory=frozenset)
    reference: str = ""

    def __post_init__(self) -> None:
        """Reject an exception that licenses nothing or explains nothing."""
        if not self.validator.strip():
            raise ValueError("PolicyException.validator must name a validator or '*'")
        if not self.states:
            raise ValueError(
                f"PolicyException for {self.validator!r} names no states, so it licenses nothing"
            )
        if EvidenceState.PASS in self.states:
            raise ValueError(
                f"PolicyException for {self.validator!r} names PASS, which every policy "
                "already accepts; an exception must license a state that blocks"
            )
        if not self.justification.strip():
            raise ValueError(
                f"PolicyException for {self.validator!r} requires a justification; "
                "an unexplained exception cannot be reviewed"
            )

    def covers(self, outcome: CheckOutcome) -> bool:
        """Return True when this exception licenses ``outcome``."""
        if self.validator not in ("*", outcome.validator):
            return False
        if outcome.state not in self.states:
            return False
        return not self.reasons or outcome.reason in self.reasons

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form."""
        return {
            "validator": self.validator,
            "states": sorted(state.value for state in self.states),
            "reasons": sorted(self.reasons),
            "justification": self.justification,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class GatePolicy:
    """What a blocking gate accepts.

    The default accepts ``PASS`` and nothing else. ``SKIP``, ``BLOCKED``, and
    ``UNKNOWN`` block unless a :class:`PolicyException` names them.
    """

    exceptions: tuple[PolicyException, ...] = ()

    def accepts(self, outcome: CheckOutcome) -> bool:
        """Return True when ``outcome`` does not block the gate."""
        if outcome.state is EvidenceState.PASS:
            return True
        return any(exception.covers(outcome) for exception in self.exceptions)

    def rejected(self, outcomes: Iterable[CheckOutcome]) -> tuple[CheckOutcome, ...]:
        """Return the outcomes that block the gate, in input order."""
        return tuple(outcome for outcome in outcomes if not self.accepts(outcome))

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form."""
        return {
            "accepted_without_exception": [EvidenceState.PASS.value],
            "exceptions": [exception.to_dict() for exception in self.exceptions],
        }


def default_pre_pr_policy() -> GatePolicy:
    """Return the policy the pre-PR gate runs under.

    One exception, and it predates issue #5635: a gate that does not apply to
    this checkout has never blocked the push, and
    ``.agents/devops/SHIFT-LEFT.md`` documents that. ``BLOCKED`` and
    ``UNKNOWN`` get no exception; those are the states that used to arrive as
    ``True``.
    """
    return GatePolicy(
        exceptions=(
            PolicyException(
                validator="*",
                states=frozenset({EvidenceState.SKIP}),
                justification=(
                    "A gate that does not apply to this checkout does not block the "
                    "push. ADR-042 expunged the PowerShell validators, so a downstream "
                    "install legitimately lacks scripts this repository ships, and "
                    "--quick plus the pre-push fast stage skip rows on purpose. Every "
                    "SKIP names a reason code, so a reader can tell which."
                ),
                reference=".agents/devops/SHIFT-LEFT.md",
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class AggregateOutcome:
    """A parent's state plus every child state that produced it.

    The children are kept rather than reduced to counters: a summary that
    reports only "3 skipped" cannot answer which three, and the reason codes
    are the actionable part.
    """

    name: str
    state: EvidenceState
    outcomes: tuple[CheckOutcome, ...]
    rejected: tuple[CheckOutcome, ...]
    policy: GatePolicy
    duration_seconds: float = 0.0

    @property
    def blocking(self) -> bool:
        """Return True when at least one child blocks under the policy."""
        return bool(self.rejected)

    def counts(self) -> dict[str, int]:
        """Return the per-state child counts, every state present at zero."""
        tally = {state.value: 0 for state in EvidenceState}
        for outcome in self.outcomes:
            tally[outcome.state.value] += 1
        return tally

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable summary a consumer parses."""
        return {
            "name": self.name,
            "state": self.state.value,
            "blocking": self.blocking,
            "exit_code": exit_code_for(self),
            "duration_seconds": round(self.duration_seconds, 4),
            "counts": self.counts(),
            "policy": self.policy.to_dict(),
            "results": [outcome.to_dict() for outcome in self.outcomes],
            "rejected": [outcome.to_dict() for outcome in self.rejected],
        }


def aggregate(
    name: str,
    outcomes: Iterable[CheckOutcome],
    policy: GatePolicy | None = None,
    duration_seconds: float = 0.0,
) -> AggregateOutcome:
    """Reduce child outcomes to one parent state without losing the children.

    The parent state is the worst child by :data:`_PRECEDENCE`. An empty child
    set aggregates to ``UNKNOWN``: a run that examined nothing proved nothing.
    """
    resolved_policy = GatePolicy() if policy is None else policy
    children = tuple(outcomes)
    return AggregateOutcome(
        name=name,
        state=worst_state(outcome.state for outcome in children),
        outcomes=children,
        rejected=resolved_policy.rejected(children),
        policy=resolved_policy,
        duration_seconds=duration_seconds,
    )


def exit_code_for(summary: AggregateOutcome) -> int:
    """Map a blocking aggregate to its ADR-035 exit code.

    ``0`` when nothing blocks. Otherwise the worst blocking state decides:
    ``FAIL`` and ``UNKNOWN`` are logic errors (``1``), ``BLOCKED`` is an
    external dependency (``3``), and a rejected ``SKIP`` is a configuration
    error (``2``) because the run was asked for a check this checkout cannot
    supply.
    """
    if not summary.rejected:
        return 0
    blocking = worst_state(outcome.state for outcome in summary.rejected)
    if blocking is EvidenceState.BLOCKED:
        return 3
    if blocking is EvidenceState.SKIP:
        return 2
    return 1
