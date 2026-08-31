#!/usr/bin/env python3
"""Deterministic engine for the decision-question capability.

Turns a candidate decision into a bounded, decision-complete brief, or proves
no user question is warranted. The logic is deterministic so tests can pin the
routing, completeness, split, and prune behavior.

Harness option bound: the maximum number of options an interaction harness can
present in one AskUserQuestion prompt. This environment (GitHub Copilot CLI,
non-interactive agent) exposes no AskUserQuestion/ask_user tool in the agent
tool schema, so the bound could not be observed at runtime. It is encoded as
configurable with the issue's expected default of four and marked UNVERIFIED.
Callers that run inside a harness which does expose the tool should pass the
observed value to override MAX_PRESENTED_OPTIONS and flip HARNESS_LIMIT_OBSERVED.

Exit codes (CLI):
    0  routing resolved: either no question is warranted, or a complete bounded
       brief was produced.
    1  invalid arguments or unreadable/malformed brief JSON.
    2  a question is warranted but the brief is not decision-complete or cannot
       be presented within the harness bound.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# Harness option bound. UNVERIFIED in this environment: no AskUserQuestion tool
# is exposed to observe. Default four per issue #5408; override when observed.
MAX_PRESENTED_OPTIONS = 4
HARNESS_LIMIT_OBSERVED = False
HARNESS_LIMIT_SOURCE = (
    "default; no AskUserQuestion/ask_user tool exposed in the GitHub Copilot CLI "
    "agent tool schema to observe the per-prompt option cap"
)

# Continuation sentinel used when options exceed the bound and must be paginated
# into a split chain. It occupies one option slot and decides nothing.
CONTINUATION_ID = "_more"

# Routing skip reasons, evaluated in order. The first match short-circuits.
_SKIP_REASONS: list[tuple[str, str]] = [
    ("task_terminal", "task already terminal; STOP TOKEN wins (#5404); no optional-follow-up prompt"),
    ("delegated", "user delegated the choice; act within existing authorization"),
    ("policy_mandated", "one path is mandated by repository or safety policy"),
    ("acceptance_criteria_determined", "existing acceptance criteria already determine the choice"),
    ("implementation_detail_authorized", "implementation detail within authorized scope"),
    ("resolvable_by_evidence", "resolvable by reading available evidence or tools"),
]


@dataclass(frozen=True)
class Option:
    """One materially distinct path the user can choose."""

    id: str
    label: str
    consequence: str = ""
    # Prior answers that must hold for this option to remain on the brief.
    requires: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Option:
        return cls(
            id=str(data["id"]),
            label=str(data.get("label", "")),
            consequence=str(data.get("consequence", "")),
            requires={str(k): str(v) for k, v in (data.get("requires") or {}).items()},
        )


@dataclass(frozen=True)
class Decision:
    """A single user decision with a stable identity."""

    id: str
    statement: str
    why_now: str
    options: list[Option]
    recommendation: str | None = None
    recommendation_reason: str = ""
    no_recommendation: bool = False
    allow_hold: bool = False
    hold_reopen_condition: str = ""
    # Prior answers that must hold before this decision becomes actionable.
    requires: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decision:
        return cls(
            id=str(data["id"]),
            statement=str(data.get("statement", "")),
            why_now=str(data.get("why_now", "")),
            options=[Option.from_dict(o) for o in data.get("options", [])],
            recommendation=(str(data["recommendation"]) if data.get("recommendation") else None),
            recommendation_reason=str(data.get("recommendation_reason", "")),
            no_recommendation=bool(data.get("no_recommendation", False)),
            allow_hold=bool(data.get("allow_hold", False)),
            hold_reopen_condition=str(data.get("hold_reopen_condition", "")),
            requires={str(k): str(v) for k, v in (data.get("requires") or {}).items()},
        )


def route(context: dict[str, Any]) -> tuple[bool, str]:
    """Decide whether a user question is warranted.

    Returns (should_ask, reason). Skip conditions win over asking, so a
    delegated or policy-mandated choice never produces a question even when it
    is also flagged material.
    """

    for key, reason in _SKIP_REASONS:
        if context.get(key):
            return (False, reason)
    if not context.get("material_decision"):
        return (False, "no material unresolved user decision; act within existing authorization")
    return (True, "material unresolved user decision; present a bounded decision brief")


def _option_active(option: Option, answers: dict[str, str]) -> bool:
    return all(answers.get(dep) == val for dep, val in option.requires.items())


def missing_brief_fields(decision: Decision) -> list[str]:
    """Return the decision-completeness gaps. Empty list means complete.

    A brief is complete when it names what must be decided, why now, at least
    two materially distinct options each with a consequence, and either a
    recommendation with its load-bearing reason or an explicit no-recommendation
    stance. A hold offer must carry a reopen condition.
    """

    missing: list[str] = []
    if not decision.statement.strip():
        missing.append("statement")
    if not decision.why_now.strip():
        missing.append("why_now")

    options = decision.options
    if len(options) < 2:
        missing.append("at_least_two_options")
    labels = [o.label.strip().lower() for o in options]
    if len(labels) != len(set(labels)):
        missing.append("options_not_distinct")
    for option in options:
        if not option.consequence.strip():
            missing.append(f"option[{option.id}].consequence")

    if decision.no_recommendation:
        if decision.recommendation:
            missing.append("recommendation_conflicts_with_no_recommendation")
    elif not decision.recommendation:
        missing.append("recommendation_or_explicit_none")
    else:
        option_ids = {o.id for o in options}
        if decision.recommendation not in option_ids:
            missing.append("recommendation_unknown_option")
        if not decision.recommendation_reason.strip():
            missing.append("recommendation_reason")

    if decision.allow_hold and not decision.hold_reopen_condition.strip():
        missing.append("hold_reopen_condition")

    return missing


def is_complete(decision: Decision) -> bool:
    return not missing_brief_fields(decision)


def plan_prompt_pages(
    options: list[Option], max_options: int = MAX_PRESENTED_OPTIONS
) -> list[list[Option]]:
    """Split options into ordered prompt pages that respect the harness bound.

    When options fit, one page and no sentinel. When they exceed the bound,
    paginate deterministically: every non-final page reserves one slot for a
    continuation sentinel so the user can advance. Every returned page has at
    most ``max_options`` entries.
    """

    if max_options < 2:
        raise ValueError("max_options must be at least 2 to leave room for a real choice")
    if len(options) <= max_options:
        return [list(options)]

    continuation = Option(
        id=CONTINUATION_ID,
        label="See more options",
        consequence="Advance to the next page of choices; nothing is decided yet.",
    )
    per_page_real = max_options - 1
    pages: list[list[Option]] = []
    remaining = list(options)
    while remaining:
        chunk = remaining[:per_page_real]
        remaining = remaining[per_page_real:]
        pages.append(chunk + [continuation] if remaining else chunk)
    return pages


def prune_chain(decisions: list[Decision], answers: dict[str, str]) -> list[Decision]:
    """Drop decisions whose prerequisites are unmet and filter dead options.

    A dependent decision is removed once a recorded answer makes it irrelevant.
    Surviving decisions keep only options still reachable under the answers, so
    a later decision is recomputed rather than shown with impossible choices.
    IDs are preserved; nothing is renumbered.
    """

    kept: list[Decision] = []
    for decision in decisions:
        if not all(answers.get(dep) == val for dep, val in decision.requires.items()):
            continue
        live_options = [o for o in decision.options if _option_active(o, answers)]
        kept.append(replace(decision, options=live_options))
    return kept


def next_decision(decisions: list[Decision], answers: dict[str, str]) -> Decision | None:
    """Return the earliest unanswered decision whose prerequisites are met."""

    for decision in prune_chain(decisions, answers):
        if decision.id not in answers:
            return decision
    return None


def _load_brief(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("brief JSON must be an object")
    return data


def _parse_brief(data: dict[str, Any]) -> tuple[list[Decision], dict[str, Any], dict[str, str]]:
    if "decisions" in data:
        decisions = [Decision.from_dict(d) for d in data["decisions"]]
    else:
        decisions = [Decision.from_dict(data)]
    context = dict(data.get("context") or {})
    answers = {str(k): str(v) for k, v in (data.get("answers") or {}).items()}
    return decisions, context, answers


def evaluate(data: dict[str, Any], max_options: int = MAX_PRESENTED_OPTIONS) -> dict[str, Any]:
    """Route, then validate and plan the next actionable decision."""

    decisions, context, answers = _parse_brief(data)
    should_ask, reason = route(context)
    result: dict[str, Any] = {
        "should_ask": should_ask,
        "reason": reason,
        "max_presented_options": max_options,
        "harness_limit_observed": HARNESS_LIMIT_OBSERVED,
    }
    if not should_ask:
        result["status"] = "skip"
        return result

    decision = next_decision(decisions, answers)
    if decision is None:
        result["status"] = "resolved"
        result["reason"] = "no actionable decision remains after pruning"
        return result

    result["decision_id"] = decision.id
    missing = missing_brief_fields(decision)
    if missing:
        result["status"] = "incomplete"
        result["missing"] = missing
        return result

    pages = plan_prompt_pages(decision.options, max_options)
    result["status"] = "ask"
    result["pages"] = [[o.id for o in page] for page in pages]
    result["split"] = len(pages) > 1
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a decision-question brief.")
    parser.add_argument("--brief", required=True, help="Path to a decision brief JSON file.")
    parser.add_argument(
        "--max-options",
        type=int,
        default=MAX_PRESENTED_OPTIONS,
        help="Observed harness option bound (default: unverified 4).",
    )
    args = parser.parse_args(argv)

    path = Path(args.brief)
    try:
        data = _load_brief(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot read brief: {exc}", file=sys.stderr)
        return 1

    try:
        result = evaluate(data, max_options=args.max_options)
    except (KeyError, ValueError) as exc:
        print(f"error: malformed brief: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result["status"] == "incomplete":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
