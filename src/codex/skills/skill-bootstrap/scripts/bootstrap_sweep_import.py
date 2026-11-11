"""Seeds from a bootstrap_sweep.py tally for bootstrap_mine --sweep-json.

Only keys, counts, and enums cross into candidates: no summary, target, or rationale text.
Stricter than canonical: the enums below mirror bootstrap_sweep.py, and
tests/skills/skill-bootstrap/test_mine_sweep.py fails if the two drift.
"""

from __future__ import annotations

import re
from typing import Any

from bootstrap_friction import (
    Payload,
    _count,
    _list,
    _object,
    _read,
    _require,
    _seed,
)

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Mirrors the enums in bootstrap_sweep.py; test_mine_sweep.py fails if the two drift.
SWEEP_TYPES = (
    "knowledge-gap",
    "human-agent",
    "agent-process",
    "agent-tool",
    "agent-agent",
    "human-process",
    "human-tool",
    "human-human",
)
SWEEP_PATTERNS = (
    "fragmented-context",
    "inconsistent-linking",
    "incomplete-evidence",
    "surface-switching",
    "review-gate-latency",
    "work-item-drift",
    "shadow-work",
    "lagging-indicator",
    "access-barrier",
    "oversized-change",
    "unclear-ownership",
    "missing-context",
    "unstable-checks",
    "other",
)
SWEEP_CLASSES = (
    "code_review",
    "work_tracking",
    "chat",
    "email",
    "documents",
    "meetings",
    "build_ops",
    "memory",
    "work_intelligence",
    "agent_sessions",
    "other",
)
SWEEP_ACTIONS = (
    "create-skill",
    "update-skill",
    "write-doc",
    "add-instrument",
    "fix-process",
    "ask-owner",
)
SWEEP_CORROBORATION = ("classes", "threads", "repo_path")
SWEEP_INCIDENT_KEYS = frozenset(
    {
        "incident",
        "primary_type",
        "types",
        "patterns",
        "evidence",
        "locators",
        "threads",
        "classes",
        "judges",
        "people",
        "repo_paths",
        "corroborated",
        "corroboration",
        "suggestions",
        "findings",
        "summary",
    }
)


def _hex_id(value: Any) -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        raise ValueError("sweep ids must be sha256")
    return value


def _members(value: Any, allowed: tuple[str, ...]) -> list[str]:
    items = _list(value)
    _require(all(isinstance(i, str) and i in allowed for i in items), "unsupported sweep enum")
    return items


def _counts(value: Any, allowed: tuple[str, ...]) -> Payload:
    counts = _object(value)
    _require(set(counts) <= set(allowed), "unsupported sweep enum key")
    for count in counts.values():
        _require(_count(count) >= 1, "sweep counts must be positive")
    return counts


def _sweep_incident(value: Any) -> Payload:
    inc = _object(value)
    _require(set(inc) == SWEEP_INCIDENT_KEYS, "sweep incident has unexpected keys")
    _require(inc["primary_type"] in SWEEP_TYPES, "unsupported sweep primary_type")
    types = _counts(inc["types"], SWEEP_TYPES)
    _require(inc["primary_type"] in types, "primary_type is not among types")
    evidence = _list(inc["evidence"])
    _require(bool(evidence) and len(set(evidence)) == len(evidence), "bad sweep evidence ids")
    _require(all(isinstance(e, str) and e for e in evidence), "bad sweep evidence ids")
    _require(type(inc["corroborated"]) is bool, "corroborated must be boolean")
    reasons = _members(inc["corroboration"], SWEEP_CORROBORATION)
    _require(inc["corroborated"] == bool(reasons), "corroborated disagrees with corroboration")
    _require(
        isinstance(inc["incident"], str) and bool(KEBAB_RE.match(inc["incident"])),
        "bad incident key",
    )
    suggestions = [_object(s) for s in _list(inc["suggestions"])]
    found = {str(s.get("action")) for s in suggestions}
    _require(found <= set(SWEEP_ACTIONS), "unsupported sweep action")
    actions = sorted(found)
    return {
        "evidence": evidence,
        "corroborated": inc["corroborated"],
        "corroboration": reasons,
        "primary_type": inc["primary_type"],
        "patterns": _counts(inc["patterns"], SWEEP_PATTERNS),
        "classes": _members(inc["classes"], SWEEP_CLASSES),
        "suggestion_actions": actions,
        "incident": inc["incident"],
    }


def read_sweep(path: str) -> tuple[list[Payload], Payload, int]:
    data, provenance = _read(path)
    _require(
        type(data.get("schema_version")) is int and data["schema_version"] == 1,
        "unsupported sweep schema_version",
    )
    index_id, plan_id = _hex_id(data.get("index_id")), _hex_id(data.get("plan_id"))
    for key in ("coverage", "knowledge_gaps", "incomplete", "single_reader"):
        _list(data.get(key))
    incidents = [_sweep_incident(v) for v in _list(data.get("incidents"))]
    _require(len({i["incident"] for i in incidents}) == len(incidents), "duplicate sweep incident")
    rows = []
    for position, inc in enumerate(incidents):
        source = {**provenance, "locator": f"/incidents/{position}"}
        row = _seed(
            ["cross_source_incident", index_id, inc["incident"]],
            "evidence_items",
            len(inc["evidence"]),
            source,
        )
        row.update({k: v for k, v in inc.items() if k not in ("incident", "evidence")})
        rows.append(row)
    metadata = {
        "schema_version": 1,
        "index_id": index_id,
        "plan_id": plan_id,
        "incomplete": len(data["incomplete"]),
        "single_reader": len(data["single_reader"]),
    }
    return rows, {**provenance, "metadata": metadata}, len(incidents)
