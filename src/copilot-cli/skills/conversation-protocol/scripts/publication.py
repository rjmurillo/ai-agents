#!/usr/bin/env python3
"""Deterministic enforcement for the review-conversation protocol.

The prose protocol lives in ``SKILL.md``. This module is the mechanical floor
underneath it: the invariants a human or an LLM could restate but must not be
trusted to hold by prose alone. Every function here is pure and network-free so
the protocol's load-bearing claims are unit-testable and can fail for the right
reason.

Boundary (issue #5403): the technical review layer (``/review``,
``reviewer-findings``) decides *what* a finding is and *how severe* it is. This
publication layer decides only *how it is rendered and discussed*. It never
mutates canonical technical severity. That separation is enforced structurally:
``render_finding`` echoes the finding's disposition verbatim and has no branch
that inspects wording to relabel it, so a blocker cannot be rendered as a nit
and an optional finding cannot be rendered as required.

What each piece maps to in the issue's acceptance criteria:

- ``Disposition`` / ``disposition_for_severity`` / ``render_finding``:
  "Required/optional/nit/FYI disposition is unambiguous" and "Publication cannot
  mutate canonical technical severity".
- ``sanitize_comment`` / ``scan_conduct``: "Comments address code/claims rather
  than author character or intent" (shared invariant 1).
- ``response_action``: the author/responder decision tree (verify, then accept /
  split / push back / investigate; never bluff, never auto-comply).
- ``RoundState`` + ``merge_round_state``: "Review-loop bounds survive
  context/agent handoffs" and "A new agent cannot reset an exhausted debate".
- ``deduplicate``: "Duplicate AI comments are suppressed/deduplicated".

Exit codes follow ADR-035 when run as a CLI self-check:
    0 - self-check passed
    1 - self-check failed
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import SupportsInt, cast

# ---------------------------------------------------------------------------
# Disposition and severity
# ---------------------------------------------------------------------------


class Disposition(Enum):
    """The four published dispositions from issue #5403's publication contract.

    ``BLOCKING`` is the "BLOCKING / REQUIRED" tier; ``OPTIONAL`` is the
    "OPTIONAL / CONSIDER" tier. Only ``BLOCKING`` gates approval.
    """

    BLOCKING = "BLOCKING"
    OPTIONAL = "OPTIONAL"
    NIT = "NIT"
    FYI = "FYI"

    @property
    def gates_approval(self) -> bool:
        """True only for the tier that must resolve before approval."""
        return self is Disposition.BLOCKING


# Canonical technical severities emitted by the review skill
# (`.claude/skills/review/SKILL.md`: "severity: CRITICAL | IMPORTANT | SUGGESTION").
# Quoted verbatim from that source on 2026-08-31 so this map mirrors the
# canonical vocabulary rather than an imagined one.
_SEVERITY_TO_DISPOSITION: dict[str, Disposition] = {
    "CRITICAL": Disposition.BLOCKING,
    "IMPORTANT": Disposition.BLOCKING,
    "SUGGESTION": Disposition.OPTIONAL,
}


def disposition_for_severity(severity: str) -> Disposition:
    """Map a canonical technical severity to a published disposition.

    Deterministic and total over the known severities. Unknown input fails
    closed with ``ValueError`` rather than silently downgrading to a
    non-gating disposition, because a silent downgrade is exactly the
    severity mutation the protocol forbids.
    """
    if not isinstance(severity, str):
        raise ValueError(f"severity must be a string, got {type(severity).__name__}")
    key = severity.strip().upper()
    if key not in _SEVERITY_TO_DISPOSITION:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of "
            f"{sorted(_SEVERITY_TO_DISPOSITION)}"
        )
    return _SEVERITY_TO_DISPOSITION[key]


# ---------------------------------------------------------------------------
# Conduct: address the code, not the person
# ---------------------------------------------------------------------------

# ponytail: regex conduct floor. A regex cannot faithfully rewrite a personal
# attack into a code-focused finding; that nuance is the authoring LLM's job.
# This is the mechanical guarantee that a blocker cannot smuggle a personal
# attack past publication: pejoratives are redacted, and author-directed
# second-person phrasing is rejected so it must be rephrased. Upgrade path: an
# LLM rewrite pass in front of this floor if false rejections become common.
_PEJORATIVES: tuple[str, ...] = (
    "sloppy",
    "lazy",
    "careless",
    "stupid",
    "dumb",
    "idiotic",
    "incompetent",
    "garbage",
    "nonsense",
    "amateur",
    "clueless",
)

# Second-person phrasing directed at the author. These attribute the problem to
# a person rather than to the code or the claim.
_PERSONAL_ADDRESS = re.compile(
    r"\byou(?:'re|r| are| clearly| obviously| should have| didn't|"
    r" did not| failed to| never| always)\b",
    re.IGNORECASE,
)

_PEJORATIVE_RE = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in _PEJORATIVES) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ConductReport:
    """What a conduct scan found in one piece of comment text."""

    pejoratives: tuple[str, ...]
    personal_address: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.pejoratives and not self.personal_address


class ConductError(ValueError):
    """Raised when text addresses the person and cannot be mechanically fixed."""


def scan_conduct(text: str) -> ConductReport:
    """Report pejoratives and author-directed phrasing without altering text."""
    pejoratives = tuple(m.group(0) for m in _PEJORATIVE_RE.finditer(text))
    personal = tuple(m.group(0) for m in _PERSONAL_ADDRESS.finditer(text))
    return ConductReport(pejoratives=pejoratives, personal_address=personal)


def sanitize_comment(text: str) -> str:
    """Return conduct-clean comment text or raise ``ConductError``.

    Pejoratives are redacted (suppressed) because dropping a loaded adjective
    leaves the technical point intact. Author-directed second-person phrasing is
    rejected, not rewritten, because a faithful rewrite needs judgment this
    floor does not have; the caller must rephrase to address the code.
    """
    report = scan_conduct(text)
    if report.personal_address:
        raise ConductError(
            "comment addresses the author, not the code: "
            f"{sorted(set(report.personal_address))}. Rephrase to describe the "
            "code, the claim, and its consequence."
        )
    # Redact pejoratives and collapse the whitespace the removal leaves behind.
    redacted = _PEJORATIVE_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", redacted).strip()


# ---------------------------------------------------------------------------
# Published finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Attribution:
    """Provenance for a finding or reply in a mixed human/AI thread."""

    author: str
    is_ai: bool

    def label(self) -> str:
        kind = "AI" if self.is_ai else "human"
        return f"{self.author} ({kind})"


@dataclass(frozen=True, slots=True)
class Finding:
    """A validated finding ready for publication.

    ``disposition`` is decided upstream by the technical layer and is immutable
    here. ``render_finding`` never changes it.
    """

    disposition: Disposition
    problem: str
    why: str = ""
    evidence: str = ""
    fix_direction: str = ""
    attribution: Attribution | None = None


def render_finding(finding: Finding) -> str:
    """Render a finding for the PR thread.

    The disposition label is ``finding.disposition.value`` verbatim. There is
    deliberately no code path that reads the comment text to decide the label,
    so publication cannot promote a nit to a blocker or downgrade a blocker to
    FYI. Conduct is enforced on every author-supplied line.
    """
    problem = sanitize_comment(finding.problem)
    lines = [f"[{finding.disposition.value}] {problem}"]
    if finding.why:
        lines.append(f"Why: {sanitize_comment(finding.why)}")
    if finding.evidence:
        lines.append(f"Evidence: {sanitize_comment(finding.evidence)}")
    if finding.fix_direction:
        lines.append(f"Fix direction: {sanitize_comment(finding.fix_direction)}")
    if finding.attribution is not None:
        lines.append(f"-- {finding.attribution.label()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Author / responder decision tree
# ---------------------------------------------------------------------------


class Verification(Enum):
    """Outcome of verifying a finding against code/tests/contracts."""

    CORRECT = "correct"
    PARTLY_CORRECT = "partly_correct"
    INCORRECT = "incorrect"
    INSUFFICIENT = "insufficient"


class ResponseAction(Enum):
    """What the author/responder does after verifying (issue #5403 tree)."""

    ACCEPT_AND_FIX = "accept_and_fix"
    SPLIT = "split"
    PUSH_BACK = "push_back"
    INVESTIGATE = "investigate"


_VERIFICATION_TO_ACTION: dict[Verification, ResponseAction] = {
    Verification.CORRECT: ResponseAction.ACCEPT_AND_FIX,
    Verification.PARTLY_CORRECT: ResponseAction.SPLIT,
    Verification.INCORRECT: ResponseAction.PUSH_BACK,
    Verification.INSUFFICIENT: ResponseAction.INVESTIGATE,
}


def response_action(verification: Verification) -> ResponseAction:
    """Route a verification outcome to its response action.

    ``INSUFFICIENT`` routes to ``INVESTIGATE``, never to compliance and never to
    a fabricated pushback: the protocol forbids bluffing on either side.
    """
    return _VERIFICATION_TO_ACTION[verification]


# ---------------------------------------------------------------------------
# Bounded escalation and thread-state handoff
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoundState:
    """Review-loop state that must survive a context or agent handoff.

    A new context cannot reset the round counter or revive a resolved finding:
    ``merge_round_state`` takes the elementwise maximum and the union, and
    ``reopen`` refuses without new evidence.
    """

    round_count: int = 0
    max_rounds: int = 3
    resolved: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.round_count < 0:
            raise ValueError("round_count must be >= 0")
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")

    @property
    def exhausted(self) -> bool:
        """True when the debate has hit its round cap and must escalate."""
        return self.round_count >= self.max_rounds

    def advance(self) -> RoundState:
        return RoundState(self.round_count + 1, self.max_rounds, self.resolved)

    def resolve(self, finding_id: str) -> RoundState:
        return RoundState(
            self.round_count, self.max_rounds, self.resolved | {finding_id}
        )

    def reopen(self, finding_id: str, new_evidence: bool) -> RoundState:
        """Reopen a resolved finding only when new contradictory evidence exists."""
        if finding_id in self.resolved and not new_evidence:
            raise ConductError(
                f"cannot reopen resolved finding {finding_id!r} without new "
                "evidence; resolved findings stay resolved"
            )
        return RoundState(
            self.round_count, self.max_rounds, self.resolved - {finding_id}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "round_count": self.round_count,
            "max_rounds": self.max_rounds,
            "resolved": sorted(self.resolved),
        }

    @staticmethod
    def from_dict(data: Mapping[str, object]) -> RoundState:
        # Deserialization boundary: a handoff payload is untyped. Cast the
        # values to the shapes the constructor needs; int() still coerces a
        # JSON number or numeric string at runtime.
        resolved_raw = data.get("resolved") or []
        return RoundState(
            round_count=int(cast(SupportsInt, data["round_count"])),
            max_rounds=int(cast(SupportsInt, data.get("max_rounds", 3))),
            resolved=frozenset(cast(Iterable[str], resolved_raw)),
        )


def merge_round_state(incoming: RoundState, current: RoundState) -> RoundState:
    """Combine handoff state so progress cannot be rewound.

    Round count is the maximum of the two, so a fresh context arriving with a
    zeroed counter cannot reset an exhausted debate. Resolved findings are the
    union, so no handoff revives a resolved finding.
    """
    return RoundState(
        round_count=max(incoming.round_count, current.round_count),
        max_rounds=max(incoming.max_rounds, current.max_rounds),
        resolved=incoming.resolved | current.resolved,
    )


# ---------------------------------------------------------------------------
# Duplicate comment suppression
# ---------------------------------------------------------------------------


def _normalize(comment: str) -> str:
    """Reduce a comment to a comparison key: lowercase, punctuation-free."""
    lowered = comment.casefold()
    stripped = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", stripped).strip()


def deduplicate(comments: Sequence[str]) -> list[str]:
    """Drop near-duplicate comments, keeping the first occurrence.

    Two comments that differ only in whitespace, case, or punctuation collapse
    to one, so an agent cannot use repetition as pressure.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for comment in comments:
        key = _normalize(comment)
        if key and key not in seen:
            seen.add(key)
            kept.append(comment)
    return kept


# ---------------------------------------------------------------------------
# CLI self-check
# ---------------------------------------------------------------------------


def _self_check() -> bool:
    """Smallest runnable proof of the load-bearing invariants."""
    ok = True

    # A blocker renders as a blocker, never a nit/FYI.
    rendered = render_finding(Finding(Disposition.BLOCKING, "guard is missing"))
    ok = ok and rendered.startswith("[BLOCKING]")
    ok = ok and "[NIT]" not in rendered and "[FYI]" not in rendered

    # Severity cannot silently downgrade.
    ok = ok and disposition_for_severity("CRITICAL").gates_approval
    ok = ok and not disposition_for_severity("SUGGESTION").gates_approval

    # A new context cannot reset an exhausted debate.
    merged = merge_round_state(RoundState(0), RoundState(3, resolved=frozenset({"f1"})))
    ok = ok and merged.round_count == 3 and "f1" in merged.resolved

    # Personal wording is rejected.
    try:
        sanitize_comment("You clearly didn't test this.")
        ok = False  # pragma: no cover - unreachable: sanitize_comment always raises here
    except ConductError:
        pass

    return ok


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess in tests
    sys.exit(0 if _self_check() else 1)
