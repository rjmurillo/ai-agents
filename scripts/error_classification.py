"""Error classification and recovery hint system.

Classifies tool execution failures into a taxonomy aligned with ADR-035
exit codes. Provides recovery hints from a YAML configuration file.

Exit Codes (ADR-035):
    0 = success
    1 = logic/validation error
    2 = configuration error
    3 = external service error
    4 = authentication error
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ErrorType(enum.Enum):
    """Error taxonomy aligned with ADR-035 exit codes."""

    TOOL_FAILURE = "tool_failure"
    REASONING_DRIFT = "reasoning_drift"
    INFINITE_LOOP = "infinite_loop"
    SCOPE_CREEP = "scope_creep"
    CONTEXT_OVERFLOW = "context_overflow"


# Map ADR-035 exit codes to error types where deterministic.
_EXIT_CODE_MAP: dict[int, ErrorType] = {
    2: ErrorType.TOOL_FAILURE,  # config error
    3: ErrorType.TOOL_FAILURE,  # external service error
    4: ErrorType.TOOL_FAILURE,  # auth error
}

# Patterns indicating transient / retriable failures.
_TRANSIENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rate limit", re.IGNORECASE),
    re.compile(r"HTTP 429", re.IGNORECASE),
    re.compile(r"HTTP 503", re.IGNORECASE),
    re.compile(r"ETIMEDOUT", re.IGNORECASE),
    re.compile(r"ECONNRESET", re.IGNORECASE),
]


@dataclass(frozen=True)
class RecoveryHint:
    """A single recovery hint for a failure pattern."""

    pattern: str
    hint: str
    compiled_pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "compiled_pattern",
            re.compile(self.pattern, re.IGNORECASE),
        )


@dataclass(frozen=True)
class ClassifiedError:
    """Result of classifying a tool execution failure."""

    error_type: ErrorType
    tool_name: str
    exit_code: int
    stderr: str
    is_transient: bool
    recovery_hints: tuple[str, ...]


def _is_transient(stderr: str) -> bool:
    """Return True if stderr matches a known transient failure pattern."""
    return any(p.search(stderr) for p in _TRANSIENT_PATTERNS)


def load_recovery_hints(
    hints_path: Path | None = None,
) -> dict[str, list[RecoveryHint]]:
    """Load recovery hints from YAML.

    Args:
        hints_path: Path to recovery-hints.yaml. Defaults to
            .agents/recovery-hints.yaml relative to the repo root.

    Returns:
        Dict mapping section names to lists of RecoveryHint objects.
    """
    if hints_path is None:
        hints_path = Path(__file__).resolve().parents[1] / ".agents" / "recovery-hints.yaml"

    if not hints_path.is_file():
        return {}

    raw: dict[str, Any] = yaml.safe_load(hints_path.read_text(encoding="utf-8")) or {}
    result: dict[str, list[RecoveryHint]] = {}

    for section, entries in raw.items():
        if not isinstance(entries, list):
            continue
        hints: list[RecoveryHint] = []
        for entry in entries:
            if isinstance(entry, dict) and "pattern" in entry and "hint" in entry:
                hints.append(RecoveryHint(pattern=entry["pattern"], hint=entry["hint"]))
        if hints:
            result[section] = hints

    return result


def _match_hints(
    stderr: str,
    tool_name: str,
    hints_db: dict[str, list[RecoveryHint]],
) -> tuple[str, ...]:
    """Return matching recovery hints for the given failure."""
    matched: list[str] = []

    # Check tool-specific hints first.
    tool_hints = hints_db.get(f"tool_{tool_name}", [])
    for rh in tool_hints:
        if rh.compiled_pattern.search(stderr):
            matched.append(rh.hint)

    # Check general hints.
    for rh in hints_db.get("general", []):
        if rh.compiled_pattern.search(stderr):
            matched.append(rh.hint)

    return tuple(matched)


def classify_error(
    tool_name: str,
    exit_code: int,
    stderr: str,
    *,
    call_history: list[str] | None = None,
    hints_db: dict[str, list[RecoveryHint]] | None = None,
) -> ClassifiedError:
    """Classify a tool execution failure.

    Args:
        tool_name: Name of the tool that failed.
        exit_code: Process exit code.
        stderr: Standard error output.
        call_history: Recent tool call names for loop detection.
        hints_db: Pre-loaded recovery hints. Loaded from disk if None.

    Returns:
        ClassifiedError with type, transient flag, and recovery hints.
    """
    if hints_db is None:
        hints_db = load_recovery_hints()

    # Loop detection: 3+ consecutive identical calls.
    if call_history and len(call_history) >= 3:
        last_three = call_history[-3:]
        if len(set(last_three)) == 1 and last_three[0] == tool_name:
            return ClassifiedError(
                error_type=ErrorType.INFINITE_LOOP,
                tool_name=tool_name,
                exit_code=exit_code,
                stderr=stderr,
                is_transient=False,
                recovery_hints=(
                    "Loop detected: same tool called 3+ times. "
                    "Break the loop, summarize progress, try a different approach.",
                ),
            )

    # Exit code mapping.
    error_type = _EXIT_CODE_MAP.get(exit_code, ErrorType.TOOL_FAILURE)

    transient = _is_transient(stderr)
    hints = _match_hints(stderr, tool_name, hints_db)

    return ClassifiedError(
        error_type=error_type,
        tool_name=tool_name,
        exit_code=exit_code,
        stderr=stderr,
        is_transient=transient,
        recovery_hints=hints,
    )
