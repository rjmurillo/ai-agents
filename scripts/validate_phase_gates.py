#!/usr/bin/env python3
"""Validate SPARC development phase gates in session logs.

Checks that phase transitions in session logs satisfy gate criteria.
Phase gates enforce structured progression through development phases.

EXIT CODES:
  0  - Success: All phase gates valid (or no phase tracking present)
  1  - Error: Phase gate validation failed
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
See: .agents/governance/sparc-methodology.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402
from scripts.validation.types import ValidationResult  # noqa: E402

VALID_PHASES = frozenset({
    "specification",
    "pseudocode",
    "architecture",
    "refinement",
    "completion",
})

PHASE_ORDER = [
    "specification",
    "pseudocode",
    "architecture",
    "refinement",
    "completion",
]

VALID_GATE_STATUSES = frozenset({"passed", "failed", "in_progress", "skipped"})

# Phases that allow skipping earlier phases (entry points)
VALID_ENTRY_PHASES = frozenset({
    "specification",   # Full methodology
    "architecture",    # Architecture-focused work
    "refinement",      # Quick fixes
    "completion",      # Documentation only
})


def validate_phase_data(phase_data: dict[str, Any]) -> ValidationResult:
    """Validate the developmentPhase object in a session log.

    Args:
        phase_data: The developmentPhase dictionary from the session log.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()

    current = phase_data.get("current")
    if current is None:
        result.errors.append("developmentPhase.current is required")
        return result

    if current not in VALID_PHASES:
        result.errors.append(
            f"Invalid phase '{current}'. Valid phases: {sorted(VALID_PHASES)}"
        )
        return result

    history = phase_data.get("history", [])
    if not isinstance(history, list):
        result.errors.append("developmentPhase.history must be an array")
        return result

    _validate_history(history, current, result)
    return result


def _validate_history(
    history: list[dict[str, Any]],
    current: str,
    result: ValidationResult,
) -> None:
    """Validate phase transition history.

    Checks ordering, valid statuses, and consistency with current phase.
    """
    if not history:
        return

    previous_index = -1

    for i, entry in enumerate(history):
        phase = entry.get("phase")
        gate = entry.get("gate")

        if phase is None:
            result.errors.append(f"history[{i}]: missing 'phase' field")
            continue

        if phase not in VALID_PHASES:
            result.errors.append(
                f"history[{i}]: invalid phase '{phase}'"
            )
            continue

        if gate is not None and gate not in VALID_GATE_STATUSES:
            result.errors.append(
                f"history[{i}]: invalid gate status '{gate}'. "
                f"Valid: {sorted(VALID_GATE_STATUSES)}"
            )

        current_index = PHASE_ORDER.index(phase)

        # First entry must be a valid entry phase
        if i == 0 and phase not in VALID_ENTRY_PHASES:
            result.warnings.append(
                f"history[{i}]: phase '{phase}' is not a standard entry phase"
            )

        # Phases must not go backwards
        if current_index < previous_index:
            result.errors.append(
                f"history[{i}]: phase '{phase}' is before "
                f"previous phase '{PHASE_ORDER[previous_index]}'. "
                "Phases must progress forward."
            )

        # Gate must be 'passed' before next phase (except last entry)
        if i > 0 and i < len(history):
            prev_gate = history[i - 1].get("gate")
            if prev_gate == "failed":
                result.warnings.append(
                    f"history[{i}]: entered '{phase}' after "
                    f"previous gate was 'failed'"
                )

        previous_index = current_index

    # Last history entry should match current phase
    if history:
        last_phase = history[-1].get("phase")
        if last_phase != current:
            result.warnings.append(
                f"Last history phase '{last_phase}' does not match "
                f"current phase '{current}'"
            )


def validate_session_file(file_path: Path) -> ValidationResult:
    """Validate phase gates in a session log file.

    Args:
        file_path: Path to session log JSON file.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.errors.append(f"Invalid JSON: {e}")
        return result
    except OSError as e:
        result.errors.append(f"Cannot read file: {e}")
        return result

    phase_data = data.get("developmentPhase")
    if phase_data is None:
        # Phase tracking is optional. No errors if absent.
        return result

    if not isinstance(phase_data, dict):
        result.errors.append("developmentPhase must be an object")
        return result

    return validate_phase_data(phase_data)


def main() -> int:
    """Run phase gate validation.

    Returns:
        Exit code: 0 for success, 1 for validation failure, 2 for unexpected error.
    """
    parser = argparse.ArgumentParser(
        description="Validate SPARC phase gates in session logs",
    )
    parser.add_argument(
        "session_log",
        help="Path to session log JSON file",
    )
    args = parser.parse_args()

    try:
        safe_path = validate_safe_path(args.session_log, _PROJECT_ROOT)
    except (ValueError, FileNotFoundError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    result = validate_session_file(safe_path)

    if result.warnings:
        for warning in result.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)

    if not result.is_valid:
        for error in result.errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: Phase gate validation successful")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(2)
