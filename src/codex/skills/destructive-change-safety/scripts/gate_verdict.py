#!/usr/bin/env python3
"""Fail-closed verdict over destructive-change evidence (destructive-change-safety).

Evidence is a JSON object the agent assembles from real command output:

    {
      "sinks": [{"location": "<file>:<line>", "trace": ["main", "apply_removals", "remove_worktree"]}],
      "preflight": {"command": "...", "exit_code": 0, "measured": 3},
      "expected": 3,                       # or {"max": 10}
      "rollback": {"kind": "backup", "ref": "...",
                   "backup_path": "...", "source_path": "..."},
      # snapshot needs "snapshot_path" (an existing file or non-empty directory).
      # version needs "ref" to be a 40-hex commit id that git can resolve.
      "approval": {"human": "who or ticket"},   # required when irreversible
      "checks": [{"command": "pytest ...", "exit_code": 0}]
    }

``PASS`` means every rule held and a scan report covers every sink it found.
Evidence may declare sinks the scan missed, even under a ``skip`` report. The scan
sets the minimum, and each declared sink is held to the same trace, scope, rollback,
and check rules.
``SKIP`` means no sink was declared and a scan report with ``"decision": "skip"``
proved the scan found none. Every verdict needs a scan report: a missing one, or
one without a known ``decision``, blocks, because the scan is what catches a sink
the evidence leaves out. A report that says ``activate`` yet lists no sink cannot
back a SKIP. ``BLOCK`` carries every reason. Missing evidence blocks; it never
defaults to pass.

EXIT CODES (ADR-035), through ``destructive_gate.py``:
    0 - PASS or SKIP
    1 - BLOCK
    2 - Config error: evidence is not a JSON object
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TypeGuard

Evidence = dict[str, object]
Rule = Callable[[Evidence, "list[str]"], list[str]]

SCAN_DECISIONS = {"skip", "activate", "unknown"}
ROLLBACK_KINDS = {"backup", "snapshot", "version", "irreversible"}
REFERENCED_KINDS = {"backup", "snapshot", "version"}
_COMMIT_ID = re.compile(r"[0-9a-fA-F]{40}")
_GIT_TIMEOUT_SECONDS = 30


def as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def exited_zero(entry: dict[str, object]) -> bool:
    """True only for the integer 0; JSON ``false`` equals 0 in Python and must not pass."""
    exit_code = entry.get("exit_code")
    return is_int(exit_code) and exit_code == 0


def rule_sinks_traced(evidence: Evidence, scanned: list[str]) -> list[str]:
    """Every sink needs a non-empty trace; every scanned sink needs an entry."""
    sinks = [as_dict(s) for s in as_list(evidence.get("sinks"))]
    reasons = [
        f"sink {s.get('location', '?')} has no traced path"
        for s in sinks
        if not as_list(s.get("trace"))
    ]
    declared = {str(s.get("location")) for s in sinks}
    reasons += [
        f"scanned sink {loc} is missing from evidence" for loc in scanned if loc not in declared
    ]
    return reasons


def rule_preflight(evidence: Evidence, scanned: list[str]) -> list[str]:
    """A preflight must have run, exited 0, and measured an integer scope."""
    preflight = as_dict(evidence.get("preflight"))
    if not preflight:
        return ["no preflight evidence: scope is unknown"]
    reasons = []
    if not exited_zero(preflight):
        reasons.append("preflight did not exit 0: scope is unknown")
    measured = preflight.get("measured")
    if is_int(measured) and measured < 0:
        reasons.append("preflight measured a negative count: scope is unknown")
    elif not is_int(measured):
        reasons.append("preflight measured no count: scope is unknown")
    return reasons


def rule_cardinality(evidence: Evidence, scanned: list[str]) -> list[str]:
    """The measured count must match the expected exact count or stay under max."""
    measured = as_dict(evidence.get("preflight")).get("measured")
    expected = evidence.get("expected")
    if not is_int(measured) or measured < 0:
        return []
    if is_int(expected):
        return (
            []
            if measured == expected
            else [f"unexpected cardinality: measured {measured}, expected {expected}"]
        )
    limit = as_dict(expected).get("max")
    if is_int(limit):
        return (
            []
            if measured <= limit
            else [f"unexpected cardinality: measured {measured}, max {limit}"]
        )
    return ["no expected scope declared: cardinality cannot be checked"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_reasons(rollback: dict[str, object]) -> list[str]:
    """A backup needs both paths, both files must exist, and their hashes must match."""
    backup, source = rollback.get("backup_path"), rollback.get("source_path")
    if not (backup and source):
        return ["rollback kind backup needs both backup_path and source_path to be verified"]
    backup_file, source_file = Path(str(backup)), Path(str(source))
    if not backup_file.is_file() or not source_file.is_file():
        return ["rollback backup or source file does not exist"]
    if sha256(backup_file) != sha256(source_file):
        return ["rollback backup does not match the source file"]
    return []


def snapshot_reasons(rollback: dict[str, object]) -> list[str]:
    """A snapshot must point at an existing file or a non-empty directory."""
    raw = rollback.get("snapshot_path")
    if not raw:
        return ["rollback kind snapshot needs a snapshot_path to be verified"]
    path = Path(str(raw))
    if path.is_file():
        return []
    if path.is_dir() and any(path.iterdir()):
        return []
    return ["rollback snapshot_path does not exist or is empty"]


def version_reasons(rollback: dict[str, object]) -> list[str]:
    """A version ref must be a full commit id that git resolves in the current repository."""
    ref = str(rollback.get("ref") or "")
    if not _COMMIT_ID.fullmatch(ref):
        return ["rollback kind version needs ref to be a 40-hex commit id"]
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["rollback version ref could not be checked: git did not run"]
    return (
        []
        if result.returncode == 0
        else ["rollback version ref is not a commit in this repository"]
    )


_KIND_CHECKS: dict[str, Callable[[dict[str, object]], list[str]]] = {
    "backup": backup_reasons,
    "snapshot": snapshot_reasons,
    "version": version_reasons,
}


def rule_rollback(evidence: Evidence, scanned: list[str]) -> list[str]:
    """Recovery must be stated before execution; irreversible needs a human."""
    rollback = as_dict(evidence.get("rollback"))
    kind = rollback.get("kind")
    if kind not in ROLLBACK_KINDS:
        return ["no rollback contract: state backup, snapshot, version, or irreversible"]
    if kind == "irreversible":
        approved = as_dict(evidence.get("approval")).get("human")
        return [] if approved else ["irreversible operation needs human approval"]
    reasons = [] if rollback.get("ref") else [f"rollback kind {kind} names no ref"]
    return reasons + _KIND_CHECKS[str(kind)](rollback)


def rule_checks(evidence: Evidence, scanned: list[str]) -> list[str]:
    """At least one check ran, and every check exited 0."""
    checks = [as_dict(c) for c in as_list(evidence.get("checks"))]
    if not checks:
        return ["no verification checks recorded"]
    return [f"check failed: {c.get('command', '?')}" for c in checks if not exited_zero(c)]


RULES: tuple[Rule, ...] = (
    rule_sinks_traced,
    rule_preflight,
    rule_cardinality,
    rule_rollback,
    rule_checks,
)


def evaluate(evidence: Evidence, scan_report: Evidence | None = None) -> dict[str, object]:
    """Return ``{"verdict", "reasons"}`` for the evidence and its scan report (None blocks)."""
    if scan_report is None:
        return {
            "verdict": "BLOCK",
            "reasons": ["no scan report: run `scan` and pass --scan to prove which sinks exist"],
        }
    scanned = [str(as_dict(s).get("location")) for s in as_list(scan_report.get("sinks"))]
    if scan_report.get("decision") not in SCAN_DECISIONS:
        return {
            "verdict": "BLOCK",
            "reasons": ["scan report has no known `decision` (skip, activate, or unknown)"],
        }
    if scan_report.get("decision") == "unknown":
        return {
            "verdict": "BLOCK",
            "reasons": ["scan could not parse or cover every file: scope is unknown"],
        }
    if "sinks" in scan_report and not isinstance(scan_report["sinks"], list):
        return {"verdict": "BLOCK", "reasons": ["scan report `sinks` must be a list"]}
    if "sinks" in evidence and not isinstance(evidence["sinks"], list):
        return {"verdict": "BLOCK", "reasons": ["evidence `sinks` must be a list"]}
    if not as_list(evidence.get("sinks")) and not scanned:
        if scan_report.get("decision") != "skip":
            return {
                "verdict": "BLOCK",
                "reasons": ["scan decision `activate` lists no sink: the report is inconsistent"],
            }
        return {"verdict": "SKIP", "reasons": ["no destructive sink declared or scanned"]}
    reasons = [reason for rule in RULES for reason in rule(evidence, scanned)]
    return {"verdict": "BLOCK" if reasons else "PASS", "reasons": reasons}
