#!/usr/bin/env python3
"""Classify evidence lineage so a second artifact is not counted as a second proof.

Reads one JSON record of a claim, the artifact under test, and the evidence
offered for it. Groups evidence into loops by shared premise or inheritance,
decides which items are independent of the artifact's own loop, and keeps
authority as a separate axis. It also enforces the Walk-or-Don't-Name rule:
a named check carries one of VERIFIED, NOT RUN, UNAVAILABLE, or FAILED.

Input shape (all keys optional unless marked):
    claim              free text
    subject            {artifact, revision, premises: [..]}   (required)
    claimed_independent integer count the author asserts
    evidence           [{id*, state*, origin, created, authority, environment,
                         premises, inherits_from, changed_by_subject,
                         discriminating, used_as_support, bound_to}]
    checks             [{check*, state, cheap, available, used_as_support}]

`premises` absent or empty on an item means its lineage is unknown, and unknown
lineage never counts as independent.

EXIT CODES (ADR-035):
    0 - Success: classification computed, no violation, claim not falsified
    1 - Logic error: a violation, a FAILED item, or independent falsification
    2 - Config error: unreadable JSON, unknown enum value, missing field
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATES = ("VERIFIED", "NOT RUN", "UNAVAILABLE", "FAILED")
ORIGINS = ("same-loop", "independent-reviewer", "human", "external-system", "pre-existing")
CREATED = ("pre-existing", "during-task")
AUTHORITIES = ("normative", "executable-runtime", "derived", "heuristic")
ENVIRONMENTS = ("synthetic", "real")
AUTHORITATIVE = ("normative", "executable-runtime")
BINDING_KEYS = ("artifact", "revision", "validator", "command", "result")


JsonObject = dict[str, Any]


class ConfigError(Exception):
    """The input record is unusable."""


@dataclass
class Item:
    """One piece of evidence with its lineage fields."""

    id: str
    state: str
    origin: str = "same-loop"
    created: str = "during-task"
    authority: str = "heuristic"
    environment: str = "synthetic"
    premises: list[str] | None = None
    inherits_from: list[str] = field(default_factory=list)
    changed_by_subject: bool = False
    discriminating: bool = False
    used_as_support: bool = False
    bound_to: dict[str, Any] | None = None
    inherits_rejected: bool = False


def pick(raw: JsonObject, key: str, allowed: tuple[str, ...], default: str) -> str:
    value = raw.get(key, default)
    if value not in allowed:
        raise ConfigError(f"{key} must be one of {list(allowed)}, got {value!r}")
    return str(value)


def str_list(raw: dict[str, Any], key: str) -> list[str]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} must be a list of strings")
    return list(value)


def parse_premises(raw: dict[str, Any]) -> list[str] | None:
    if "premises" not in raw:
        return None
    return str_list(raw, "premises")


def parse_item(raw: object) -> Item:
    if not isinstance(raw, dict):
        raise ConfigError("each evidence entry must be an object")
    if not isinstance(raw.get("id"), str) or not raw["id"]:
        raise ConfigError("each evidence entry needs a string id")
    bound = raw.get("bound_to")
    if bound is not None and not isinstance(bound, dict):
        raise ConfigError("bound_to must be an object")
    return Item(
        id=raw["id"],
        state=pick(raw, "state", STATES, ""),
        origin=pick(raw, "origin", ORIGINS, "same-loop"),
        created=pick(raw, "created", CREATED, "during-task"),
        authority=pick(raw, "authority", AUTHORITIES, "heuristic"),
        environment=pick(raw, "environment", ENVIRONMENTS, "synthetic"),
        premises=parse_premises(raw),
        inherits_from=str_list(raw, "inherits_from"),
        changed_by_subject=bool(raw.get("changed_by_subject", False)),
        discriminating=bool(raw.get("discriminating", False)),
        used_as_support=bool(raw.get("used_as_support", False)),
        bound_to=bound,
    )


def parse_items(record: dict[str, Any]) -> list[Item]:
    raw_items = record.get("evidence", [])
    if not isinstance(raw_items, list):
        raise ConfigError("evidence must be a list")
    items = [parse_item(raw) for raw in raw_items]
    ids = [item.id for item in items]
    if "subject" in ids:
        raise ConfigError("'subject' is reserved and cannot be an evidence id")
    if len(set(ids)) != len(ids):
        raise ConfigError("evidence ids must be unique")
    unknown = {ref for item in items for ref in item.inherits_from} - set(ids) - {"subject"}
    if unknown:
        raise ConfigError(f"inherits_from names unknown ids: {sorted(unknown)}")
    return items


def parse_subject(record: dict[str, Any]) -> dict[str, Any]:
    subject = record.get("subject")
    if not isinstance(subject, dict):
        raise ConfigError("subject is required and must be an object")
    return {
        "artifact": subject.get("artifact"),
        "revision": subject.get("revision"),
        "premises": str_list(subject, "premises"),
    }


def binding_problem(item: Item, subject: dict[str, Any], promotion: bool) -> str | None:
    """Return why an item cannot speak for this artifact revision, or None."""
    bound = item.bound_to
    if bound is None:
        return "binding-missing" if promotion else None
    if promotion and any(not bound.get(key) for key in BINDING_KEYS):
        return "binding-missing"
    if bound.get("artifact") not in (None, subject["artifact"]):
        return "binding-mismatch"
    if bound.get("revision") not in (None, subject["revision"]):
        return "binding-mismatch"
    return None


class LoopMap:
    """Union-find over the subject and the accepted evidence ids."""

    def __init__(self, names: list[str]) -> None:
        self.parent = {name: name for name in names}

    def find(self, name: str) -> str:
        while self.parent[name] != name:
            self.parent[name] = self.parent[self.parent[name]]
            name = self.parent[name]
        return name

    def union(self, left: str, right: str) -> None:
        self.parent[self.find(left)] = self.find(right)


def link_item(loops: LoopMap, owners: dict[str, str], item: Item) -> None:
    """Join an item to every loop it shares a premise with or inherits from."""
    for premise in item.premises or []:
        loops.union(item.id, owners.setdefault(premise, item.id))
    known = [ref for ref in item.inherits_from if ref in loops.parent]
    for ref in known:
        loops.union(item.id, ref)


def build_loops(subject: dict[str, Any], items: list[Item]) -> LoopMap:
    loops = LoopMap(["subject", *[item.id for item in items]])
    owners = {premise: "subject" for premise in subject["premises"]}
    for item in items:
        link_item(loops, owners, item)
    return loops


def mark_rejected_inheritance(items: list[Item], rejected_ids: set[str]) -> None:
    """Flag every item that inherits, directly or through a chain, from a rejected item."""
    tainted = set(rejected_ids)
    changed = True
    while changed:
        changed = False
        for item in items:
            if item.id not in tainted and tainted.intersection(item.inherits_from):
                tainted.add(item.id)
                item.inherits_rejected = True
                changed = True


def independence_reasons(item: Item, in_subject_loop: bool) -> list[str]:
    reasons = []
    if item.inherits_rejected:
        reasons.append("inherits-rejected-evidence")
    if not item.premises:
        reasons.append("lineage-missing")
    if in_subject_loop:
        reasons.append("shares-subject-loop")
    if item.changed_by_subject:
        reasons.append("changed-by-subject")
    synthetic_self = item.origin == "same-loop" and item.created != "pre-existing"
    if synthetic_self and item.environment != "real":
        reasons.append("same-origin-synthetic")
    return reasons


def describe(item: Item, loops: LoopMap, labels: dict[str, str]) -> dict[str, Any]:
    in_subject = loops.find(item.id) == loops.find("subject")
    reasons = independence_reasons(item, in_subject)
    return {
        "id": item.id,
        "state": item.state,
        "loop": labels[loops.find(item.id)],
        "independent": not reasons,
        "not_independent_because": reasons,
        "authority": item.authority,
        "authoritative": item.authority in AUTHORITATIVE,
        "discriminating": item.discriminating,
    }


def loop_labels(loops: LoopMap, items: list[Item]) -> dict[str, str]:
    labels = {loops.find("subject"): "L0-subject"}
    for item in items:
        root = loops.find(item.id)
        labels.setdefault(root, f"L{len(labels)}")
    return labels


def verdict_for(rows: list[dict[str, Any]]) -> str:
    independent = [r for r in rows if r["independent"]]
    falsifiers = [r for r in independent if r["state"] == "FAILED" and r["authoritative"]]
    if falsifiers:
        return "FALSIFIED_BY_INDEPENDENT_OBSERVATION"
    if any(r["state"] == "FAILED" for r in rows):
        return "FAILED"
    if any(r["independent"] and r["state"] == "VERIFIED" for r in rows):
        return "CORROBORATED"
    if any(r["state"] == "VERIFIED" for r in rows):
        return "SINGLE_LOOP"
    return "NO_VERIFIED_EVIDENCE"


def count_loops(rows: list[dict[str, Any]], authoritative_only: bool) -> int:
    loops = {
        r["loop"]
        for r in rows
        if r["independent"]
        and r["state"] == "VERIFIED"
        and (r["authoritative"] or not authoritative_only)
    }
    return len(loops)


def check_violations(record: dict[str, Any], items: list[Item]) -> list[dict[str, str]]:
    found = []
    for item in items:
        if item.used_as_support and item.state != "VERIFIED":
            found.append({"rule": "unverified-support", "subject": item.id})
    checks = record.get("checks", [])
    if not isinstance(checks, list):
        raise ConfigError("checks must be a list")
    for check in checks:
        found.extend(check_violation(check))
    return found


def check_violation(check: object) -> list[dict[str, str]]:
    if not isinstance(check, dict) or not isinstance(check.get("check"), str):
        raise ConfigError("each check needs a string 'check' name")
    name = check["check"]
    state = check.get("state")
    if state not in STATES:
        return [{"rule": "named-without-state", "subject": name}]
    if check.get("used_as_support") and state != "VERIFIED":
        return [{"rule": "unverified-support", "subject": name}]
    return []


def warnings_for(record: dict[str, Any]) -> list[dict[str, str]]:
    checks = record.get("checks", [])
    return [
        {"rule": "cheap-gate-not-run", "subject": str(c["check"])}
        for c in checks
        if isinstance(c, dict)
        and c.get("state") == "NOT RUN"
        and c.get("cheap")
        and c.get("available")
    ]


def classify(record: dict[str, Any], promotion: bool) -> dict[str, Any]:
    subject = parse_subject(record)
    every = parse_items(record)
    problems = {item.id: binding_problem(item, subject, promotion) for item in every}
    items = [item for item in every if not problems[item.id]]
    rejected = [{"id": i.id, "reason": problems[i.id]} for i in every if problems[i.id]]
    mark_rejected_inheritance(items, {key for key, why in problems.items() if why})
    loops = build_loops(subject, items)
    labels = loop_labels(loops, items)
    rows = [describe(item, loops, labels) for item in items]
    violations = check_violations(record, every)
    independent_loops = count_loops(rows, authoritative_only=False)
    claimed = record.get("claimed_independent")
    if isinstance(claimed, int) and claimed > independent_loops:
        violations.append(
            {"rule": "inflated-confidence", "subject": f"{claimed}>{independent_loops}"}
        )
    return {
        "claim": record.get("claim", ""),
        "verdict": verdict_for(rows),
        "independent_loops": independent_loops,
        "authoritative_independent_loops": count_loops(rows, authoritative_only=True),
        "evidence": rows,
        "rejected": rejected,
        "violations": violations,
        "warnings": warnings_for(record),
    }


def exit_code(report: dict[str, Any]) -> int:
    bad_verdicts = ("FAILED", "FALSIFIED_BY_INDEPENDENT_OBSERVATION")
    return 1 if report["violations"] or report["verdict"] in bad_verdicts else 0


def load(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"cannot read JSON from {path}: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("record", help="JSON evidence record")
    parser.add_argument(
        "--promotion",
        action="store_true",
        help="require artifact, revision, validator, command, and result on every item",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = classify(load(args.record), args.promotion)
    except ConfigError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
