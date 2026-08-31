#!/usr/bin/env python3
"""Classify request intent and decide mutation authorization.

Encodes the task-intent invariant so it is testable, not just prose:

    Diagnose problem reports before mutating. Mutation requires explicit user
    authorization or an already-authorized workflow. Once mutation is
    authorized and enough information exists, act without asking again.

Three semantic modes:

    ASSESS    understand, explain, compare, evaluate (no mutation implied)
    DIAGNOSE  inspect evidence, reproduce, identify cause (no mutation implied)
    MUTATE    fix, update, apply, create, delete, send, merge, change state

A question or bare problem report does not authorize a state change. An
explicit imperative or an already-authorized workflow does. When authorization
already exists and enough information is present, the inverse guard suppresses
a redundant permission question.

The module is stdlib-only and deterministic so the negative controls run.

EXIT CODES (ADR-035):
    0 - Success (classification produced)
    2 - Invalid command or arguments
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys

ASSESS = "ASSESS"
DIAGNOSE = "DIAGNOSE"
MUTATE = "MUTATE"

SOURCE_NONE = "none"
SOURCE_EXPLICIT = "explicit_request"
SOURCE_WORKFLOW = "workflow"
SOURCE_CONDITIONAL = "conditional_fix"

# Leading verbs that request understanding only. They never authorize a change,
# even when a mutation word appears later in a hypothetical ("should we change").
ASSESS_VERBS: frozenset[str] = frozenset([
    "why", "is", "are", "was", "were", "does", "do", "did", "should", "could",
    "would", "can", "what", "which", "who", "when", "where", "how", "evaluate",
    "assess", "review", "compare", "explain", "describe", "analyze", "analyse",
    "investigate", "diagnose", "understand", "check", "inspect", "examine",
    "consider", "tell", "show", "list", "summarize", "summarise", "look",
    "audit", "identify", "determine", "clarify", "verify",
])

# Leading verbs that authorize the requested bounded change.
MUTATE_VERBS: frozenset[str] = frozenset([
    "fix", "update", "apply", "create", "file", "send", "merge", "change",
    "delete", "remove", "add", "implement", "write", "commit", "push",
    "rename", "patch", "set", "configure", "generate", "bump", "migrate",
    "install", "deploy", "refactor", "edit", "modify", "replace", "revert",
    "close", "assign", "comment", "format", "rebuild", "regenerate", "make",
    "build", "append", "insert", "drop", "reset", "rerun", "resolve",
])

# Words that mark a diagnostic problem report rather than a neutral question.
DIAGNOSTIC_MARKERS: frozenset[str] = frozenset([
    "why", "failing", "fails", "failed", "error", "errors", "broken", "break",
    "breaks", "cause", "causing", "reproduce", "crash", "crashes", "bug",
    "wrong", "debug", "regression", "flaky", "hang", "hangs", "stuck",
    "exception", "traceback", "misbehaving", "incorrect",
])

_CONDITIONAL_FIX_RE = re.compile(
    r"\b("
    r"and\s+fix|then\s+fix|fix\s+if|fix\s+only\s+if|"
    r"and\s+(?:repair|correct|patch)|"
    r"(?:repair|correct|patch)\s+if|"
    r"if\s+confirmed|if\s+it\s+is\s+confirmed|if\s+you\s+confirm"
    r")\b"
)

_TOKEN_RE = re.compile(r"[a-zA-Z']+")
_ISSUE_RE = re.compile(r"#\d+")
_PATHLIKE_RE = re.compile(r"[\w./-]*[\w]/[\w./-]+|[\w.-]+\.[A-Za-z]{1,6}")
_QUOTED_RE = re.compile(r"[\"'`]([^\"'`]{1,60})[\"'`]")


@dataclasses.dataclass(frozen=True)
class IntentDecision:
    """The outcome of classifying one request."""

    request: str
    intent: str
    mutation_authorized: bool
    authorization_source: str
    diagnosis_gated: bool
    authorized_targets: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable view."""
        return dataclasses.asdict(self)


def _leading_verb(text: str) -> str:
    """Return the first alphabetic token, lowercased, or an empty string."""
    match = _TOKEN_RE.search(text)
    return match.group(0).lower() if match else ""


def _has_conditional_fix(text: str) -> bool:
    """True when the request gates a change behind diagnosis (fix if confirmed)."""
    return _CONDITIONAL_FIX_RE.search(text.lower()) is not None


def _is_diagnostic(text: str) -> bool:
    """True when assessment language carries a problem-report marker."""
    tokens = {t.lower() for t in _TOKEN_RE.findall(text)}
    return bool(tokens & DIAGNOSTIC_MARKERS)


def _mutation_tokens_present(text: str) -> bool:
    """True when any mutation verb appears anywhere in the request."""
    tokens = {t.lower() for t in _TOKEN_RE.findall(text)}
    return bool(tokens & MUTATE_VERBS)


def extract_targets(text: str) -> tuple[str, ...]:
    """Extract explicit mutation targets: issue refs, path-like names, quotes.

    Used to bound authorization to the request. An empty result means the
    request named no concrete target, so scope cannot be narrowed by target.
    """
    found: list[str] = []
    found.extend(_ISSUE_RE.findall(text))
    found.extend(_PATHLIKE_RE.findall(text))
    found.extend(m.strip() for m in _QUOTED_RE.findall(text))
    seen: dict[str, None] = {}
    for item in found:
        key = item.strip()
        if key and key not in seen:
            seen[key] = None
    return tuple(seen)


