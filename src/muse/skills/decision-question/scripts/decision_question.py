#!/usr/bin/env python3
"""Deterministic engine for the decision-question capability.

Turns a candidate decision into a bounded, decision-complete brief, or proves
that no user question is warranted. The logic is deterministic so tests pin the
routing, completeness, split, prune, and hold behavior.

Harness bound: Claude Code's AskUserQuestion input schema accepts 1 to 4
questions per call and 2 to 4 options per question. The tool adds an "Other"
free-text choice itself, so "Other" does not count against the option bound.
Observed in the Claude Code 2.1.296 binary (the schema text says the bounds are
hard constraints and to split into multiple calls instead). Other harnesses may
differ: pass the value observed there with --max-options.

Exit codes (CLI):
    0  routing resolved: no question warranted, a complete bounded brief was
       produced, or every remaining decision is held.
    1  invalid arguments or unreadable/malformed brief JSON.
    2  a question is warranted but the brief is not decision-complete, or an
       earlier answer filtered out its recommended option (revise_recommendation).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

MAX_PRESENTED_OPTIONS = 4
MIN_PRESENTED_OPTIONS = 2
MAX_QUESTIONS_PER_CALL = 4
HARNESS_LIMIT_OBSERVED = True
HARNESS_LIMIT_SOURCE = (
    "Claude Code 2.1.296 AskUserQuestion input schema: questions min 1 max 4, "
    "options 2-4 per question, 'Other' added by the tool"
)

# Reserved option ids. Both occupy a presented slot and decide nothing about
# the underlying choice: _more advances a split chain, _hold defers it.
CONTINUATION_ID = "_more"
HOLD_ID = "_hold"
RESERVED_IDS = frozenset({CONTINUATION_ID, HOLD_ID})

# Routing skip reasons, evaluated in order. The first match short-circuits.
_SKIP_REASONS: list[tuple[str, str]] = [
    (
        "task_terminal",
        "task already terminal; STOP TOKEN wins (#5404); no optional-follow-up prompt",
    ),
    ("delegated", "user delegated the choice; act within existing authorization"),
    ("policy_mandated", "one path is mandated by repository or safety policy"),
    ("acceptance_criteria_determined", "existing acceptance criteria already determine the choice"),
    ("implementation_detail_authorized", "implementation detail within authorized scope"),
    ("resolvable_by_evidence", "resolvable by reading available evidence or tools"),
]

# Chain states for a decision under a set of recorded answers.
LIVE = "live"
PENDING = "pending"
PRUNED = "pruned"
BLOCKED = "blocked"


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


def _option_gaps(options: list[Option]) -> list[str]:
    gaps: list[str] = []
    if len(options) < MIN_PRESENTED_OPTIONS:
        gaps.append("at_least_two_options")
    labels = [o.label.strip().lower() for o in options]
    if len(labels) != len(set(labels)):
        gaps.append("options_not_distinct")
    gaps.extend(f"option[{o.id}].reserved_id" for o in options if o.id in RESERVED_IDS)
    gaps.extend(f"option[{o.id}].consequence" for o in options if not o.consequence.strip())
    return gaps


def _recommendation_gaps(decision: Decision) -> list[str]:
    if decision.no_recommendation:
        return (
            ["recommendation_conflicts_with_no_recommendation"] if decision.recommendation else []
        )
    if not decision.recommendation:
        return ["recommendation_or_explicit_none"]
    gaps: list[str] = []
    if decision.recommendation not in {o.id for o in decision.options}:
        gaps.append("recommendation_unknown_option")
    if not decision.recommendation_reason.strip():
        gaps.append("recommendation_reason")
    return gaps


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
    missing.extend(_option_gaps(decision.options))
    missing.extend(_recommendation_gaps(decision))
    if decision.allow_hold and not decision.hold_reopen_condition.strip():
        missing.append("hold_reopen_condition")
    return missing


def is_complete(decision: Decision) -> bool:
    return not missing_brief_fields(decision)


def plan_prompt_pages(
    options: list[Option], max_options: int = MAX_PRESENTED_OPTIONS, hold: bool = False
) -> list[list[Option]]:
    """Split options into ordered prompt pages that respect the harness bound.

    Every page holds between MIN_PRESENTED_OPTIONS and ``max_options`` entries.
    A non-final page ends with a continuation sentinel. When ``hold`` is true,
    a Hold entry closes every page, because Hold is always a legitimate answer
    and a sentinel-only page would hide it. Hold and the sentinel both occupy a
    presented slot.
    """

    if max_options < MIN_PRESENTED_OPTIONS + 1:
        raise ValueError("max_options must be at least 3 to paginate and keep a real choice")
    hold_entry = [_hold_option()] if hold else []
    final_cap = max_options - len(hold_entry)
    if len(options) <= final_cap:
        return [list(options) + hold_entry]

    mid_cap = final_cap - 1
    chunks: list[list[Option]] = []
    remaining = list(options)
    while len(remaining) > final_cap:
        chunks.append(remaining[:mid_cap])
        remaining = remaining[mid_cap:]
    pages = [chunk + [_continuation_option()] for chunk in chunks]
    pages.append(remaining)
    return [page + hold_entry for page in pages]


def _continuation_option() -> Option:
    return Option(
        id=CONTINUATION_ID,
        label="See more options",
        consequence="Advance to the next page of choices; nothing is decided yet.",
    )


def _hold_option() -> Option:
    return Option(
        id=HOLD_ID,
        label="Hold",
        consequence="Leave this decision unresolved; it reopens on the stated condition.",
    )


def _dependency_state(requires: dict[str, str], answers: dict[str, str]) -> str:
    """Classify a decision (or option) against recorded answers."""

    state = LIVE
    for dep, wanted in requires.items():
        got = answers.get(dep)
        if got is None:
            state = PENDING if state == LIVE else state
        elif got == HOLD_ID:
            state = BLOCKED
        elif got != wanted:
            return PRUNED
    return state


def chain_state(decisions: list[Decision], answers: dict[str, str]) -> dict[str, str]:
    """Map each decision id to LIVE, PENDING, PRUNED, or BLOCKED.

    A decision whose own prerequisites hold is still not actionable while any
    of its options waits on an unanswered or held prerequisite: asking it now
    would hide that option from the user.
    """

    return {d.id: _decision_state(d, answers) for d in decisions}


def _decision_state(decision: Decision, answers: dict[str, str]) -> str:
    own = _dependency_state(decision.requires, answers)
    if own != LIVE:
        return own
    option_states = {_dependency_state(o.requires, answers) for o in decision.options}
    for waiting in (PENDING, BLOCKED):
        if waiting in option_states:
            return waiting
    return LIVE


def prune_chain(decisions: list[Decision], answers: dict[str, str]) -> list[Decision]:
    """Keep live decisions and filter options that earlier answers made dead.

    IDs are preserved; nothing is renumbered. A decision whose prerequisite is
    unanswered, held, or answered differently is not live.
    """

    states = chain_state(decisions, answers)
    kept: list[Decision] = []
    for decision in decisions:
        if states[decision.id] != LIVE:
            continue
        live = [o for o in decision.options if _dependency_state(o.requires, answers) == LIVE]
        kept.append(replace(decision, options=live))
    return kept


def next_decision(decisions: list[Decision], answers: dict[str, str]) -> Decision | None:
    """Return the earliest unanswered live decision."""

    for decision in prune_chain(decisions, answers):
        if decision.id not in answers:
            return decision
    return None


def held_records(decisions: list[Decision], answers: dict[str, str]) -> list[dict[str, str]]:
    """Decisions the user held, each with the condition that reopens it."""

    return [
        {"id": d.id, "reopen_condition": d.hold_reopen_condition}
        for d in decisions
        if answers.get(d.id) == HOLD_ID
    ]


def _validate_answers(decisions: list[Decision], answers: dict[str, str]) -> None:
    by_id = {d.id: d for d in decisions}
    for decision_id, value in answers.items():
        decision = by_id.get(decision_id)
        if decision is None:
            raise ValueError(f"answer for unknown decision {decision_id}")
        if value == CONTINUATION_ID:
            raise ValueError(
                f"{decision_id} answer {CONTINUATION_ID!r} is a page request; "
                "record it under paging, not answers"
            )
        if value == HOLD_ID and not decision.allow_hold:
            raise ValueError(f"{decision_id} was held but offers no Hold")
        if value != HOLD_ID and value not in {o.id for o in decision.options}:
            raise ValueError(f"{decision_id} answer {value!r} is not one of its options")


def _load_brief(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("brief JSON must be an object")
    return data


def _parse_brief(data: dict[str, Any]) -> tuple[list[Decision], dict[str, str], dict[str, int]]:
    if "decisions" in data:
        decisions = [Decision.from_dict(d) for d in data["decisions"]]
    else:
        decisions = [Decision.from_dict(data)]
    ids = [d.id for d in decisions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate decision id: {', '.join(duplicates)}")
    answers = {str(k): str(v) for k, v in (data.get("answers") or {}).items()}
    _validate_answers(decisions, answers)
    paging = _parse_paging(data.get("paging") or {}, decisions)
    return decisions, answers, paging


def _parse_paging(raw: dict[str, Any], decisions: list[Decision]) -> dict[str, int]:
    """Read the page cursor per decision: how many `_more` picks were recorded."""

    known = {d.id for d in decisions}
    paging: dict[str, int] = {}
    for decision_id, count in raw.items():
        if str(decision_id) not in known:
            raise ValueError(f"paging for unknown decision {decision_id}")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"paging for {decision_id} must be a non-negative integer")
        paging[str(decision_id)] = count
    return paging


def _ask_result(decision: Decision, max_options: int, page_index: int = 0) -> dict[str, Any]:
    missing = missing_brief_fields(decision)
    if missing:
        return {"status": "incomplete", "decision_id": decision.id, "missing": missing}
    pages = plan_prompt_pages(decision.options, max_options, hold=decision.allow_hold)
    if page_index >= len(pages):
        raise ValueError(
            f"paging for {decision.id} is {page_index} but it has {len(pages)} page(s)"
        )
    ids = [[o.id for o in page] for page in pages]
    return {
        "status": "ask",
        "decision_id": decision.id,
        "pages": ids,
        "page_index": page_index,
        "page": ids[page_index],
        "split": len(pages) > 1,
    }


def _stale_recommendation(decisions: list[Decision], decision: Decision) -> dict[str, Any] | None:
    """Detect a recommendation that earlier answers filtered out of the options."""

    original = next(d for d in decisions if d.id == decision.id)
    live = {o.id for o in decision.options}
    stale = original.recommendation
    if decision.no_recommendation or stale is None or stale in live:
        return None
    if stale not in {o.id for o in original.options}:
        return None
    return {
        "status": "revise_recommendation",
        "decision_id": decision.id,
        "stale_recommendation": stale,
        "remaining_options": [o.id for o in decision.options],
    }


def evaluate(data: dict[str, Any], max_options: int = MAX_PRESENTED_OPTIONS) -> dict[str, Any]:
    """Route, then validate and plan the next actionable decision."""

    context = dict(data.get("context") or {})
    should_ask, reason = route(context)
    result: dict[str, Any] = {
        "should_ask": should_ask,
        "reason": reason,
        "max_presented_options": max_options,
        "harness_limit_observed": HARNESS_LIMIT_OBSERVED,
    }
    if not should_ask:
        return {**result, "status": "skip"}
    decisions, answers, paging = _parse_brief(data)
    if context.get("irreversible") and context.get("weak_evidence"):
        result["pre_ask_review"] = ["decision-critic", "pre-mortem"]

    states = chain_state(decisions, answers)
    result["deferred"] = sorted(i for i, s in states.items() if s in (PENDING, BLOCKED))
    result["pruned"] = sorted(i for i, s in states.items() if s == PRUNED)
    held = held_records(decisions, answers)
    if held:
        result["held"] = held

    decision = next_decision(decisions, answers)
    if decision is not None:
        stale = _stale_recommendation(decisions, decision)
        if stale is not None:
            return {**result, **stale}
        return {**result, **_ask_result(decision, max_options, paging.get(decision.id, 0))}
    if held:
        return {**result, "status": "held", "reason": "every open decision is held"}
    return {
        **result,
        "status": "resolved",
        "reason": "no actionable decision remains after pruning",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a decision-question brief.")
    parser.add_argument("--brief", required=True, help="Path to a decision brief JSON file.")
    parser.add_argument(
        "--max-options",
        type=int,
        default=MAX_PRESENTED_OPTIONS,
        help="Options per prompt the harness accepts (default: Claude Code observed 4).",
    )
    args = parser.parse_args(argv)

    try:
        data = _load_brief(Path(args.brief))
        result = evaluate(data, max_options=args.max_options)
    except (OSError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 2 if result["status"] in ("incomplete", "revise_recommendation") else 0


if __name__ == "__main__":
    sys.exit(main())
