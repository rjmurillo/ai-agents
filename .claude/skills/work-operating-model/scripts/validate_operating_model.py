#!/usr/bin/env python3
"""Validate a work-operating-model JSON document against the v1 schema.

Reads a JSON file (or stdin when path is "-") and checks the contract
documented in references/entry-contract.md. Returns exit 0 when the
document conforms, non-zero otherwise.

The validator is intentionally permissive on optional fields. The output
format is meant to grow; new optional sections do not break old documents.
Breaking changes bump schema_version.

EXIT CODES (ADR-035):
    0 - Success: document conforms to the schema
    1 - Validation failure: document violates the schema
    2 - Invalid usage: bad CLI arguments or unreadable input
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"

CANONICAL_LAYERS: tuple[str, ...] = (
    "rhythms",
    "decisions",
    "dependencies",
    "institutional_knowledge",
    "friction",
)

REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "schema_version",
    "team",
    "rhythms",
    "decisions",
    "dependencies",
    "institutional_knowledge",
    "friction",
    "metadata",
)

ALLOWED_INTERVIEW_STATUS: tuple[str, ...] = ("in_progress", "complete")
ALLOWED_SOURCE: tuple[str, ...] = ("documented", "tacit")
ALLOWED_FORMALITY: tuple[str, ...] = ("formal", "informal")
ALLOWED_CRITICALITY: tuple[str, ...] = ("low", "medium", "high")
ALLOWED_DOC_STATUS: tuple[str, ...] = ("none", "partial", "complete")
ALLOWED_IMPACT: tuple[str, ...] = ("low", "medium", "high")
ALLOWED_CATEGORY: tuple[str, ...] = ("tooling", "process", "communication", "other")

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(document: Any) -> list[str]:
    """Validate a parsed operating-model document.

    Returns a list of human-readable errors. Empty list means the document
    conforms to the schema.
    """
    errors: list[str] = []

    if not isinstance(document, dict):
        return ["root: must be a JSON object"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in document:
            errors.append(f"missing required key: {key}")

    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version: expected {SCHEMA_VERSION!r}, got {document.get('schema_version')!r}"
        )

    errors.extend(_validate_team(document.get("team")))
    errors.extend(_validate_rhythms(document.get("rhythms")))
    errors.extend(_validate_decisions(document.get("decisions")))
    errors.extend(_validate_dependencies(document.get("dependencies")))
    errors.extend(_validate_institutional_knowledge(document.get("institutional_knowledge")))
    errors.extend(_validate_friction(document.get("friction")))
    errors.extend(_validate_metadata(document.get("metadata")))

    return errors


def _validate_team(team: Any) -> list[str]:
    if not isinstance(team, dict):
        return ["team: must be an object"]
    errors: list[str] = []
    name = team.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("team.name: must be a non-empty string")
    if "size" in team and team["size"] is not None:
        size = team["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append("team.size: must be a non-negative integer or null")
    return errors


def _validate_rhythms(rhythms: Any) -> list[str]:
    if not isinstance(rhythms, dict):
        return ["rhythms: must be an object"]
    errors: list[str] = []
    cadences = rhythms.get("cadences", [])
    if not isinstance(cadences, list):
        errors.append("rhythms.cadences: must be a list")
    else:
        for i, cadence in enumerate(cadences):
            if not isinstance(cadence, dict):
                errors.append(f"rhythms.cadences[{i}]: must be an object")
                continue
            errors.extend(
                _validate_enum(cadence, "source", ALLOWED_SOURCE, f"rhythms.cadences[{i}]")
            )
    milestones = rhythms.get("milestones", [])
    if not isinstance(milestones, list):
        errors.append("rhythms.milestones: must be a list")
    return errors


def _validate_decisions(decisions: Any) -> list[str]:
    if not isinstance(decisions, dict):
        return ["decisions: must be an object"]
    errors: list[str] = []
    rights = decisions.get("decision_rights", [])
    if not isinstance(rights, list):
        errors.append("decisions.decision_rights: must be a list")
    else:
        for i, right in enumerate(rights):
            prefix = f"decisions.decision_rights[{i}]"
            if not isinstance(right, dict):
                errors.append(f"{prefix}: must be an object")
                continue
            errors.extend(_validate_enum(right, "formality", ALLOWED_FORMALITY, prefix))
            errors.extend(_validate_enum(right, "source", ALLOWED_SOURCE, prefix))
    triggers = decisions.get("review_triggers", [])
    if not isinstance(triggers, list):
        errors.append("decisions.review_triggers: must be a list")
    return errors


def _validate_dependencies(dependencies: Any) -> list[str]:
    if not isinstance(dependencies, dict):
        return ["dependencies: must be an object"]
    errors: list[str] = []
    for direction in ("upstream", "downstream"):
        items = dependencies.get(direction, [])
        if not isinstance(items, list):
            errors.append(f"dependencies.{direction}: must be a list")
            continue
        for i, item in enumerate(items):
            prefix = f"dependencies.{direction}[{i}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix}: must be an object")
                continue
            errors.extend(_validate_enum(item, "criticality", ALLOWED_CRITICALITY, prefix))
            errors.extend(_validate_enum(item, "source", ALLOWED_SOURCE, prefix))
    return errors


def _validate_institutional_knowledge(knowledge: Any) -> list[str]:
    if not isinstance(knowledge, dict):
        return ["institutional_knowledge: must be an object"]
    errors: list[str] = []
    tacit = knowledge.get("tacit", [])
    if not isinstance(tacit, list):
        errors.append("institutional_knowledge.tacit: must be a list")
    else:
        for i, item in enumerate(tacit):
            if not isinstance(item, dict):
                errors.append(f"institutional_knowledge.tacit[{i}]: must be an object")
                continue
            errors.extend(
                _validate_enum(
                    item,
                    "documentation_status",
                    ALLOWED_DOC_STATUS,
                    f"institutional_knowledge.tacit[{i}]",
                )
            )
    return errors


def _validate_friction(friction: Any) -> list[str]:
    if not isinstance(friction, dict):
        return ["friction: must be an object"]
    errors: list[str] = []
    blockers = friction.get("blockers", [])
    if not isinstance(blockers, list):
        errors.append("friction.blockers: must be a list")
    else:
        for i, blocker in enumerate(blockers):
            prefix = f"friction.blockers[{i}]"
            if not isinstance(blocker, dict):
                errors.append(f"{prefix}: must be an object")
                continue
            errors.extend(_validate_enum(blocker, "impact", ALLOWED_IMPACT, prefix))
            errors.extend(_validate_enum(blocker, "category", ALLOWED_CATEGORY, prefix))
    return errors


def _validate_metadata(metadata: Any) -> list[str]:
    if not isinstance(metadata, dict):
        return ["metadata: must be an object"]
    errors: list[str] = []

    date = metadata.get("interview_date")
    if not isinstance(date, str) or not DATE_PATTERN.match(date):
        errors.append("metadata.interview_date: must match YYYY-MM-DD")

    status = metadata.get("interview_status")
    if status not in ALLOWED_INTERVIEW_STATUS:
        errors.append(
            f"metadata.interview_status: must be one of {ALLOWED_INTERVIEW_STATUS}, got {status!r}"
        )

    completed = metadata.get("completed_layers")
    if not isinstance(completed, list):
        errors.append("metadata.completed_layers: must be a list")
    else:
        for layer in completed:
            if layer not in CANONICAL_LAYERS:
                errors.append(
                    f"metadata.completed_layers: unknown layer {layer!r} "
                    f"(allowed: {CANONICAL_LAYERS})"
                )

    return errors


def _validate_enum(
    container: Any,
    key: str,
    allowed: tuple[str, ...],
    prefix: str,
) -> list[str]:
    if not isinstance(container, dict) or key not in container:
        return []
    value = container[key]
    if value not in allowed:
        return [f"{prefix}.{key}: must be one of {allowed}, got {value!r}"]
    return []


def _resolve_path_safely(path: str) -> Path:
    """Resolve a CLI path argument, blocking traversal that escapes the cwd boundary.

    Resolves symlinks via Path.resolve() so symlink-based traversal cannot bypass
    containment. Anchors relative paths to the current working directory and rejects
    any resolved path that escapes both the cwd and the repository root (when one
    can be located).
    """
    candidate = Path(path)  # security-scan: ignore CWE-22
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
    )

    cwd = Path.cwd().resolve()
    if resolved.is_relative_to(cwd):
        return resolved

    repo_root = _find_repo_root()
    if repo_root is not None and resolved.is_relative_to(repo_root):
        return resolved

    raise PermissionError(
        f"path traversal blocked: '{path}' resolves to '{resolved}' which is outside cwd '{cwd}'"
    )


def _find_repo_root() -> Path | None:
    """Walk upward from this file until a .git directory is found."""
    for parent in Path(__file__).resolve().parents:  # security-scan: ignore CWE-22
        if (parent / ".git").exists():
            return parent
    return None


def load_document(path: str, validate_path: bool = True) -> Any:
    """Read and parse JSON from a file path or stdin.

    Args:
        path: File path, or '-' for stdin.
        validate_path: When True (default), enforce CWE-22 containment via
            ``_resolve_path_safely``. Tests may pass False to read fixture
            files outside the repository (for example, ``pytest`` ``tmp_path``).

    Raises:
        FileNotFoundError: when the file does not exist.
        OSError: when the file cannot be read.
        json.JSONDecodeError: when input is not valid JSON.
        PermissionError: when ``validate_path`` is True and ``path`` resolves
            outside the cwd or repository root.
    """
    if path == "-":
        text = sys.stdin.read()
    else:
        if validate_path:
            target = _resolve_path_safely(path)
        else:
            target = Path(path)  # security-scan: ignore CWE-22
        with open(target, encoding="utf-8") as handle:  # security-scan: ignore CWE-22
            text = handle.read()
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        description="Validate a work-operating-model JSON document.",
    )
    parser.add_argument(
        "path",
        help="Path to operating-model.json. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--skip-path-validation",
        action="store_true",
        help="Skip CWE-22 path containment check (for testing only).",
    )
    args = parser.parse_args(argv)

    try:
        document = load_document(args.path, validate_path=not args.skip_path_validation)
    except FileNotFoundError:
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot read {args.path}: {exc}", file=sys.stderr)
        return 2

    errors = validate(document)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
