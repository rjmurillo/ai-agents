"""Single source of truth for the session-log JSON structure (Issue #2591).

Both `new_session_log.py` and `new_session_log_json.py` build the same session
JSON. Before this module, each generator hardcoded the `protocolCompliance`
block and top-level shape independently, so every schema change (for example
the `schemaVersion` and trailing-newline fixes in #2537 / PR #2588) had to be
made twice or the two outputs silently drifted.

The required-field set is the generator's copy of the protocol keys consumed by
`scripts/validate_session_json.py`, which remains the authoritative checker.
"""

from __future__ import annotations

from typing import Any


def _must(complete: bool, evidence: str) -> dict[str, Any]:
    return {"level": "MUST", "Complete": complete, "Evidence": evidence}


def _should(complete: bool, evidence: str) -> dict[str, Any]:
    return {"level": "SHOULD", "Complete": complete, "Evidence": evidence}


def _build_protocol_compliance(branch: str, commit: str) -> dict[str, Any]:
    not_on_main = branch not in ("main", "master")
    return {
        "sessionStart": {
            "serenaActivated": _must(False, ""),
            "serenaInstructions": _must(False, ""),
            "handoffRead": _must(False, ""),
            "sessionLogCreated": _must(True, "This file"),
            "skillScriptsListed": _must(False, ""),
            "usageMandatoryRead": _must(False, ""),
            "constraintsRead": _must(False, ""),
            "memoriesLoaded": _must(False, ""),
            "branchVerified": _must(True, branch),
            "notOnMain": _must(not_on_main, f"On {branch}"),
            "gitStatusVerified": _should(False, ""),
            "startingCommitNoted": _should(True, commit),
        },
        "sessionEnd": {
            "checklistComplete": _must(False, ""),
            "handoffPreserved": _must(False, ""),
            "serenaMemoryUpdated": _must(False, ""),
            "markdownLintRun": _must(False, ""),
            "changesCommitted": _must(False, ""),
            "validationPassed": _must(False, ""),
            "tasksUpdated": _should(False, ""),
            "retrospectiveInvoked": _should(False, ""),
        },
    }


def build_session_log(
    *,
    branch: str,
    commit: str,
    session_number: int,
    objective: str,
    current_date: str,
    schema_version: str = "1.0",
    trace_id: str = "",
    parent_session_id: str = "",
) -> dict[str, Any]:
    """Build the protocol-compliant session-log JSON structure.

    `trace_id` and `parent_session_id` are optional multi-agent correlation
    fields; they are added to the session metadata only when non-empty.
    """
    session_metadata: dict[str, Any] = {
        "number": session_number,
        "date": current_date,
        "branch": branch,
        "startingCommit": commit,
        "objective": objective or "[TODO: Describe objective]",
    }
    if trace_id:
        session_metadata["traceId"] = trace_id
    if parent_session_id:
        session_metadata["parentSessionId"] = parent_session_id

    return {
        "schemaVersion": schema_version,
        "session": session_metadata,
        "protocolCompliance": _build_protocol_compliance(branch, commit),
        "workLog": [],
        "endingCommit": "",
        "nextSteps": [],
    }
