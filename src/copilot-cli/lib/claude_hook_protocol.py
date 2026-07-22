"""Strict Claude Code hook-output classification for grouped dispatch."""

from __future__ import annotations

import json

_DECISION_KEYS = frozenset({"decision", "continue", "permissionDecision"})
_TOP_LEVEL_COMMON_KEYS = frozenset({"suppressOutput", "systemMessage"})
_STOP_DECISION_EVENTS = frozenset({"Stop", "SubagentStop"})


def _has_valid_common_fields(doc: dict[str, object]) -> bool:
    """Return whether optional top-level Claude fields have valid types."""
    if "suppressOutput" in doc and not isinstance(doc["suppressOutput"], bool):
        return False
    return "systemMessage" not in doc or isinstance(doc["systemMessage"], str)


def _is_valid_continue_block(doc: dict[str, object]) -> bool:
    allowed = _TOP_LEVEL_COMMON_KEYS | {"continue", "stopReason"}
    return (
        set(doc) <= allowed
        and doc.get("continue") is False
        and ("stopReason" not in doc or isinstance(doc["stopReason"], str))
    )


def _is_valid_stop_block(doc: dict[str, object], event: str) -> bool:
    allowed = _TOP_LEVEL_COMMON_KEYS | {"decision", "reason"}
    return (
        event in _STOP_DECISION_EVENTS
        and set(doc) <= allowed
        and doc.get("decision") == "block"
        and isinstance(doc.get("reason"), str)
    )


def _is_valid_pretooluse_block(doc: dict[str, object], event: str) -> bool:
    hso = doc.get("hookSpecificOutput")
    if not isinstance(hso, dict):
        return False
    allowed_top = _TOP_LEVEL_COMMON_KEYS | {"hookSpecificOutput"}
    allowed_hso = {
        "hookEventName",
        "permissionDecision",
        "permissionDecisionReason",
        "additionalContext",
    }
    return (
        event == "PreToolUse"
        and set(doc) <= allowed_top
        and set(hso) <= allowed_hso
        and hso.get("hookEventName") == "PreToolUse"
        and hso.get("permissionDecision") == "deny"
        and isinstance(hso.get("permissionDecisionReason"), str)
        and (
            "additionalContext" not in hso
            or isinstance(hso["additionalContext"], str)
        )
    )


def _is_valid_blocking_document(doc: dict[str, object], event: str) -> bool:
    """Return whether ``doc`` is a strict blocking output for ``event``."""
    if not _has_valid_common_fields(doc):
        return False
    if "continue" in doc:
        return _is_valid_continue_block(doc)
    if "decision" in doc:
        return _is_valid_stop_block(doc, event)
    return _is_valid_pretooluse_block(doc, event)


def _classify_hook_specific_output(
    doc: dict[str, object],
    event: str,
    stripped: str,
) -> tuple[str | None, str | None, bool] | None:
    hso = doc.get("hookSpecificOutput")
    if "hookSpecificOutput" in doc and not isinstance(hso, dict):
        return None, stripped, False
    if not isinstance(hso, dict):
        return None
    extra_keys = set(hso) - {"hookEventName", "additionalContext"}
    top_keys = set(doc) - {"hookSpecificOutput", "suppressOutput", "systemMessage"}
    if extra_keys or top_keys:
        return None, stripped, _is_valid_blocking_document(doc, event)
    if hso.get("hookEventName") != event:
        return None, stripped, False
    context = hso.get("additionalContext")
    if "additionalContext" in hso and not isinstance(context, str):
        return None, stripped, False
    if isinstance(context, str) and context.strip():
        return context, None, True
    return None, None, True


def _classify_advisory_output(
    doc: dict[str, object],
) -> tuple[str | None, str | None, bool] | None:
    if not set(doc) <= {"systemMessage", "suppressOutput"}:
        return None
    message = doc.get("systemMessage")
    if isinstance(message, str) and message.strip():
        return message, None, True
    return None, None, True


def _classify_stdout(text: str, event: str) -> tuple[str | None, str | None, bool]:
    """Return ``(context, decision, recognized)`` for one shim's stdout."""
    stripped = text.strip()
    if not stripped:
        return None, None, True
    try:
        doc = json.loads(stripped)
    except ValueError:
        if stripped.startswith("{"):
            return None, stripped, False
        return stripped, None, True
    if not isinstance(doc, dict):
        return stripped, None, True
    if not _has_valid_common_fields(doc):
        return None, stripped, False
    if _DECISION_KEYS & doc.keys():
        return None, stripped, _is_valid_blocking_document(doc, event)
    classified = _classify_hook_specific_output(doc, event, stripped)
    if classified is not None:
        return classified
    advisory = _classify_advisory_output(doc)
    if advisory is not None:
        return advisory
    return stripped, None, False