def _assessment_decision(request: str) -> IntentDecision:
    """Build an ASSESS or DIAGNOSE decision (never authorizes mutation)."""
    intent = DIAGNOSE if _is_diagnostic(request) else ASSESS
    reason = (
        "diagnostic problem report; understand the cause before any change"
        if intent == DIAGNOSE
        else "assessment or question; no state change implied"
    )
    return IntentDecision(
        request=request,
        intent=intent,
        mutation_authorized=False,
        authorization_source=SOURCE_NONE,
        diagnosis_gated=False,
        authorized_targets=(),
        reason=reason,
    )


def classify(
    request: str,
    *,
    workflow_authorizes_mutation: bool = False,
    distinguish_intent: bool = True,
) -> IntentDecision:
    """Classify one request into an intent mode and an authorization decision.

    ``workflow_authorizes_mutation`` marks an already-authorized lifecycle or
    remediation workflow whose contract includes mutation.

    ``distinguish_intent=False`` disables the assessment gate. It exists for the
    negative control: without the ASSESS/DIAGNOSE distinction, a question that
    merely mentions a change word is misread as authorization to mutate.
    """
    targets = extract_targets(request)

    if workflow_authorizes_mutation:
        return IntentDecision(
            request=request,
            intent=MUTATE,
            mutation_authorized=True,
            authorization_source=SOURCE_WORKFLOW,
            diagnosis_gated=False,
            authorized_targets=targets,
            reason="active workflow contract authorizes the bounded mutation",
        )

    if _has_conditional_fix(request):
        return IntentDecision(
            request=request,
            intent=MUTATE,
            mutation_authorized=True,
            authorization_source=SOURCE_CONDITIONAL,
            diagnosis_gated=True,
            authorized_targets=targets,
            reason="diagnosis gates the change; a confirmed cause may be fixed",
        )

    leading = _leading_verb(request)

    if not distinguish_intent:
        # Negative control: without the intent distinction, any change word
        # anywhere reads as authorization.
        if _mutation_tokens_present(request):
            return IntentDecision(
                request=request,
                intent=MUTATE,
                mutation_authorized=True,
                authorization_source=SOURCE_EXPLICIT,
                diagnosis_gated=False,
                authorized_targets=targets,
                reason="intent distinction disabled; change word treated as authority",
            )
        return _assessment_decision(request)

    if leading in ASSESS_VERBS:
        return _assessment_decision(request)

    if leading in MUTATE_VERBS:
        return IntentDecision(
            request=request,
            intent=MUTATE,
            mutation_authorized=True,
            authorization_source=SOURCE_EXPLICIT,
            diagnosis_gated=False,
            authorized_targets=targets,
            reason="explicit imperative authorizes the bounded change",
        )

    # No recognized leading verb: a bare problem report or statement. Treat as
    # assessment or diagnosis. It does not authorize a change.
    return _assessment_decision(request)


def requires_permission_question(
    decision: IntentDecision,
    have_enough_info: bool,
    *,
    honor_existing_authorization: bool = True,
) -> bool:
    """Decide whether to ask the user for mutation permission.

    Returns False when mutation is already authorized and enough information
    exists: act, do not ask twice. Returns True only when a change is
    contemplated without authorization.

    ``honor_existing_authorization=False`` is the negative control: ignoring
    prior authorization makes an explicit fix request ask a redundant question.
    """
    if not honor_existing_authorization:
        return decision.intent == MUTATE or decision.mutation_authorized

    if decision.mutation_authorized:
        # Enough info: act. Not enough info: diagnose or gather, still no
        # redundant permission prompt.
        _ = have_enough_info
        return False

    return decision.intent == MUTATE


def action_requires_new_decision(
    decision: IntentDecision,
    proposed_targets: tuple[str, ...],
    *,
    workflow_scope_covers: bool = False,
    materially_broader: bool = False,
) -> bool:
    """True when a proposed action falls outside the authorized scope.

    Authorization is bounded by the request. A change to a target the user did
    not name, or a materially broader or destructive action than the request
    described, is a new material decision unless an active workflow already
    covers it. ``materially_broader`` is the caller's judgment that the action
    exceeds the described scope even when no explicit target names it.
    """
    if not decision.mutation_authorized:
        return True
    if workflow_scope_covers:
        return False
    if materially_broader:
        return True
    if decision.authorized_targets and proposed_targets:
        authorized = set(decision.authorized_targets)
        if not set(proposed_targets) <= authorized:
            return True
    return False


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="classify-intent",
        description="Classify request intent and decide mutation authorization.",
    )
    parser.add_argument("text", nargs="*", help="Request text (or read from stdin).")
    parser.add_argument(
        "--workflow-authorized",
        action="store_true",
        help="Mark an already-authorized workflow whose contract includes mutation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints the decision as JSON."""
    parser = build_parser()
    args = parser.parse_args(argv)
    request = " ".join(args.text) if args.text else sys.stdin.read()
    request = request.strip()
    if not request:
        print("Error: no request text provided", file=sys.stderr)
        return 2
    decision = classify(
        request,
        workflow_authorizes_mutation=args.workflow_authorized,
    )
    print(json.dumps(decision.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
