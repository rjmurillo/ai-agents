"""Bounded-delegation contract checks for registered delegators (issue #5184).

``check_agent_delegation.py`` ties an agent's delegation prose to its tool
grant. This module adds the second half of the contract: every registered
delegator declares, in its frontmatter under ``metadata.delegation``, the bounds
that make its delegation verifiable.

Fields (all required, no others allowed):

- ``budget``: maximum delegations per task, an integer from 1 to
  ``MAX_DELEGATION_BUDGET``.
- ``responsibility``: one sentence naming what the delegator owns.
- ``report_schema``: field names a worker's return must carry. A list of unique
  snake_case names that includes ``REQUIRED_REPORT_FIELDS``.
- ``acceptance_owner``: who accepts or rejects a return. ``user`` or an agent
  that exists in the tree.
- ``retry_limit``: changed-context retries per failed delegation, an integer
  from 0 to ``MAX_RETRY_LIMIT``.
- ``stop_condition``: when delegation halts.
- ``escalation_owner``: who receives the task when it cannot finish. ``user`` or
  an agent that exists in the tree.

The ceilings mirror the orchestrator's own prose: 15 delegations per task and
one retry after the approach or context changes. Every "Max agent delegations
per task: N" statement in a body, outside code fences, must equal the declared
budget, so the prose and the declaration cannot drift apart.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence

CONTRACT_KEY = "delegation"

MAX_DELEGATION_BUDGET = 15
MAX_RETRY_LIMIT = 1
USER_OWNER = "user"
REQUIRED_REPORT_FIELDS = frozenset({"artifacts", "acceptance_status", "escalation_status"})

TEXT_FIELDS = ("responsibility", "stop_condition")
OWNER_FIELDS = ("acceptance_owner", "escalation_owner")
CONTRACT_FIELDS = frozenset({"budget", "report_schema", "retry_limit", *TEXT_FIELDS, *OWNER_FIELDS})

_FIELD_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_BUDGET_PROSE = re.compile(r"max\s+agent\s+delegations\s+per\s+task\W*(\d+)", re.IGNORECASE)


def prose_budgets(body: str) -> tuple[int, ...]:
    """Return every delegation cap a body states in prose, in order of appearance."""
    return tuple(int(value) for value in _BUDGET_PROSE.findall(body))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_bounded_int(contract: dict[str, object], field: str, low: int, high: int) -> list[str]:
    value = contract.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        return [f"contract field '{field}' must be an integer, got {value!r}"]
    if not low <= value <= high:
        return [f"contract field '{field}' is {value}, outside the bound {low} to {high}"]
    return []


def _check_text(contract: dict[str, object], field: str) -> list[str]:
    value = contract.get(field)
    if not isinstance(value, str) or not value.strip():
        return [f"contract field '{field}' must be a non-empty string"]
    return []


def _check_owner(contract: dict[str, object], field: str, agents: Collection[str]) -> list[str]:
    value = contract.get(field)
    if not isinstance(value, str) or not value.strip():
        return [f"contract field '{field}' must name an owner"]
    if value != USER_OWNER and value not in agents:
        return [
            f"contract field '{field}' names '{value}', "
            f"which is neither '{USER_OWNER}' nor an agent"
        ]
    return []


def _check_report_schema(contract: dict[str, object]) -> list[str]:
    schema = contract.get("report_schema")
    if not isinstance(schema, list) or not schema:
        return ["contract field 'report_schema' must be a non-empty list of field names"]
    bad = [item for item in schema if not isinstance(item, str) or not _FIELD_NAME.fullmatch(item)]
    if bad:
        return [f"contract field 'report_schema' has malformed names {bad!r} (use snake_case)"]
    if len(set(schema)) != len(schema):
        return ["contract field 'report_schema' repeats a field name"]
    missing = sorted(REQUIRED_REPORT_FIELDS - set(schema))
    if missing:
        return [f"contract field 'report_schema' lacks required field(s): {', '.join(missing)}"]
    return []


def _check_fields(contract: dict[str, object], agents: Collection[str]) -> list[str]:
    findings: list[str] = []
    findings += _check_bounded_int(contract, "budget", 1, MAX_DELEGATION_BUDGET)
    findings += _check_bounded_int(contract, "retry_limit", 0, MAX_RETRY_LIMIT)
    findings += _check_report_schema(contract)
    for field in TEXT_FIELDS:
        findings += _check_text(contract, field)
    for field in OWNER_FIELDS:
        findings += _check_owner(contract, field, agents)
    return findings


def check_contract(
    contract: object,
    agents: Collection[str],
    stated_budgets: Sequence[int] = (),
) -> list[str]:
    """Return the findings for one delegator's declared contract.

    ``contract`` is the raw ``metadata.delegation`` value, or None when absent.
    ``agents`` holds the agent names an owner may reference. ``stated_budgets``
    holds every cap the agent's body states in prose.
    """
    if contract is None:
        return [
            "registered delegator declares no bounded-delegation contract "
            f"(add metadata.{CONTRACT_KEY} with {', '.join(sorted(CONTRACT_FIELDS))})"
        ]
    if not isinstance(contract, dict):
        return [f"metadata.{CONTRACT_KEY} must be a mapping, got {type(contract).__name__}"]
    findings = [
        f"contract is missing field '{field}'" for field in sorted(CONTRACT_FIELDS - set(contract))
    ]
    findings += [
        f"contract has unknown field '{field}'"
        for field in sorted(str(key) for key in set(contract) - CONTRACT_FIELDS)
    ]
    if findings:
        return findings
    findings = _check_fields(contract, agents)
    declared = contract.get("budget")
    if _is_int(declared):
        conflicts = dict.fromkeys(value for value in stated_budgets if value != declared)
        findings += [
            f"body states a cap of {value} delegations, but the contract budget is {declared}"
            for value in conflicts
        ]
    return findings
