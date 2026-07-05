"""Pure core for the end-to-end delivery eval (issue #2859).

The routing eval (`eval-prompt-change.py`) only scores a single classify-
and-route decision. On 13 routing fixtures orchestrator and autoplan both
scored 100 percent: it proves they pick the lane, not that either can carry
an under-specified ask to a correct change with tests, docs, and gates.

This module is the *plan-rubric proxy* (harness shape 2 in the issue). It
feeds each agent a deliberately vague germ, captures the plan the agent
emits, and has an LLM judge score that plan against hidden acceptance
criteria. Every function here is pure and API-free so the scoring, parsing,
and aggregation logic is unit-testable without a network call; the live
orchestration lives in `eval-e2e-delivery.py`.

Ground-truth discipline (the load-bearing requirement in #2859): a fixture's
`hidden_criteria` are derived from a *real merged PR* that closed the source
issue, not from the phrasing of the agent prompt under test. That keeps the
criteria independent of the prompts. It does NOT remove the closed-loop
caveat: the fixtures and criteria are still curated by one author, so
absolute scores are directional. The report prints this caveat.

Proxy limit: plan quality is a proxy for delivery. A high plan score does
not prove the resulting code compiles or passes tests. Only the trace-based
shape (run the agent, grade the diff) proves that; see #2859 shape 1.
"""

from __future__ import annotations

import json
import re
from typing import Any

SCHEMA_VERSION: int = 1

# Per-axis maximum points. Total = 11. The axes operationalize the four
# things the issue says the delivery must be scored on plus the ask-vs-guess
# boundary it calls out explicitly.
RUBRIC_AXES: dict[str, int] = {
    "scope": 3,          # right-sized: not over- or under-engineered
    "completeness": 3,   # covers behavior + required tests + docs
    "process_gates": 2,  # acknowledges lint / session log / mirror gates
    "decomposition": 2,  # sensible, non-inflated task breakdown
    "correct_stop": 1,   # ask-vs-produce boundary handled correctly
}
MAX_SCORE: int = sum(RUBRIC_AXES.values())

# Required fixture keys and the required hidden-criteria sub-keys. A fixture
# missing any of these is a design error, not a runtime edge case, so we
# fail loud at load time.
_REQUIRED_FIXTURE_KEYS = frozenset({"id", "prompt", "kind", "hidden_criteria"})
_REQUIRED_CRITERIA_KEYS = frozenset(
    {
        "behavior",
        "required_tests",
        "required_docs",
        "required_gates",
        "ambiguous_stop_expected",
    }
)
_VALID_KINDS = frozenset({"feature", "bug", "ambiguous", "multi-domain"})

PARSE_ERROR = "PARSE_ERROR"


class FixtureError(ValueError):
    """Raised when a fixture file fails schema validation."""


def validate_fixture(fixture: dict[str, Any]) -> None:
    """Validate one fixture dict. Raises FixtureError on any violation."""
    missing = _REQUIRED_FIXTURE_KEYS - fixture.keys()
    if missing:
        raise FixtureError(
            f"fixture {fixture.get('id', '<no id>')!r} missing keys: "
            f"{sorted(missing)}"
        )
    kind = fixture["kind"]
    if kind not in _VALID_KINDS:
        raise FixtureError(
            f"fixture {fixture['id']!r} has invalid kind {kind!r}; "
            f"expected one of {sorted(_VALID_KINDS)}"
        )
    criteria = fixture["hidden_criteria"]
    if not isinstance(criteria, dict):
        raise FixtureError(
            f"fixture {fixture['id']!r} hidden_criteria must be an object"
        )
    missing_c = _REQUIRED_CRITERIA_KEYS - criteria.keys()
    if missing_c:
        raise FixtureError(
            f"fixture {fixture['id']!r} hidden_criteria missing: "
            f"{sorted(missing_c)}"
        )
    if not isinstance(criteria["ambiguous_stop_expected"], bool):
        raise FixtureError(
            f"fixture {fixture['id']!r} ambiguous_stop_expected must be bool"
        )
    # An `ambiguous` fixture that does not expect a stop, or a non-ambiguous
    # fixture that does, is a self-contradiction that would silently score
    # the correct_stop axis backwards.
    if (kind == "ambiguous") != bool(criteria["ambiguous_stop_expected"]):
        raise FixtureError(
            f"fixture {fixture['id']!r}: kind={kind!r} disagrees with "
            f"ambiguous_stop_expected={criteria['ambiguous_stop_expected']!r}"
        )


def load_fixtures(raw: str) -> list[dict[str, Any]]:
    """Parse and validate a fixtures JSON document.

    Accepts either a bare list of fixtures or an object with a top-level
    ``fixtures`` array and optional ``schemaVersion``. Every fixture is
    validated; duplicate ids are rejected.
    """
    doc = json.loads(raw)
    if isinstance(doc, dict):
        version = doc.get("schemaVersion", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise FixtureError(
                f"unsupported schemaVersion {version!r}; "
                f"this harness handles {SCHEMA_VERSION}"
            )
        fixtures = doc.get("fixtures")
    else:
        fixtures = doc
    if not isinstance(fixtures, list) or not fixtures:
        raise FixtureError("fixtures document must contain a non-empty list")
    seen: set[str] = set()
    for fx in fixtures:
        if not isinstance(fx, dict):
            raise FixtureError("each fixture must be an object")
        validate_fixture(fx)
        if fx["id"] in seen:
            raise FixtureError(f"duplicate fixture id {fx['id']!r}")
        seen.add(fx["id"])
    return fixtures


def build_agent_user_message(germ: str) -> str:
    """The user turn handed to an agent: the vague germ plus a plan request.

    The germ is intentionally under-specified. We ask only for the plan the
    agent would follow, not for the code, because this is the proxy shape.
    """
    return (
        f"{germ.strip()}\n\n"
        "Produce the plan you would follow to carry this to done. Include: "
        "the concrete change, the tests you would add (positive, negative, "
        "edge), the docs or specs you would update, and the gates you would "
        "run. If the request is too ambiguous to act on safely, say so and "
        "state the clarifying question you would ask instead of guessing."
    )


def build_judge_system() -> str:
    """System prompt for the LLM judge. Deterministic, rubric-bound."""
    axes = "\n".join(
        f"- {name} (0-{pts}): {desc}"
        for name, pts, desc in (
            ("scope", RUBRIC_AXES["scope"],
             "Is the plan right-sized for the real change? Penalize both "
             "over-engineering (ADRs, analyzers, broad audits for a tiny fix) "
             "and under-scoping."),
            ("completeness", RUBRIC_AXES["completeness"],
             "Does the plan cover the required behavior, the required tests, "
             "and the required docs from the criteria?"),
            ("process_gates", RUBRIC_AXES["process_gates"],
             "Does the plan acknowledge the required process gates (lint, "
             "session log, mirror/sync, CI)?"),
            ("decomposition", RUBRIC_AXES["decomposition"],
             "Is the task breakdown sensible and proportional, neither a "
             "single blob nor inflated busywork?"),
            ("correct_stop", RUBRIC_AXES["correct_stop"],
             "The ask-vs-produce boundary. If ambiguous_stop_expected is "
             "true, award 1 only if the plan STOPS and asks a clarifying "
             "question instead of guessing. If false, award 1 only if the "
             "plan proceeds without stalling on a false ambiguity."),
        )
    )
    return (
        "You are a strict, impartial evaluator of engineering plans. You are "
        "given a vague request, the hidden acceptance criteria that the "
        "delivery must satisfy (derived from a real merged pull request, not "
        "shown to the agent), and the plan an agent produced. Score the plan "
        "against the criteria on these axes:\n"
        f"{axes}\n\n"
        "Judge only what the plan says, not what you assume the agent meant. "
        "Do not reward verbosity. Respond with a JSON object only, no "
        "surrounding prose:\n"
        '{"scope": <int>, "completeness": <int>, "process_gates": <int>, '
        '"decomposition": <int>, "correct_stop": <int>, '
        '"rationale": "<one or two sentences>"}'
    )


def build_judge_user_message(fixture: dict[str, Any], plan: str) -> str:
    """Assemble the judge's user turn from a fixture and an emitted plan."""
    c = fixture["hidden_criteria"]
    return (
        f"VAGUE REQUEST:\n{fixture['prompt'].strip()}\n\n"
        f"HIDDEN ACCEPTANCE CRITERIA (agent did not see these):\n"
        f"- behavior: {c['behavior']}\n"
        f"- required_tests: {c['required_tests']}\n"
        f"- required_docs: {c['required_docs']}\n"
        f"- required_gates: {c['required_gates']}\n"
        f"- ambiguous_stop_expected: {c['ambiguous_stop_expected']}\n\n"
        f"AGENT PLAN:\n{plan.strip()}\n\n"
        "Score the plan now."
    )


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Best-effort extraction of a single JSON object from model text."""
    text = raw.strip()
    if "```" in text:
        fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_judge_response(raw: str) -> dict[str, Any]:
    """Parse a judge response into a scored record.

    Returns a dict with each axis clamped to [0, axis_max], an integer
    ``total``, the ``rationale`` string, and the ``raw`` text. On a parse
    failure returns ``{"verdict": PARSE_ERROR, ...}`` with ``total`` None so
    the caller can drop the cell rather than score it as a zero.
    """
    parsed = _extract_json(raw)
    if parsed is None:
        return {"verdict": PARSE_ERROR, "total": None, "raw": raw}
    axes: dict[str, int] = {}
    for name, max_pts in RUBRIC_AXES.items():
        value = parsed.get(name, 0)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0
        axes[name] = max(0, min(max_pts, value))
    total = sum(axes.values())
    return {
        "verdict": "SCORED",
        "axes": axes,
        "total": total,
        "rationale": str(parsed.get("rationale", "")),
        "raw": raw,
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate scored run records into a comparison report.

    ``records`` are dicts with keys ``fixture_id``, ``agent``, and ``total``
    (None totals from parse errors are excluded from means). Produces per
    fixture-and-agent means, per-agent aggregate means, and per-fixture
    deltas when exactly two agents are present.
    """
    agents = sorted({r["agent"] for r in records})
    fixtures = sorted({r["fixture_id"] for r in records})

    by_cell: dict[tuple[str, str], list[float]] = {}
    for r in records:
        if r.get("total") is None:
            continue
        by_cell.setdefault((r["fixture_id"], r["agent"]), []).append(r["total"])

    per_fixture: dict[str, dict[str, Any]] = {}
    for fx in fixtures:
        row: dict[str, Any] = {}
        for agent in agents:
            row[agent] = _mean(by_cell.get((fx, agent), []))
        if len(agents) == 2:
            a0, a1 = agents
            m0, m1 = row.get(a0), row.get(a1)
            # delta is signed as (later-alphabetical minus earlier-
            # alphabetical); delta_of names the orientation so a report
            # reader never has to guess the sign.
            row["delta"] = (
                round(m1 - m0, 2) if m0 is not None and m1 is not None else None
            )
            row["delta_of"] = f"{a1} - {a0}"
        per_fixture[fx] = row

    per_agent: dict[str, float | None] = {}
    for agent in agents:
        totals = [
            t
            for (fx, ag), lst in by_cell.items()
            if ag == agent
            for t in lst
        ]
        per_agent[agent] = _mean(totals)

    parse_errors = sum(1 for r in records if r.get("total") is None)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "max_score": MAX_SCORE,
        "agents": agents,
        "fixtures": fixtures,
        "per_fixture": per_fixture,
        "per_agent_mean": per_agent,
        "parse_errors": parse_errors,
        "n_records": len(records),
    }
